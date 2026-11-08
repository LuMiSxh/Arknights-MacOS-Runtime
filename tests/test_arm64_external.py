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
from scripts.arm64.fetch_external import (
    FetchError,
    _extract_archive,
    fetch_selected_release,
    select_release,
)
from scripts.arm64.provenance import ProvenanceError, write_provenance
from scripts.build_common import CLEARED_DOS_STUB, ROOT
from scripts.release.provenance import runtime_lock_provenance

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


def _interface() -> dict:
    return {
        "dxmtDirectory": "DXMT",
        "requiredFiles": [
            "DXMT/x64/d3d10core.dll",
            "DXMT/x64/d3d11.dll",
            "DXMT/x64/dxgi.dll",
        ],
    }


def _text_values(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from _text_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _text_values(child)
    elif isinstance(value, str):
        yield value


def test_selects_the_newest_arm64_release():
    releases = [
        {
            "id": "wine-11-18-arm64-v4",
            "arch": "arm64",
            "published_at": "2026-11-06T06:35:15Z",
        },
        {
            "id": "wine-11-18-arm64-v5",
            "arch": "arm64",
            "published_at": "2026-11-07T12:14:35Z",
        },
        {
            "id": "wine-11-18-x86_64-v9",
            "arch": "x86_64",
            "published_at": "2026-11-08T00:00:00Z",
        },
    ]

    assert select_release(releases, "")["id"] == "wine-11-18-arm64-v5"


def test_uses_the_highest_build_when_publish_dates_match():
    releases = [
        {
            "id": "wine-11-18-arm64-v4",
            "arch": "arm64",
            "published_at": "2026-11-07T12:14:35Z",
        },
        {
            "id": "wine-11-18-arm64-v6",
            "arch": "arm64",
            "published_at": "2026-11-07T12:14:35Z",
        },
    ]

    assert select_release(releases, "")["id"] == "wine-11-18-arm64-v6"


def test_rejects_a_catalog_without_arm64_releases():
    with pytest.raises(FetchError, match="arm64"):
        select_release([{"id": "wine-11-18-x86_64-v1", "arch": "x86_64"}], "")


def test_select_release_rejects_a_missing_published_at():
    releases = [
        {"id": "wine-11-18-arm64-v4", "arch": "arm64"},
        {
            "id": "wine-11-18-arm64-v5",
            "arch": "arm64",
            "published_at": "2026-11-07T12:14:35Z",
        },
    ]

    with pytest.raises(FetchError, match="published_at"):
        select_release(releases, "")


def test_select_release_rejects_an_invalid_published_at():
    releases = [
        {
            "id": "wine-11-18-arm64-v5",
            "arch": "arm64",
            "published_at": "not-a-date",
        }
    ]

    with pytest.raises(FetchError, match="published_at"):
        select_release(releases, "")


def test_explicit_release_id_wins_over_the_newest():
    releases = [
        {
            "id": "wine-11-18-arm64-v5",
            "arch": "arm64",
            "published_at": "2026-11-07T12:14:35Z",
        },
        {
            "id": "wine-11-18-arm64-v4",
            "arch": "arm64",
            "published_at": "2026-11-06T06:35:15Z",
        },
    ]

    assert (
        select_release(releases, "wine-11-18-arm64-v4")["id"] == "wine-11-18-arm64-v4"
    )


def test_fetch_uses_the_newest_arm64_release_by_default(tmp_path, monkeypatch):
    newest = b"newest archive"
    older = b"older archive"
    catalog_url = "https://catalog.example/catalog.json"
    newest_url = "https://download.example/newest.tar.xz"
    older_url = "https://download.example/older.tar.xz"
    catalog = json.dumps(
        {
            "releases": [
                {
                    "id": "wine-11-18-arm64-v4",
                    "arch": "arm64",
                    "published_at": "2026-11-06T06:35:15Z",
                    "sha256": _sha256(older),
                    "url": older_url,
                },
                {
                    "id": "wine-11-18-arm64-v5",
                    "arch": "arm64",
                    "published_at": "2026-11-07T12:14:35Z",
                    "sha256": _sha256(newest),
                    "url": newest_url,
                },
            ]
        }
    ).encode()
    monkeypatch.setenv("ARM64_RUNTIME_CATALOG_URL", catalog_url)
    responses = {catalog_url: catalog, newest_url: newest, older_url: older}

    release, path = fetch_selected_release(
        "ARM64_RUNTIME_CATALOG_URL",
        "",
        tmp_path / "wine.tar.xz",
        fetch=responses.__getitem__,
    )

    assert release["id"] == "wine-11-18-arm64-v5"
    assert path.read_bytes() == newest


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
        fetch_selected_release(
            "ARM64_RUNTIME_CATALOG_URL",
            RELEASE_ID,
            tmp_path / "wine.tar.xz",
            expected_sha256=_sha256(archive),
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
        fetch_selected_release(
            "ARM64_RUNTIME_CATALOG_URL",
            RELEASE_ID,
            tmp_path / "wine.tar.xz",
            expected_sha256=_sha256(archive),
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


def test_fetch_target_requests_only_the_wine_archive(tmp_path, monkeypatch):
    calls = []

    def fake_fetch(env_name, release_id, output):
        calls.append((env_name, release_id))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"archive")
        return (
            {
                "id": RELEASE_ID,
                "arch": "arm64",
                "sha256": "0" * 64,
                "size": 7,
            },
            output,
        )

    def fake_extract(archive, destination):
        (destination / "wine").mkdir()

    monkeypatch.setattr(fetch_external, "fetch_selected_release", fake_fetch)
    monkeypatch.setattr(fetch_external, "_extract_archive", fake_extract)

    output = tmp_path / "incoming"
    fetch_external._fetch_target(
        {
            "artifact": {
                "catalog": "wine",
                "release": RELEASE_ID,
                "sha256": "0" * 64,
            }
        },
        output,
        "wine-11-18-arm64-v4",
    )

    assert calls == [("ARM64_RUNTIME_CATALOG_URL", "wine-11-18-arm64-v4")]
    metadata = json.loads((output / "external.json").read_text())
    assert metadata["id"] == RELEASE_ID
    assert metadata["sha256"] == "0" * 64


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
            "",
        )


@pytest.mark.parametrize(
    ("catalog_id", "sha256"),
    [("wine-11-18-arm64-v6", "b" * 64), (RELEASE_ID, "c" * 64)],
    ids=["newer-release", "rebuilt-archive"],
)
def test_fetch_target_updates_the_lock_when_the_catalog_release_differs(
    tmp_path, monkeypatch, catalog_id, sha256
):
    pin_writes = []

    def fake_fetch(env_name, release_id, output, expected_sha256=None, fetch=None):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"archive")
        return (
            {
                "id": catalog_id,
                "arch": "arm64",
                "sha256": sha256,
                "size": 7,
            },
            output,
        )

    def fake_extract(archive, destination):
        (destination / "wine").mkdir()

    def fake_write_artifact_pin(root, target, release, pinned_sha256):
        pin_writes.append((target, release, pinned_sha256))
        return True

    monkeypatch.setattr(fetch_external, "fetch_selected_release", fake_fetch)
    monkeypatch.setattr(fetch_external, "_extract_archive", fake_extract)
    monkeypatch.setattr(fetch_external, "write_artifact_pin", fake_write_artifact_pin)

    fetch_external._fetch_target(
        {
            "target": "native-arm64",
            "artifact": {
                "catalog": "wine",
                "release": RELEASE_ID,
                "sha256": "a" * 64,
            },
        },
        tmp_path / "incoming",
        "",
    )

    assert pin_writes == [("native-arm64", catalog_id, sha256)]


