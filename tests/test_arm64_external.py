# SPDX-License-Identifier: MPL-2.0

import hashlib
import io
import json
import os
import tarfile
from pathlib import Path

import pytest

from scripts.arm64 import fetch_external
from scripts.arm64.assemble import AssemblyError, assemble
from scripts.arm64.fetch_external import FetchError, _extract_archive, fetch_release
from scripts.arm64.provenance import write_provenance
from scripts.build_common import CLEARED_DOS_STUB

RELEASE_ID = "wine-11-18-arm64-v5"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _catalog(release: dict, archive: bytes = b"archive") -> bytes:
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
    (wine / "lib" / "wine" / "aarch64-unix").mkdir(parents=True)
    (wine / "lib" / "wine" / "aarch64-windows").mkdir(parents=True)
    (wine / "share" / "licenses" / "fex-wine").mkdir(parents=True)
    (wine / "share" / "licenses" / "fex-wine" / "LICENSE").write_text("FEX license")
    (wine / "lib" / "wine" / "aarch64-unix" / "wine").write_bytes(b"wine loader")
    (wine / "bin" / "wine").symlink_to("../lib/wine/aarch64-unix/wine")

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

    fetch_release(
        env_name="ARM64_RUNTIME_CATALOG_URL",
        release_id=RELEASE_ID,
        expected_sha256=_sha256(archive),
        output=tmp_path / "wine.tar.xz",
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
        fetch_release(
            env_name="ARM64_RUNTIME_CATALOG_URL",
            release_id=RELEASE_ID,
            expected_sha256=_sha256(archive),
            output=tmp_path / "wine.tar.xz",
            fetch=lambda url: catalog,
        )


def test_fetch_rejects_a_catalog_sha_mismatch(tmp_path, monkeypatch):
    archive = b"fake wine archive"
    monkeypatch.setenv(
        "ARM64_RUNTIME_CATALOG_URL", "https://catalog.example/catalog.json"
    )
    catalog = _catalog(
        {
            "id": RELEASE_ID,
            "arch": "arm64",
            "sha256": "0" * 64,
            "url": "https://download.example/archive.tar.xz",
        }
    )

    with pytest.raises(FetchError, match="SHA-256"):
        fetch_release(
            env_name="ARM64_RUNTIME_CATALOG_URL",
            release_id=RELEASE_ID,
            expected_sha256=_sha256(archive),
            output=tmp_path / "wine.tar.xz",
            fetch=lambda url: catalog,
        )


def test_fetch_rejects_a_size_mismatch(tmp_path, monkeypatch):
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

    with pytest.raises(FetchError, match="size"):
        fetch_release(
            env_name="ARM64_RUNTIME_CATALOG_URL",
            release_id=RELEASE_ID,
            expected_sha256=_sha256(archive),
            output=tmp_path / "wine.tar.xz",
            fetch=responses.__getitem__,
        )


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
        fetch_release(
            env_name="ARM64_RUNTIME_CATALOG_URL",
            release_id=RELEASE_ID,
            expected_sha256="0" * 64,
            output=tmp_path / "wine.tar.xz",
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


def test_fetch_target_requests_only_the_wine_archive(tmp_path, monkeypatch):
    calls = []

    def fake_fetch(env_name, release_id, expected_sha256, output):
        calls.append((env_name, release_id, expected_sha256))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"archive")
        return output

    def fake_extract(archive, destination):
        (destination / "wine").mkdir()

    monkeypatch.setattr(fetch_external, "fetch_release", fake_fetch)
    monkeypatch.setattr(fetch_external, "_extract_archive", fake_extract)

    fetch_external._fetch_target(
        {
            "artifact": {
                "catalog": "wine",
                "release": RELEASE_ID,
                "sha256": "0" * 64,
            }
        },
        tmp_path / "incoming",
    )

    assert calls == [("ARM64_RUNTIME_CATALOG_URL", RELEASE_ID, "0" * 64)]


def test_fetch_target_rejects_a_non_wine_catalog(tmp_path):
    with pytest.raises(FetchError, match="wine"):
        fetch_external._fetch_target(
            {
                "artifact": {
                    "catalog": "dxmt",
                    "release": RELEASE_ID,
                    "sha256": "0" * 64,
                }
            },
            tmp_path / "incoming",
        )


def test_assemble_moves_the_wine_tree_and_adds_links(tmp_path):
    wine_root, dxmt_root = _build_external_trees(tmp_path)

    layout = assemble(wine_root, dxmt_root, tmp_path / "Libraries")

    assert (layout / "Wine/bin/wine64").is_symlink()
    assert (layout / "Wine/bin/Arknights").is_symlink()
    assert os.readlink(layout / "Wine/bin/wine64") == "wine"
    assert os.readlink(layout / "Wine/bin/Arknights") == "wine64"
    assert (layout / "DXMT/x64/d3d11.dll").is_file()
    assert (layout / "Wine/lib/wine/aarch64-unix/winemetal.so").is_file()
    assert (layout / "Wine/lib/wine/aarch64-windows/winemetal.dll").is_file()
    assert (tmp_path / "Licenses/external/fex-wine/LICENSE").is_file()
    assert (tmp_path / "NOTICE.md").is_file()


def test_assemble_clears_the_wine_dos_stub(tmp_path):
    wine_root, dxmt_root = _build_external_trees(tmp_path)

    layout = assemble(wine_root, dxmt_root, tmp_path / "Libraries")

    with (layout / "DXMT/x64/d3d11.dll").open("rb") as file:
        file.seek(64)
        assert file.read(len(CLEARED_DOS_STUB)) == CLEARED_DOS_STUB


def test_assemble_rejects_a_symlink_escape(tmp_path):
    _, dxmt_root = _build_external_trees(tmp_path)
    wine_root = tmp_path / "escape"
    (wine_root / "bin").mkdir(parents=True)
    (wine_root / "bin" / "escape").symlink_to("../../outside")

    with pytest.raises(AssemblyError, match="escape"):
        assemble(wine_root, dxmt_root, tmp_path / "Libraries")


def test_provenance_records_the_external_build_without_urls(tmp_path):
    runtime_archive = tmp_path / "Arknights-MacOS-Runtime-v0.9.0+arm.tar.gz"
    runtime_archive.write_bytes(b"runtime payload")
    source_archive = tmp_path / "Arknights-MacOS-Runtime-v0.9.0+arm-source.tar.gz"
    source_archive.write_bytes(b"source payload")
    lock = {
        "buildMode": "external",
        "target": "native-arm64",
        "deploymentTarget": "26.0",
        "interface": {"minimumMacOS": "26.0"},
        "features": {
            "hardwareCursor": True,
            "metalFXSpatialUpscaling": True,
            "nativeFullscreenSpace": True,
        },
        "sources": {"wine": {"commit": "7b3fff76fa5178f6ce0141b2c776afa2a822f101"}},
    }

    write_provenance(
        lock,
        "v0.9.0+arm",
        runtime_archive,
        source_archive,
        tmp_path / "provenance.json",
    )

    data = json.loads((tmp_path / "provenance.json").read_text())
    assert data["releaseTag"] == "v0.9.0+arm"
    assert data["target"] == "native-arm64"
    assert data["minimumMacOS"] == "26.0"
    assert data["features"] == {
        "hardwareCursor": True,
        "metalFXSpatialUpscaling": True,
        "nativeFullscreenSpace": True,
    }
    assert (
        data["externalBuild"]["repository"]
        == "https://github.com/riverfog7/wine-build-new"
    )
    assert (
        data["externalBuild"]["revision"] == "7b3fff76fa5178f6ce0141b2c776afa2a822f101"
    )
    assert data["runtimeArchive"]["name"] == "Arknights-MacOS-Runtime-v0.9.0+arm.tar.gz"
    assert data["runtimeArchive"]["sha256"] == _sha256(b"runtime payload")
    assert data["correspondingSourceArchive"]["sha256"] == _sha256(b"source payload")

    raw = (tmp_path / "provenance.json").read_text()
    assert "catalog" not in raw
    assert "pull/4" not in raw
