# SPDX-License-Identifier: MPL-2.0

import json
import tempfile
import unittest
from pathlib import Path

from scripts.lanes import (
    inventory_name,
    notices_name,
    provenance_name,
    runtime_archive_name,
    source_archive_name,
)
from scripts.lib.artifact import sha256, write_archive
from scripts.release.combine import CombineError, combine

VERSION = "0.9.0"


def _write_lane(directory: Path, target: str, arch: str) -> None:
    """Write one lane output directory with a fragment and matching archives."""

    directory.mkdir(parents=True)
    content = directory / "content"
    (content / "Runtime").mkdir(parents=True)
    (content / "Runtime" / "marker").write_bytes(arch.encode())
    runtime = write_archive(
        directory,
        runtime_archive_name(VERSION, arch),
        [(content / "Runtime", "Runtime")],
    )
    source = directory / "source.txt"
    source.write_bytes(b"source")
    corresponding = write_archive(
        directory,
        source_archive_name(VERSION, arch),
        [(source, "source.txt")],
    )
    (directory / inventory_name(arch)).write_text(
        "component\trole\tsource\n", encoding="utf-8"
    )
    (directory / notices_name(arch)).write_text(f"{target} notices\n", encoding="utf-8")
    fragment = {
        "target": target,
        "arch": arch,
        "version": VERSION,
        "buildCommit": "1" * 40,
        "runtimeArchive": _record(runtime),
        "correspondingSourceArchive": _record(corresponding),
    }
    (directory / provenance_name(arch)).write_text(
        json.dumps(fragment), encoding="utf-8"
    )


def _record(path: Path) -> dict[str, object]:
    return {
        "name": path.name,
        "sha256": sha256(path),
        "sizeBytes": path.stat().st_size,
    }


class CombineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        self.x86 = self.root / "x86"
        self.arm = self.root / "arm"
        self.output = self.root / "release"
        _write_lane(self.x86, "rosetta-x86_64", "x86_64")
        _write_lane(self.arm, "native-arm64", "arm64")

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def _combine(self, *, required=("rosetta-x86_64", "native-arm64")):
        return combine(
            version=VERSION,
            inputs=[self.x86, self.arm],
            output=self.output,
            required=required,
        )

    def test_merges_both_lanes_into_one_release_provenance(self) -> None:
        provenance = self._combine()

        self.assertEqual(provenance["schemaVersion"], 2)
        self.assertEqual(provenance["releaseTag"], "v0.9.0")
        self.assertEqual(
            [runtime["target"] for runtime in provenance["runtimes"]],
            ["native-arm64", "rosetta-x86_64"],
        )
        notices = (self.output / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8")
        self.assertIn("===== native-arm64 (arm64) =====", notices)
        self.assertIn("===== rosetta-x86_64 (x86_64) =====", notices)

    def test_rejects_an_archive_that_differs_from_its_fragment(self) -> None:
        archive = self.x86 / runtime_archive_name(VERSION, "x86_64")
        archive.write_bytes(b"tampered")

        with self.assertRaisesRegex(CombineError, "SHA-256 does not match"):
            self._combine()

    def test_rejects_a_missing_required_target(self) -> None:
        with self.assertRaisesRegex(CombineError, "missing required targets"):
            self._combine(required=("rosetta-x86_64", "native-arm64", "other"))
