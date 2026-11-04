# SPDX-License-Identifier: MPL-2.0

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.shared.runtime import (
    LockError,
    _sha256_file,
    load_lock,
    monitored_sources,
    patches_for_stage,
    prepare,
    source_directory,
)


class RuntimeLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        patch = self.root / "patches" / "wine" / "audio" / "0001.patch"
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
                "runtimeCapabilities": "runtime-capabilities.json",
                "executables": ["Wine/bin/wine64"],
                "requiredFiles": ["Wine/lib/wine/x86_64-unix/winemac.so"],
            },
            "targets": {"rosetta-x86_64": {}},
            "patches": [
                {
                    "id": "wine-audio-default-output",
                    "component": "wine",
                    "family": "audio",
                    "path": "patches/wine/audio/0001.patch",
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
            "baseArtifact": None,
            "interface": {
                "runtimeCapabilities": "runtime-capabilities.json",
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

    def test_combined_stage_preserves_declared_patch_order(self) -> None:
        loaded = load_lock(self.write_lock(), repository_root=self.root)
        self.assertEqual(
            [p["id"] for p in patches_for_stage(loaded, "combined")],
            ["wine-audio-default-output"],
        )

    def test_family_stage_selects_only_that_family(self) -> None:
        hardware_cursor = dict(self.lock["patches"][0])
        hardware_cursor.update(
            id="wine-hardware-cursor-suppression",
            family="hardware-cursor",
        )
        self.lock["patches"].append(hardware_cursor)
        loaded = load_lock(self.write_lock(), repository_root=self.root)

        self.assertEqual(len(patches_for_stage(loaded, "audio")), 1)
        self.assertEqual(
            patches_for_stage(loaded, "hardware-cursor"), [hardware_cursor]
        )
        self.assertEqual(patches_for_stage(loaded, "ace"), [])

    def test_cef_family_stage_is_separate_from_cn_windowing(self) -> None:
        cef = dict(self.lock["patches"][0])
        cef.update(
            id="wine-cef-bilibili-stackbase",
            family="cef",
        )
        cn = dict(self.lock["patches"][0])
        cn.update(
            id="wine-cn-bilibili-layered-child",
            family="cn",
        )
        self.lock["patches"] = [cef, cn]
        loaded = load_lock(self.write_lock(), repository_root=self.root)

        self.assertEqual(patches_for_stage(loaded, "cef"), [cef])
        self.assertEqual(patches_for_stage(loaded, "cn"), [cn])

    def test_hashes_files_incrementally(self) -> None:
        path = self.root / "payload"
        path.write_bytes(b"abc")
        self.assertEqual(
            _sha256_file(path),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )

    def test_performance_stage_is_isolated_and_included_in_combined(self) -> None:
        performance = dict(self.lock["patches"][0])
        performance.update(
            id="example-performance",
            component="dxmt",
            family="performance",
        )
        self.lock["patches"].append(performance)
        loaded = load_lock(self.write_lock(), repository_root=self.root)

        self.assertEqual(patches_for_stage(loaded, "performance"), [performance])
        self.assertEqual(len(patches_for_stage(loaded, "audio")), 1)
        self.assertEqual(patches_for_stage(loaded, "combined"), self.lock["patches"])

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
        self.assertEqual(patches_for_stage(arm64_view, "combined"), [])

    def test_rejects_an_undeclared_target(self) -> None:
        with self.assertRaisesRegex(LockError, "unknown target"):
            load_lock(self.write_lock(), repository_root=self.root, target="riscv64")

    def test_rejects_a_default_target_that_is_not_declared(self) -> None:
        self.lock["defaultTarget"] = "native-arm64"

        with self.assertRaisesRegex(LockError, "defaultTarget"):
            load_lock(self.write_lock(), repository_root=self.root)

    def test_rejects_a_patch_naming_an_undeclared_target(self) -> None:
        self.lock["patches"][0]["targets"] = ["native-arm64"]

        with self.assertRaisesRegex(LockError, "undeclared target"):
            load_lock(self.write_lock(), repository_root=self.root)

    def test_rejects_a_patch_component_that_a_target_does_not_build(self) -> None:
        self.lock["patches"][0]["component"] = "fex"

        with self.assertRaisesRegex(LockError, "does not build"):
            load_lock(self.write_lock(), repository_root=self.root)

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

        self.assertEqual(
            source_directory("wine", "combined", default_view), "wine-combined"
        )
        self.assertEqual(
            source_directory("wine", "combined", arm64_view),
            "wine-native-arm64-combined",
        )

    def test_rejects_an_unknown_patch_to_skip(self) -> None:
        with self.assertRaisesRegex(LockError, "unknown patch to skip"):
            prepare("audio", self.root / "sources", skip_patches=("missing",))

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


if __name__ == "__main__":
    unittest.main()
