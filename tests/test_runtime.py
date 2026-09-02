# SPDX-License-Identifier: MPL-2.0

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.runtime import (
    LockError,
    _sha256_file,
    load_lock,
    monitored_sources,
    patches_for_stage,
)


class RuntimeLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        patch = self.root / "patches" / "wine" / "audio" / "0001.patch"
        patch.parent.mkdir(parents=True)
        patch.write_text("example patch\n", encoding="utf-8")
        self.lock = {
            "schemaVersion": 2,
            "archiveSchemaVersion": 2,
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
                "gstreamer": {
                    "repository": "https://github.com/GStreamer/gstreamer.git",
                    "commit": "d" * 40,
                },
                "ffmpeg": {
                    "repository": "https://github.com/FFmpeg/FFmpeg.git",
                    "commit": "e" * 40,
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
        loaded = load_lock(self.write_lock(), repository_root=self.root)
        self.assertEqual(len(patches_for_stage(loaded, "audio")), 1)
        self.assertEqual(patches_for_stage(loaded, "cursor"), [])

    def test_hashes_files_incrementally(self) -> None:
        path = self.root / "payload"
        path.write_bytes(b"abc")
        self.assertEqual(
            _sha256_file(path),
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
                "gstreamer",
                "ffmpeg",
                "wineGecko",
                "nixpkgs",
            ],
        )
        self.assertEqual(pins[2].commit, "b" * 40)
        self.assertEqual(
            pins[6].repository,
            "https://gitlab.winehq.org/wine/wine-gecko.git",
        )


if __name__ == "__main__":
    unittest.main()