def test_fetch_target_keeps_the_lock_when_extraction_fails(tmp_path, monkeypatch):
    pin_writes = []

    def fake_fetch(env_name, release_id, output, expected_sha256=None, fetch=None):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"archive")
        return (
            {
                "id": "wine-11-18-arm64-v6",
                "arch": "arm64",
                "sha256": "b" * 64,
                "size": 7,
            },
            output,
        )

    def failing_extract(archive, destination):
        raise FetchError("cannot extract the wine archive: broken")

    def fake_write_artifact_pin(root, target, release, sha256):
        pin_writes.append((target, release, sha256))
        return True

    monkeypatch.setattr(fetch_external, "fetch_selected_release", fake_fetch)
    monkeypatch.setattr(fetch_external, "_extract_archive", failing_extract)
    monkeypatch.setattr(fetch_external, "write_artifact_pin", fake_write_artifact_pin)

    with pytest.raises(FetchError, match="cannot extract"):
        fetch_external._fetch_target(
            {
                "target": "native-arm64",
                "artifact": {
                    "catalog": "wine",
                    "release": RELEASE_ID,
                    "sha256": "a" * 64,
                },
            },
            tmp_path / "incoming",
            "",
        )

    assert pin_writes == []


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

    runtime_lock = {
        "path": "runtime.lock.json",
        "sha256": "d" * 64,
        "contents": lock,
    }
    validation = {
        "target": "native-arm64",
        "deploymentTarget": "26.0",
        "inheritedMachOAboveTarget": 0,
        "releaseEligible": False,
        "builtExternally": True,
    }

    write_provenance(
        lock,
        "v0.9.0+arm",
        runtime_archive,
        source_archive,
        tmp_path / "provenance.json",
        source_commit="c" * 40,
        runtime_lock=runtime_lock,
        validation=validation,
    )

    data = json.loads((tmp_path / "provenance.json").read_text())
    assert data["releaseTag"] == "v0.9.0+arm"
    assert data["sourceCommit"] == "c" * 40
    assert data["runtimeLock"] == runtime_lock
    assert data["validation"] == validation
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

    data = json.loads((tmp_path / "provenance.json").read_text())
    assert "catalog" not in data
    assert "externalArtifact" not in data
    assert not any("pull/4" in text for text in _text_values(data))


