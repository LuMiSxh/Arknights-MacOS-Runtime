# SPDX-License-Identifier: MPL-2.0

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.runtime import (
    LockError,
    load_lock,
    prepare,
)


class RuntimeLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        patch = self.root / "patches" / "wine" / "0001.patch"
        patch.parent.mkdir(parents=True)
        patch.write_text("example patch\n", encoding="utf-8")
        self.lock = {
            "schemaVersion": 3,
            "archiveSchemaVersion": 2,
            "defaultTarget": "rosetta-x86_64",
            "deploymentTarget": "15.0",
            "sources": {
                "wine": {
                    "repository": "https://github.com/dappermint/winecx.git",
                    "commit": "7dbc5b5322a6ef3fb04bdc643c64b188fd641149",
                },
                "dxmt": {
                    "repository": "https://github.com/3Shain/dxmt.git",
                    "commit": "19e24ee068a44a747e556965730482038c5bb068",
                },
            },
            "baseArtifact": {
                "url": "https://github.com/example/runtime/releases/download/v1/Libraries.tar.gz",
                "sha256": "a" * 64,
                "recipe": {
                    "repository": "https://github.com/example/recipe.git",
                    "commit": "b" * 40,
                },
            },
            "baseProvenance": {
                "moltenvk": {
                    "repository": "https://github.com/KhronosGroup/MoltenVK.git",
                    "commit": "c" * 40,
                },
                "wineGecko": {
                    "repository": "https://gitlab.winehq.org/wine/wine-gecko.git",
                    "commit": "f" * 40,
                },
            },
            "build": {
                "nixpkgs": {
                    "repository": "https://github.com/NixOS/nixpkgs.git",
                    "commit": "a" * 40,
                }
            },
            "interface": {
                "executables": ["Wine/bin/wine64"],
                "requiredFiles": ["Wine/lib/wine/x86_64-unix/winemac.so"],
            },
            "features": {
                "hardwareCursor": True,
                "metalFXSpatialUpscaling": True,
                "nativeFullscreenSpace": True,
            },
            "targets": {"rosetta-x86_64": {"buildMode": "build"}},
            "patches": [
                {
                    "id": "wine-audio-default-output",
                    "component": "wine",
                    "number": 12,
                    "gate": "LMISXH_AKMOCL_AUDIO",
                    "default": True,
                    "targets": ["rosetta-x86_64"],
                    "path": "patches/wine/0001.patch",
                    "sha256": hashlib.sha256(b"example patch\n").hexdigest(),
                }
            ],
        }

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_lock(self) -> Path:
        path = self.root / "runtime.lock.json"
        path.write_text(json.dumps(self.lock), encoding="utf-8")
        return path

    def test_rejects_a_patch_path_outside_the_repository(self) -> None:
        self.lock["patches"][0]["path"] = "../escape.patch"
        with self.assertRaisesRegex(LockError, "repository-relative"):
            load_lock(self.write_lock(), repository_root=self.root)

    def test_rejects_a_patch_hash_mismatch(self) -> None:
        self.lock["patches"][0]["sha256"] = "b" * 64
        with self.assertRaisesRegex(LockError, "hash mismatch"):
            load_lock(self.write_lock(), repository_root=self.root)

    def test_prepare_applies_the_whole_patch_list_in_lock_order(self) -> None:
        def entry(patch_id: str, component: str, path: str) -> dict[str, str]:
            return {"id": patch_id, "component": component, "path": path}

        view = {
            "target": "rosetta-x86_64",
            "defaultTarget": "rosetta-x86_64",
            "buildMode": "build",
            "sources": {
                "wine": {"repository": "https://example.invalid/wine", "commit": "1"},
                "dxmt": {"repository": "https://example.invalid/dxmt", "commit": "2"},
            },
            "patches": [
                entry("a", "wine", "patches/wine/0003-first.patch"),
                entry("b", "dxmt", "patches/dxmt/0001-third.patch"),
                entry("c", "wine", "patches/wine/0004-second.patch"),
            ],
        }
        applied: list[str] = []

        def record(*command: str, cwd: Path | None = None) -> None:
            if command[:2] == ("git", "apply") and command[2] != "--check":
                applied.append(Path(command[2]).name)

        with (
            mock.patch("scripts.runtime.load_lock", return_value=view),
            mock.patch("scripts.runtime._run", side_effect=record),
        ):
            prepare(self.root / "sources")

        self.assertEqual(
            applied,
            ["0001-third.patch", "0003-first.patch", "0004-second.patch"],
        )

    def test_rejects_an_undeclared_target(self) -> None:
        with self.assertRaisesRegex(LockError, "unknown target"):
            load_lock(self.write_lock(), repository_root=self.root, target="riscv64")

    def test_rejects_a_patch_naming_an_undeclared_target(self) -> None:
        self.lock["patches"][0]["targets"] = ["native-arm64"]

        with self.assertRaisesRegex(LockError, "undeclared target"):
            load_lock(self.write_lock(), repository_root=self.root)

    def test_rejects_a_malformed_patch_schema_field(self) -> None:
        cases = {
            "number": (0, "number must be a positive integer"),
            "gate": (7, "gate must be a string or null"),
            "default": ("yes", "default must be a boolean"),
        }
        for field, (value, message) in cases.items():
            with self.subTest(field=field):
                lock = copy.deepcopy(self.lock)
                lock["patches"][0][field] = value
                path = self.root / f"{field}.lock.json"
                path.write_text(json.dumps(lock), encoding="utf-8")

                with self.assertRaisesRegex(LockError, message):
                    load_lock(path, repository_root=self.root)

    def test_rejects_unknown_target_keys(self) -> None:
        self.lock["targets"]["rosetta-x86_64"] = {"sorce": {}}

        with self.assertRaisesRegex(LockError, "unknown keys"):
            load_lock(self.write_lock(), repository_root=self.root)

    def test_rejects_an_interface_path_that_leaves_the_runtime(self) -> None:
        self.lock["interface"]["executables"] = ["../escape"]

        with self.assertRaisesRegex(LockError, "runtime-relative"):
            load_lock(self.write_lock(), repository_root=self.root)


if __name__ == "__main__":
    unittest.main()
