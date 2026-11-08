# SPDX-License-Identifier: MPL-2.0

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.build_common import sha256
from scripts.runtime import (
    LockError,
    load_lock,
    monitored_sources,
    prepare,
    source_directory,
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

    def add_arm64_target(self) -> None:
        self.lock["targets"]["native-arm64"] = {
            "buildMode": "external",
            "deploymentTarget": "26.0",
            "sources": {
                "wine": {
                    "repository": "https://github.com/dappermint/winecx.git",
                    "commit": "c" * 40,
                },
                "dxmt": {
                    "repository": "https://github.com/3Shain/dxmt.git",
                    "commit": "d" * 40,
                },
                "fex": {
                    "repository": "https://github.com/dappermint/FEX.git",
                    "commit": "e" * 40,
                },
            },
            "artifact": {
                "catalog": "wine",
                "release": "wine-arm64",
                "sha256": "a" * 64,
            },
            "baseArtifact": None,
            "interface": {
                "executables": ["Wine/bin/wine64"],
            },
        }

    def test_accepts_a_pinned_lock_with_matching_patch_hash(self) -> None:
        loaded = load_lock(self.write_lock(), repository_root=self.root)
        self.assertEqual(loaded["deploymentTarget"], "15.0")

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

    def test_hashes_files_incrementally(self) -> None:
        path = self.root / "payload"
        path.write_bytes(b"abc")
        self.assertEqual(
            sha256(path),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )

    def test_repository_lock_requires_the_launcher_alias(self) -> None:
        root = Path(__file__).resolve().parents[1]
        lock = load_lock(root / "runtime.lock.json", repository_root=root)

        self.assertIn("Wine/bin/Arknights", lock["interface"]["executables"])

    def test_exposes_every_monitored_source_without_duplicate_commit_fields(
        self,
    ) -> None:
        loaded = load_lock(self.write_lock(), repository_root=self.root)

        pins = monitored_sources(loaded)

        self.assertEqual(
            [pin.name for pin in pins],
            [
                "wine",
                "dxmt",
                "buildRecipe",
                "moltenvk",
                "wineGecko",
                "nixpkgs",
            ],
        )
        self.assertEqual(pins[2].commit, "b" * 40)
        self.assertEqual(
            pins[4].repository,
            "https://gitlab.winehq.org/wine/wine-gecko.git",
        )

    def test_default_target_resolves_the_top_level_pins(self) -> None:
        loaded = load_lock(self.write_lock(), repository_root=self.root)

        self.assertEqual(loaded["target"], "rosetta-x86_64")
        self.assertEqual(loaded["sources"], self.lock["sources"])
        self.assertEqual(loaded["patches"], self.lock["patches"])

    def test_target_entry_replaces_the_whole_pinned_source_set(self) -> None:
        self.add_arm64_target()
        loaded = load_lock(
            self.write_lock(), repository_root=self.root, target="native-arm64"
        )

        self.assertEqual(loaded["target"], "native-arm64")
        self.assertEqual(sorted(loaded["sources"]), ["dxmt", "fex", "wine"])
        self.assertEqual(loaded["sources"]["wine"]["commit"], "c" * 40)
        self.assertIsNone(loaded["baseArtifact"])
        self.assertEqual(
            [pin.name for pin in monitored_sources(loaded)],
            ["wine", "dxmt", "fex", "nixpkgs"],
        )

    def test_patch_target_list_limits_the_patch_to_that_target(self) -> None:
        self.add_arm64_target()
        self.lock["patches"][0]["targets"] = ["rosetta-x86_64"]
        default_view = load_lock(self.write_lock(), repository_root=self.root)
        arm64_view = load_lock(
            self.write_lock(), repository_root=self.root, target="native-arm64"
        )

        self.assertEqual(
            [patch["id"] for patch in default_view["patches"]],
            ["wine-audio-default-output"],
        )
        self.assertEqual(arm64_view["patches"], [])

    def test_rejects_an_undeclared_target(self) -> None:
        with self.assertRaisesRegex(LockError, "unknown target"):
            load_lock(self.write_lock(), repository_root=self.root, target="riscv64")

    def test_rejects_a_default_target_that_is_not_declared(self) -> None:
        self.lock["defaultTarget"] = "native-arm64"

        with self.assertRaisesRegex(LockError, "defaultTarget"):
            load_lock(self.write_lock(), repository_root=self.root)

    def test_rejects_an_unknown_external_target_key(self) -> None:
        self.add_arm64_target()
        self.lock["targets"]["native-arm64"]["dxmtArtifact"] = {
            "catalog": "dxmt",
            "release": "dxmt-arm64",
            "sha256": "b" * 64,
        }

        with self.assertRaisesRegex(LockError, "unknown keys"):
            load_lock(
                self.write_lock(),
                repository_root=self.root,
                target="native-arm64",
            )

    def test_rejects_a_patch_naming_an_undeclared_target(self) -> None:
        self.lock["patches"][0]["targets"] = ["native-arm64"]

        with self.assertRaisesRegex(LockError, "undeclared target"):
            load_lock(self.write_lock(), repository_root=self.root)

    def test_rejects_a_patch_component_that_a_target_does_not_build(self) -> None:
        self.lock["patches"][0]["component"] = "fex"

        with self.assertRaisesRegex(LockError, "does not build"):
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

    def test_source_directories_distinguish_the_non_default_target(self) -> None:
        self.add_arm64_target()
        default_view = load_lock(self.write_lock(), repository_root=self.root)
        arm64_view = load_lock(
            self.write_lock(), repository_root=self.root, target="native-arm64"
        )

        self.assertEqual(source_directory("wine", default_view), "wine")
        self.assertEqual(source_directory("wine", arm64_view), "wine-native-arm64")

    def test_rejects_an_unknown_patch_to_skip(self) -> None:
        with self.assertRaisesRegex(LockError, "unknown patch to skip"):
            prepare(self.root / "sources", skip_patches=("missing",))

    def test_repository_lock_declares_the_native_arm64_target(self) -> None:
        root = Path(__file__).resolve().parents[1]
        lock = load_lock(
            root / "runtime.lock.json", repository_root=root, target="native-arm64"
        )

        self.assertEqual(lock["defaultTarget"], "rosetta-x86_64")
        self.assertEqual(sorted(lock["sources"]), ["dxmt", "fex", "wine"])
        self.assertIsNone(lock["baseArtifact"])
        self.assertTrue(
            all(
                "aarch64-unix" in path or "aarch64-windows" in path or "DXMT/" in path
                for path in lock["interface"]["requiredFiles"]
            )
        )
        self.assertNotIn(
            "wine-ace-rosetta-workarounds",
            [patch["id"] for patch in lock["patches"]],
        )

    def test_native_arm64_is_an_external_target(self) -> None:
        root = Path(__file__).resolve().parents[1]
        lock = load_lock(
            root / "runtime.lock.json", repository_root=root, target="native-arm64"
        )

        self.assertEqual(lock["buildMode"], "external")
        self.assertEqual(lock["deploymentTarget"], "26.0")
        self.assertEqual(lock["artifact"]["release"], "wine-11-18-arm64-v5")
        self.assertEqual(
            lock["artifact"]["sha256"],
            "3008b2d45cbe1653ebdd4a0704de790ecc5668a580a84b3db42140fd5c1af31b",
        )
        self.assertNotIn("dxmtArtifact", lock)
        self.assertEqual(
            lock["sources"]["dxmt"]["commit"],
            "647b0020ba5764e5593b12407afd76964fa11e20",
        )
        self.assertEqual(lock["patches"], [])

    def test_prepare_refuses_an_external_target(self) -> None:
        with self.assertRaisesRegex(LockError, "external"):
            prepare(target="native-arm64")


if __name__ == "__main__":
    unittest.main()
