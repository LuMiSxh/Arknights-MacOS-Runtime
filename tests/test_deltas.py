# SPDX-License-Identifier: MPL-2.0

import fnmatch
import hashlib
import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from typing import Any

import pytest

from scripts.release.deltas import (
    DeltaError,
    apply_delta_archive,
    apply_patch,
    diff_bytes,
    download_runtime_archive,
    extract_install_root,
    select_sources,
    tree_entries,
    write_delta,
)

VECTOR_OLD = b"ABCDEFGH"
VECTOR_NEW = b"ABXDEFGH!"
VECTOR_HEX = (
    "5254425344463031"  # magic "RTBSDF01"
    "0900000000000000"  # newSize 9
    "0100000000000000"  # controlCount 1
    "0800000000000000"  # control: add 8
    "0100000000000000"  # control: copy 1
    "0000000000000000"  # control: seek 0
    "0000150000000000"  # diff bytes
    "21"  # extra bytes
)

# File path -> (content, executable). Links map a path to its relative target.
SOURCE_FILES = {
    "bin/wine": (b"wine loader, revision one\n" * 20, True),
    "lib/keep.dll": (b"unchanged library\n" * 20, False),
    "lib/patch.so": (b"library body, first build\n" * 20, False),
    "lib/mode.sh": (b"echo mode\n" * 5, True),
    "lib/remove.txt": (b"only in the source\n", False),
    "share/doc/readme": (b"readme\n", False),
}
SOURCE_LINKS = {"bin/wine64": "wine"}
TARGET_FILES = {
    "bin/wine": (b"wine loader, revision two\n" * 20, True),
    "lib/keep.dll": (b"unchanged library\n" * 20, False),
    "lib/patch.so": (b"library body, second build\n" * 20, False),
    "lib/mode.sh": (b"echo mode\n" * 5, False),
    "lib/add.so": (b"only in the target\n", True),
    "share/doc/readme": (b"readme\n", False),
}
TARGET_LINKS = {"bin/wine64": "wine"}


def _write_tree(
    root: Path, files: dict[str, tuple[bytes, bool]], links: dict[str, str]
) -> None:
    for relative, (content, executable) in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(0o755 if executable else 0o644)
    for relative, target in links.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, path)


def _operations(archive: Path, scratch: Path) -> set[str]:
    with tarfile.open(archive, "r:xz") as tar:
        tar.extractall(scratch, filter="data")
    document = json.loads(
        (scratch / "Delta" / "delta.json").read_text(encoding="utf-8")
    )
    return {entry["op"] for entry in document["entries"] if "op" in entry}


class DeltaRoundTripTests(unittest.TestCase):
    def test_applying_a_delta_reproduces_the_target_tree_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            _write_tree(source, SOURCE_FILES, SOURCE_LINKS)
            _write_tree(target, TARGET_FILES, TARGET_LINKS)
            (root / "dist").mkdir()
            archive = write_delta(
                version="1.0.2",
                source_version="1.0.1",
                arch="arm64",
                source_root=source,
                target_root=target,
                directory=root / "dist",
            )

            self.assertEqual(
                _operations(archive, root / "extracted"), {"keep", "patch", "add"}
            )
            result = root / "result"
            apply_delta_archive(archive, source, result)

            self.assertEqual(tree_entries(result), tree_entries(target))


