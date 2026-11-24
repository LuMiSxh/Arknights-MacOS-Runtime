# SPDX-License-Identifier: MPL-2.0

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.lock.model import ROOT, LockError, load_lock
from scripts.lock.patches import export_wine_build_new
from scripts.lock.sources import prepare
from tests.lock_fixture import DEFAULT_LANE, patch_entry, synthetic_lock


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class RuntimeLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        path = "patches/wine/0001.patch"
        self.write_patch(path, "example patch\n")
        self.document = synthetic_lock(
            [patch_entry("wine-12", "wine", 12, path, _digest("example patch\n"))]
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_patch(self, relative: str, text: str) -> str:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return _digest(text)

    def load(self, document: dict | None = None):
        path = self.root / "runtime.lock.json"
        path.write_text(json.dumps(document or self.document), encoding="utf-8")
        return load_lock(path, repository_root=self.root)

    def test_rejects_a_patch_path_outside_the_repository(self) -> None:
        self.document["patches"][0]["files"][DEFAULT_LANE]["path"] = "../escape.patch"
        with self.assertRaisesRegex(LockError, "repository-relative"):
            self.load()

    def test_rejects_a_patch_hash_mismatch(self) -> None:
        self.document["patches"][0]["files"][DEFAULT_LANE]["sha256"] = "b" * 64
        with self.assertRaisesRegex(LockError, "hash mismatch"):
            self.load()

    def test_prepare_applies_the_whole_patch_list_in_lock_order(self) -> None:
        entries = [
            ("wine", 3, "patches/wine/0003-first.patch"),
            ("dxmt", 1, "patches/dxmt/0001-third.patch"),
            ("wine", 4, "patches/wine/0004-second.patch"),
        ]
        self.document["patches"] = [
            patch_entry(
                f"{component}-{number}",
                component,
                number,
                path,
                self.write_patch(path, f"{path}\n"),
            )
            for component, number, path in entries
        ]
        applied: list[str] = []

        def record(*command: str, cwd: Path | None = None) -> None:
            if command[:2] == ("git", "apply") and command[2] != "--check":
                applied.append(Path(command[2]).name)

        with (
            mock.patch("scripts.lock.sources.load_lock", return_value=self.load()),
            mock.patch("scripts.lock.sources._run", side_effect=record),
        ):
            prepare(self.root / "sources")

        self.assertEqual(
            applied,
            ["0001-third.patch", "0003-first.patch", "0004-second.patch"],
        )

    def test_rejects_an_undeclared_lane(self) -> None:
        with self.assertRaisesRegex(LockError, "unknown lane 'riscv64'"):
            self.load().lane("riscv64")

    def test_rejects_a_malformed_patch_schema_field(self) -> None:
        cases = {
            "number": (0, "number must be a positive integer"),
            "gate": (7, "gate must be a string or null"),
            "default": ("yes", "default must be a boolean"),
        }
        for field, (value, message) in cases.items():
            with self.subTest(field=field):
                document = copy.deepcopy(self.document)
                document["patches"][0][field] = value

                with self.assertRaisesRegex(LockError, message):
                    self.load(document)

    def test_rejects_unknown_lane_keys(self) -> None:
        self.document["lanes"][DEFAULT_LANE]["sorce"] = {}

        with self.assertRaisesRegex(LockError, "unknown keys: sorce"):
            self.load()

    def test_rejects_an_interface_path_that_leaves_the_runtime(self) -> None:
        self.document["lanes"][DEFAULT_LANE]["interface"]["executables"] = ["../escape"]

        with self.assertRaisesRegex(LockError, "runtime-relative"):
            self.load()

    def test_rejects_an_invalid_lock_with_its_exact_message(self) -> None:
        def unknown_lane(document: dict) -> None:
            document["patches"][0]["files"]["riscv64"] = {
                "path": "patches/wine/0001.patch",
                "sha256": _digest("example patch\n"),
            }

        def duplicate_number(document: dict) -> None:
            document["patches"].append(
                patch_entry(
                    "wine-12-copy",
                    "wine",
                    12,
                    "patches/wine/0001.patch",
                    _digest("example patch\n"),
                )
            )

        def missing_executables(document: dict) -> None:
            del document["lanes"][DEFAULT_LANE]["interface"]["executables"]

        cases = {
            "unknown lane in a patch file": (
                unknown_lane,
                "patch wine-12 names an undeclared lane: riscv64",
            ),
            "duplicate patch number": (
                duplicate_number,
                "duplicate wine patch number: 12",
            ),
            "missing interface field": (
                missing_executables,
                "lanes.rosetta-x86_64.interface is missing executables",
            ),
        }
        for name, (mutate, message) in cases.items():
            with self.subTest(name):
                document = copy.deepcopy(self.document)
                mutate(document)

                with self.assertRaises(LockError) as caught:
                    self.load(document)
                self.assertEqual(str(caught.exception), message)


class ExportTests(unittest.TestCase):
    def test_export_matches_the_committed_wine_build_new_lock(self) -> None:
        committed = (ROOT / "wine-build-new" / "lock.json").read_text(encoding="utf-8")

        self.assertEqual(export_wine_build_new(load_lock()), committed)


if __name__ == "__main__":
    unittest.main()