def test_provenance_records_the_selected_catalog_artifact(tmp_path):
    runtime_archive = tmp_path / "Arknights-MacOS-Runtime-v0.9.0+arm.tar.gz"
    runtime_archive.write_bytes(b"runtime payload")
    source_archive = tmp_path / "Arknights-MacOS-Runtime-v0.9.0+arm-source.tar.gz"
    source_archive.write_bytes(b"source payload")
    external = tmp_path / "external.json"
    external.write_text(
        json.dumps(
            {
                "id": RELEASE_ID,
                "arch": "arm64",
                "sha256": "a" * 64,
                "size": 7,
            }
        ),
        encoding="utf-8",
    )
    lock = {
        "buildMode": "external",
        "target": "native-arm64",
        "deploymentTarget": "26.0",
        "interface": {"minimumMacOS": "26.0"},
        "artifact": {"catalog": "wine", "release": RELEASE_ID, "sha256": "a" * 64},
        "features": {},
        "sources": {"wine": {"commit": "7b3fff76fa5178f6ce0141b2c776afa2a822f101"}},
    }

    runtime_lock = {
        "path": "runtime.lock.json",
        "sha256": "d" * 64,
        "contents": lock,
    }

    write_provenance(
        lock,
        "v0.9.0+arm",
        runtime_archive,
        source_archive,
        tmp_path / "provenance.json",
        source_commit="c" * 40,
        runtime_lock=runtime_lock,
        external_artifact=external,
    )

    data = json.loads((tmp_path / "provenance.json").read_text())
    assert data["externalArtifact"] == {
        "id": RELEASE_ID,
        "sha256": "a" * 64,
        "size": 7,
    }


def test_provenance_rejects_artifact_metadata_that_differs_from_the_lock(tmp_path):
    runtime_archive = tmp_path / "runtime.tar.gz"
    runtime_archive.write_bytes(b"runtime")
    source_archive = tmp_path / "source.tar.gz"
    source_archive.write_bytes(b"source")
    external = tmp_path / "external.json"
    external.write_text(
        json.dumps({"id": "wine-11-18-arm64-v6", "sha256": "b" * 64, "size": 7}),
        encoding="utf-8",
    )
    lock = {
        "buildMode": "external",
        "target": "native-arm64",
        "deploymentTarget": "26.0",
        "interface": {"minimumMacOS": "26.0"},
        "artifact": {"catalog": "wine", "release": RELEASE_ID, "sha256": "a" * 64},
        "features": {},
        "sources": {"wine": {"commit": "7b3fff76fa5178f6ce0141b2c776afa2a822f101"}},
    }

    runtime_lock = {
        "path": "runtime.lock.json",
        "sha256": "d" * 64,
        "contents": lock,
    }

    with pytest.raises(ProvenanceError, match="lock pin"):
        write_provenance(
            lock,
            "v0.9.0+arm",
            runtime_archive,
            source_archive,
            tmp_path / "provenance.json",
            source_commit="c" * 40,
            runtime_lock=runtime_lock,
            external_artifact=external,
        )


def test_provenance_rejects_a_short_build_commit(tmp_path):
    runtime_archive = tmp_path / "runtime.tar.gz"
    runtime_archive.write_bytes(b"runtime")
    source_archive = tmp_path / "source.tar.gz"
    source_archive.write_bytes(b"source")
    lock = {
        "buildMode": "external",
        "target": "native-arm64",
        "interface": {"minimumMacOS": "26.0"},
        "features": {},
        "sources": {"wine": {"commit": "7b3fff76fa5178f6ce0141b2c776afa2a822f101"}},
    }

    with pytest.raises(ProvenanceError, match="full commit hash"):
        write_provenance(
            lock,
            "v0.9.0+arm",
            runtime_archive,
            source_archive,
            tmp_path / "provenance.json",
            source_commit="7b3fff76",
            runtime_lock={
                "path": "runtime.lock.json",
                "sha256": "d" * 64,
                "contents": lock,
            },
        )


def test_runtime_lock_provenance_resolves_the_target_view():
    runtime_lock = runtime_lock_provenance(ROOT, "native-arm64")
    contents = runtime_lock["contents"]

    assert runtime_lock["path"] == "runtime.lock.json"
    assert len(runtime_lock["sha256"]) == 64
    assert contents["target"] == "native-arm64"
    assert {"wine", "dxmt"} <= contents["sources"].keys()
    for name in ("wine", "dxmt"):
        assert {"repository", "commit", "version"} <= contents["sources"][name].keys()
