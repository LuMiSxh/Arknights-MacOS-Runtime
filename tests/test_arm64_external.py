# SPDX-License-Identifier: MPL-2.0

import hashlib
import io
import json
import os
import tarfile
from pathlib import Path

import pytest

from scripts.build_common import CLEARED_DOS_STUB
from scripts.lanes import arm64_external as fetch_external
from scripts.lanes.arm64_assemble import AssemblyError, assemble
from scripts.lanes.arm64_external import (
    FetchError,
    _extract_archive,
    fetch_selected_release,
)
from scripts.lock.model import Artifact, DxmtPayload, Interface, Lane, Launcher

RELEASE_ID = "wine-11-18-arm64-v5"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _catalog(release: dict) -> bytes:
    return json.dumps({"releases": [release]}).encode()


def _release(archive: bytes, *, arch: str = "arm64", size: int | None = None) -> dict:
    release = {
        "id": RELEASE_ID,
        "arch": arch,
        "sha256": _sha256(archive),
        "url": "https://download.example/archive.tar.xz",
    }
    if size is not None:
        release["size"] = size
    return release


def _interface() -> Interface:
    return Interface(
        executables=("bin/wine64",),
        required_files=(),
        mac_driver="lib/wine/aarch64-unix/winemac.so",
        launcher=Launcher("bin/Arknights", "wine64"),
        dxmt=DxmtPayload(
            "DXMT", {"x64": "system32"}, ("d3d10core.dll", "d3d11.dll", "dxgi.dll")
        ),
        features={},
    )


def _lane() -> Lane:
    return Lane(
        name="native-arm64",
        arch="arm64",
        build="external",
        minimum_macos="26.5",
        sources={},
        interface=_interface(),
        base=None,
        artifact=Artifact("wine", RELEASE_ID, "a" * 64),
    )