class SelectSourcesTests(unittest.TestCase):
    def test_selects_the_newest_published_releases_other_than_the_current_one(
        self,
    ) -> None:
        releases: list[dict[str, Any]] = [
            _release("v1.0.1", "2026-10-01T10:00:00Z"),
            _release("v1.0.0", "2026-09-01T10:00:00Z"),
            _release("v1.0.2", "2026-11-01T10:00:00Z"),
            _release("v1.0.3", "2026-11-03T10:00:00Z", draft=True),
            _release("v1.0.4-rc1", "2026-11-05T10:00:00Z", prerelease=True),
            _release("v0.9.0", "2026-08-01T10:00:00Z"),
            _release("v0.8.0", "2026-07-01T10:00:00Z"),
        ]
        cases = [
            (
                "newest three, newest first",
                releases,
                "1.0.5",
                3,
                ["1.0.2", "1.0.1", "1.0.0"],
            ),
            (
                "the current release is skipped",
                releases,
                "1.0.2",
                3,
                ["1.0.1", "1.0.0", "0.9.0"],
            ),
            ("the count limits the list", releases, "1.0.5", 1, ["1.0.2"]),
            (
                "drafts and prereleases never serve",
                releases,
                "1.0.5",
                10,
                ["1.0.2", "1.0.1", "1.0.0", "0.9.0", "0.8.0"],
            ),
            ("no releases", [], "1.0.0", 3, []),
        ]
        for name, listed, current, count, expected in cases:
            with self.subTest(name):
                self.assertEqual(select_sources(listed, current, count), expected)


class PatchFormatTests(unittest.TestCase):
    def test_patch_bytes_match_the_rtbsdf01_vector(self) -> None:
        patch = bytes.fromhex(VECTOR_HEX)

        self.assertEqual(diff_bytes(VECTOR_OLD, VECTOR_NEW), patch)
        self.assertEqual(apply_patch(VECTOR_OLD, patch), VECTOR_NEW)


def _release(
    tag: str, published: str | None, *, draft: bool = False, prerelease: bool = False
) -> dict[str, Any]:
    return {
        "tagName": tag,
        "isDraft": draft,
        "isPrerelease": prerelease,
        "publishedAt": published,
    }


def _tar(path: Path, members: dict[str, bytes], mode: str) -> None:
    with tarfile.open(path, mode) as tar:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))


def _release_assets(tmp_path: Path, legacy: bool) -> dict[str, bytes]:
    staging = tmp_path / "staging"
    staging.mkdir()
    if legacy:
        name = "Arknights-MacOS-Runtime-v1.0.1-arm64.tar.gz"
        _tar(staging / name, {"Libraries/Wine/bin/wine": b"wine"}, "w:gz")
        digest = hashlib.sha256((staging / name).read_bytes()).hexdigest()
        (staging / f"{name}.sha256").write_text(f"{digest}  {name}\n")
    else:
        _tar(staging / "runtime-arm64.tar.xz", {"Runtime/bin/wine": b"wine"}, "w:xz")
        digest = hashlib.sha256((staging / "runtime-arm64.tar.xz").read_bytes())
        (staging / "SHA256SUMS").write_text(
            f"{digest.hexdigest()}  runtime-arm64.tar.xz\n"
        )
    return {path.name: path.read_bytes() for path in staging.iterdir()}


@pytest.mark.parametrize(
    ("legacy", "expected"),
    [
        (False, "runtime-arm64.tar.xz"),
        (True, "Arknights-MacOS-Runtime-v1.0.1-arm64.tar.gz"),
    ],
    ids=["current names", "legacy names of a previous release"],
)
def test_the_previous_release_downloads_under_current_and_legacy_names(
    tmp_path, monkeypatch, legacy, expected
):
    assets = _release_assets(tmp_path, legacy)

    def gh(*arguments: str) -> str:
        directory = Path(arguments[arguments.index("--dir") + 1])
        patterns = [
            arguments[i + 1] for i, a in enumerate(arguments) if a == "--pattern"
        ]
        matched = [n for n in assets if any(fnmatch.fnmatch(n, p) for p in patterns)]
        if not matched:
            raise DeltaError("no assets match")
        for name in matched:
            (directory / name).write_bytes(assets[name])
        return ""

    monkeypatch.setattr("scripts.release.deltas._gh", gh)

    archive = download_runtime_archive("1.0.1", "arm64", tmp_path / "download")

    assert archive.name == expected
    assert (
        extract_install_root(archive, tmp_path / "root") / "bin/wine"
    ).read_bytes() == b"wine"


if __name__ == "__main__":
    unittest.main()
