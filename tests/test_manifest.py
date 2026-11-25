# SPDX-License-Identifier: MPL-2.0

import hashlib
import json
from pathlib import Path

import pytest
from lock_fixture import synthetic_lock

from scripts.release.manifest import finalize

LOCK = synthetic_lock([])
VERSION = "1.0.2"
DELTA = "runtime-arm64-from-1.0.1.delta.tar.xz"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fragment(target: str, arch: str, lock_sha256: str, dist: Path) -> dict:
    archive = dist / f"runtime-{arch}.tar.xz"
    archive.write_bytes(f"runtime {arch}".encode())
    (dist / f"source-{arch}.tar.xz").write_bytes(b"source")
    (dist / f"inventory-{arch}.tsv").write_text("component\trole\tsource\n")
    lane = LOCK["lanes"][target]
    wine, dxmt = lane["sources"]["wine"], lane["sources"]["dxmt"]
    return {
        "target": target,
        "arch": arch,
        "version": VERSION,
        "buildCommit": "7" * 40,
        "runtimeLock": {"sha256": lock_sha256},
        "wine": {
            **wine,
            **(
                {
                    "externalBuild": {
                        "repository": "https://example.org/build",
                        "commit": "8" * 40,
                    }
                }
                if target == "native-arm64"
                else {}
            ),
        },
        "dxmt": dxmt,
        "runtimeArchive": {
            "name": archive.name,
            "sha256": _digest(archive),
            "sizeBytes": archive.stat().st_size,
        },
    }


@pytest.fixture
def release(tmp_path):
    lock_path = tmp_path / "runtime.lock.json"
    lock_path.write_text(json.dumps(LOCK), encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    runtimes = [
        _fragment(target, arch, _digest(lock_path), dist)
        for target, arch in (("rosetta-x86_64", "x86_64"), ("native-arm64", "arm64"))
    ]
    (dist / "provenance.json").write_text(json.dumps({"runtimes": runtimes}))
    (dist / "THIRD-PARTY-NOTICES.txt").write_text("notices")
    (dist / "RELEASE-NOTES.md").write_text("notes")
    (dist / DELTA).write_bytes(b"delta")
    finalize(dist, lock_path)
    return dist


COMMON_PROVENANCE = {
    "buildRepository": "https://github.com/LuMiSxh/Arknights-MacOS-Runtime",
    "buildCommit": "7" * 40,
}


@pytest.mark.parametrize(
    ("arch", "target", "minimum", "components", "deltas", "provenance"),
    [
        (
            "x86_64",
            "rosetta-x86_64",
            "15.0",
            {"wine": "11.17", "dxmt": "0.80"},
            [],
            {
                "wineRepository": "https://github.com/example/wine",
                "wineCommit": "a" * 40,
                "dxmtRepository": "https://github.com/example/dxmt",
                "dxmtCommit": "b" * 40,
                "moltenvkRepository": "https://github.com/example/moltenvk",
                "moltenvkCommit": "e" * 40,
                "nixpkgsRepository": "https://github.com/example/nixpkgs",
                "nixpkgsCommit": "1" * 40,
                "baseRecipeRepository": "https://github.com/example/recipe",
                "baseRecipeCommit": "d" * 40,
                "baseArchiveUrl": "https://github.com/example/runtime/releases/download/v1/Libraries.tar.gz",
                "baseArchiveSha256": "c" * 64,
            },
        ),
        (
            "arm64",
            "native-arm64",
            "27.0",
            {"wine": "11.18", "dxmt": "0.80"},
            [
                {
                    "from": "1.0.1",
                    "name": DELTA,
                    "sha256": hashlib.sha256(b"delta").hexdigest(),
                    "sizeBytes": 5,
                }
            ],
            {
                "externalBuildRepository": "https://example.org/build",
                "externalBuildCommit": "8" * 40,
                "wineRepository": "https://github.com/example/wine",
                "wineCommit": "2" * 40,
                "dxmtRepository": "https://github.com/example/dxmt",
                "dxmtCommit": "4" * 40,
            },
        ),
    ],
)
def test_manifest_carries_archive_deltas_interface_and_provenance(
    release, arch, target, minimum, components, deltas, provenance
):
    runtime = f"runtime {arch}".encode()

    assert json.loads((release / f"runtime-{arch}.json").read_text()) == {
        "schemaVersion": 1,
        "arch": arch,
        "version": VERSION,
        "minimumMacOS": minimum,
        "archive": {
            "name": f"runtime-{arch}.tar.xz",
            "sha256": hashlib.sha256(runtime).hexdigest(),
            "sizeBytes": len(runtime),
        },
        "deltas": deltas,
        "interface": LOCK["lanes"][target]["interface"],
        "components": components,
        "provenance": {**COMMON_PROVENANCE, **provenance},
    }


def test_sha256sums_lists_every_asset_but_the_release_notes(release):
    sums = (release / "SHA256SUMS").read_text().splitlines()
    assets = sorted(
        path.name
        for path in release.iterdir()
        if path.name not in ("SHA256SUMS", "RELEASE-NOTES.md")
    )

    assert [line.split("  ")[1] for line in sums] == assets
    assert {"runtime-arm64.json", "runtime-x86_64.json", DELTA} <= set(assets)
    assert all(
        line == f"{_digest(release / name)}  {name}"
        for line, name in zip(sums, assets, strict=True)
    )