def _text_values(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from _text_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _text_values(child)
    elif isinstance(value, str):
        yield value


def _single_member_tar(name: str, *, linkname: str | None = None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        info = tarfile.TarInfo(name)
        if linkname is not None:
            info.type = tarfile.SYMTYPE
            info.linkname = linkname
        tar.addfile(info, io.BytesIO())
    return buffer.getvalue()


def _build_external_trees(root: Path) -> tuple[Path, Path]:
    wine = root / "wine"
    (wine / "bin").mkdir(parents=True)
    aarch64_unix = wine / "lib" / "wine" / "aarch64-unix"
    loader_macos = aarch64_unix / "wine.app" / "Contents" / "MacOS"
    loader_macos.mkdir(parents=True)
    (wine / "lib" / "wine" / "aarch64-windows").mkdir(parents=True)
    (wine / "share" / "licenses" / "fex-wine").mkdir(parents=True)
    (wine / "share" / "licenses" / "fex-wine" / "LICENSE").write_text("FEX license")
    (loader_macos / "wine").write_bytes(b"wine loader")
    (aarch64_unix / "wine").symlink_to("wine.app/Contents/MacOS/wine")
    (wine / "bin" / "wine").symlink_to(
        "../lib/wine/aarch64-unix/wine.app/Contents/MacOS/wine"
    )

    dxmt = root / "dxmt"
    (dxmt / "aarch64-unix").mkdir(parents=True)
    (dxmt / "aarch64-windows").mkdir(parents=True)
    (dxmt / "aarch64-unix" / "winemetal.so").write_bytes(b"winemetal.so payload")
    (dxmt / "aarch64-windows" / "winemetal.dll").write_bytes(b"winemetal.dll payload")
    for name in ("d3d10core.dll", "d3d11.dll", "dxgi.dll"):
        (dxmt / "aarch64-windows" / name).write_bytes(
            bytes(64) + b"Wine builtin DLL\0" + b"\0" * 16 + name.encode()
        )
    return wine, dxmt


def test_fetch_never_prints_the_catalog_url(tmp_path, monkeypatch, capsys):
    archive = b"fake wine archive"
    catalog_url = "https://catalog.example/catalog.json"
    archive_url = "https://download.example/archive.tar.xz"
    catalog = _catalog(
        {
            "id": RELEASE_ID,
            "arch": "arm64",
            "sha256": _sha256(archive),
            "size": len(archive),
            "url": archive_url,
        }
    )
    monkeypatch.setenv("ARM64_RUNTIME_CATALOG_URL", catalog_url)
    responses = {catalog_url: catalog, archive_url: archive}

    fetch_selected_release(
        "ARM64_RUNTIME_CATALOG_URL",
        RELEASE_ID,
        tmp_path / "wine.tar.xz",
        expected_sha256=_sha256(archive),
        fetch=responses.__getitem__,
    )

    captured = capsys.readouterr()
    assert "catalog.example" not in captured.out
    assert "catalog.example" not in captured.err
    assert "download.example" not in captured.out
    assert "download.example" not in captured.err
    assert (tmp_path / "wine.tar.xz").read_bytes() == archive


def test_fetch_rejects_a_non_arm64_release(tmp_path, monkeypatch):
    archive = b"fake wine archive"
    monkeypatch.setenv(
        "ARM64_RUNTIME_CATALOG_URL", "https://catalog.example/catalog.json"
    )
    catalog = _catalog(_release(archive, arch="x86_64"))

    with pytest.raises(FetchError, match="arm64"):
        fetch_selected_release(
            "ARM64_RUNTIME_CATALOG_URL",
            RELEASE_ID,
            tmp_path / "wine.tar.xz",
            expected_sha256=_sha256(archive),
            fetch=lambda url: catalog,
        )


def test_fetch_accepts_a_stale_catalog_digest(tmp_path, monkeypatch):
    archive = b"fake wine archive"
    catalog_url = "https://catalog.example/catalog.json"
    archive_url = "https://download.example/archive.tar.xz"
    catalog = _catalog(
        {
            "id": RELEASE_ID,
            "arch": "arm64",
            "sha256": "0" * 64,
            "url": archive_url,
        }
    )
    monkeypatch.setenv("ARM64_RUNTIME_CATALOG_URL", catalog_url)
    responses = {catalog_url: catalog, archive_url: archive}

    release, path = fetch_selected_release(
        "ARM64_RUNTIME_CATALOG_URL",
        RELEASE_ID,
        tmp_path / "wine.tar.xz",
        expected_sha256=_sha256(archive),
        fetch=responses.__getitem__,
    )

    assert release["id"] == RELEASE_ID
    assert path.read_bytes() == archive


def test_fetch_ignores_the_catalog_size(tmp_path, monkeypatch):
    archive = b"fake wine archive"
    catalog_url = "https://catalog.example/catalog.json"
    archive_url = "https://download.example/archive.tar.xz"
    catalog = _catalog(
        {
            "id": RELEASE_ID,
            "arch": "arm64",
            "sha256": _sha256(archive),
            "size": len(archive) + 1,
            "url": archive_url,
        }
    )
    monkeypatch.setenv("ARM64_RUNTIME_CATALOG_URL", catalog_url)
    responses = {catalog_url: catalog, archive_url: archive}

    _, path = fetch_selected_release(
        "ARM64_RUNTIME_CATALOG_URL",
        RELEASE_ID,
        tmp_path / "wine.tar.xz",
        expected_sha256=_sha256(archive),
        fetch=responses.__getitem__,
    )

    assert path.read_bytes() == archive


def test_fetch_rejects_an_archive_sha_mismatch(tmp_path, monkeypatch):
    catalog_url = "https://catalog.example/catalog.json"
    archive_url = "https://download.example/archive.tar.xz"
    catalog = _catalog(
        {
            "id": RELEASE_ID,
            "arch": "arm64",
            "sha256": "0" * 64,
            "url": archive_url,
        }
    )
    monkeypatch.setenv("ARM64_RUNTIME_CATALOG_URL", catalog_url)
    responses = {catalog_url: catalog, archive_url: b"wrong payload"}

    with pytest.raises(FetchError, match="SHA-256"):
        fetch_selected_release(
            "ARM64_RUNTIME_CATALOG_URL",
            RELEASE_ID,
            tmp_path / "wine.tar.xz",
            expected_sha256="0" * 64,
            fetch=responses.__getitem__,
        )


@pytest.mark.parametrize(
    ("name", "linkname"),
    [
        ("/absolute/path", None),
        ("../escape", None),
        ("C:/drive/path", None),
        ("__MACOSX/._metadata", None),
        ("._AppleDouble", None),
        ("link", "/outside"),
    ],
)
def test_extract_rejects_unsafe_archive_members(tmp_path, name, linkname):
    archive = tmp_path / "bad.tar"
    archive.write_bytes(_single_member_tar(name, linkname=linkname))

    with pytest.raises(FetchError):
        _extract_archive(archive, tmp_path / "out")


def test_fetch_target_takes_exactly_the_locked_release(tmp_path, monkeypatch):
    locked = b"locked archive"
    newer = b"newer archive"
    catalog_url = "https://catalog.example/catalog.json"
    locked_url = "https://download.example/locked.tar.xz"
    newer_url = "https://download.example/newer.tar.xz"
    catalog = json.dumps(
        {
            "releases": [
                {
                    "id": RELEASE_ID,
                    "arch": "arm64",
                    "published_at": "2026-11-07T12:14:35Z",
                    "sha256": _sha256(locked),
                    "url": locked_url,
                },
                {
                    "id": "wine-11-18-arm64-v6",
                    "arch": "arm64",
                    "published_at": "2026-11-08T12:14:35Z",
                    "sha256": _sha256(newer),
                    "url": newer_url,
                },
            ]
        }
    ).encode()
    monkeypatch.setenv("ARM64_RUNTIME_CATALOG_URL", catalog_url)
    responses = {catalog_url: catalog, locked_url: locked, newer_url: newer}

    release, path = fetch_selected_release(
        "ARM64_RUNTIME_CATALOG_URL",
        RELEASE_ID,
        tmp_path / "wine.tar.xz",
        _sha256(locked),
        fetch=responses.__getitem__,
    )

    assert release["id"] == RELEASE_ID
    assert path.read_bytes() == locked


def test_fetch_picks_the_newest_entry_when_the_catalog_repeats_an_id(
    tmp_path, monkeypatch
):
    older = b"older archive"
    newer = b"newer archive"
    catalog_url = "https://catalog.example/catalog.json"
    older_url = "https://download.example/older.tar.xz"
    newer_url = "https://download.example/newer.tar.xz"
    catalog = json.dumps(
        {
            "releases": [
                {
                    "id": RELEASE_ID,
                    "arch": "arm64",
                    "published_at": "2026-11-07T12:14:35Z",
                    "sha256": _sha256(older),
                    "url": older_url,
                },
                {
                    "id": RELEASE_ID,
                    "arch": "arm64",
                    "published_at": "2026-11-08T12:14:35Z",
                    "sha256": _sha256(newer),
                    "url": newer_url,
                },
            ]
        }
    ).encode()
    monkeypatch.setenv("ARM64_RUNTIME_CATALOG_URL", catalog_url)
    responses = {catalog_url: catalog, older_url: older, newer_url: newer}

    _, path = fetch_selected_release(
        "ARM64_RUNTIME_CATALOG_URL",
        RELEASE_ID,
        tmp_path / "wine.tar.xz",
        _sha256(newer),
        fetch=responses.__getitem__,
    )

    assert path.read_bytes() == newer


def test_fetch_target_rejects_bytes_that_differ_from_the_lock(tmp_path, monkeypatch):
    rebuilt = b"rebuilt archive"
    catalog_url = "https://catalog.example/catalog.json"
    archive_url = "https://download.example/archive.tar.xz"
    catalog = _catalog(_release(rebuilt))
    monkeypatch.setenv("ARM64_RUNTIME_CATALOG_URL", catalog_url)
    responses = {catalog_url: catalog, archive_url: rebuilt}

    with pytest.raises(FetchError, match="SHA-256"):
        fetch_external.fetch_target(
            _lane(), tmp_path / "incoming", fetch=responses.__getitem__
        )

    assert not (tmp_path / "incoming" / "wine.tar.xz").exists()


def test_assemble_moves_the_wine_tree_and_adds_links(tmp_path):
    wine_root, dxmt_root = _build_external_trees(tmp_path)

    layout = assemble(
        wine_root,
        dxmt_root,
        tmp_path / "Libraries",
        archive_root=tmp_path,
        interface=_interface(),
    )

    assert (layout / "Wine/bin/wine64").is_symlink()
    assert (layout / "Wine/bin/Arknights").is_symlink()
    assert os.readlink(layout / "Wine/bin/wine64") == "wine"
    assert os.readlink(layout / "Wine/bin/Arknights") == "wine64"
    assert (layout / "DXMT/x64/d3d11.dll").is_file()
    assert (layout / "Wine/lib/wine/aarch64-unix/winemetal.so").is_file()
    assert (layout / "Wine/lib/wine/aarch64-windows/winemetal.dll").is_file()
    assert (tmp_path / "Licenses/external/fex-wine/LICENSE").is_file()
    assert (tmp_path / "NOTICE.md").is_file()


def test_assemble_renames_the_loader_bundle_and_repoints_its_links(tmp_path):
    wine_root, dxmt_root = _build_external_trees(tmp_path)

    layout = assemble(
        wine_root,
        dxmt_root,
        tmp_path / "Libraries",
        archive_root=tmp_path,
        interface=_interface(),
    )

    wine = layout / "Wine"
    loader = layout / "Wine/lib/wine/aarch64-unix/Arknights.app/Contents/MacOS/wine"
    assert loader.read_bytes() == b"wine loader"
    assert not (wine / "lib/wine/aarch64-unix/wine.app").exists()
    assert (wine / "bin/wine").resolve() == loader.resolve()
    assert (wine / "lib/wine/aarch64-unix/wine").resolve() == loader.resolve()
    targets = [os.readlink(path) for path in wine.rglob("*") if path.is_symlink()]
    assert targets
    assert not any("wine.app" in target for target in targets)


def test_assemble_clears_the_wine_dos_stub(tmp_path):
    wine_root, dxmt_root = _build_external_trees(tmp_path)

    layout = assemble(
        wine_root,
        dxmt_root,
        tmp_path / "Libraries",
        archive_root=tmp_path,
        interface=_interface(),
    )

    with (layout / "DXMT/x64/d3d11.dll").open("rb") as file:
        file.seek(64)
        assert file.read(len(CLEARED_DOS_STUB)) == CLEARED_DOS_STUB


def test_assemble_rejects_a_symlink_escape(tmp_path):
    _, dxmt_root = _build_external_trees(tmp_path)
    wine_root = tmp_path / "escape"
    (wine_root / "bin").mkdir(parents=True)
    (wine_root / "bin" / "escape").symlink_to("../../outside")

    with pytest.raises(AssemblyError, match="escape"):
        assemble(
            wine_root,
            dxmt_root,
            tmp_path / "Libraries",
            archive_root=tmp_path,
            interface=_interface(),
        )
