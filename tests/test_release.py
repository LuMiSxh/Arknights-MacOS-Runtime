# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import hashlib
import json
import re
import tarfile
import tempfile
import unittest
from pathlib import Path

from scripts.release.verify import (
    ReleaseValidationError,
    normalize_version,
    verify_release,
)


class ReleaseVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self._write_repository()
        self.archive = self.root / "runtime.tar.gz"
        self.archive.write_bytes(b"runtime")
        self.checksum = self.root / "runtime.tar.gz.sha256"
        self._write_checksum(self.archive, self.checksum)
        self.source_root = self.root / "sources"
        for name in ("wine-combined", "dxmt-combined"):
            path = self.source_root / name
            path.mkdir(parents=True)
            (path / "source.c").write_text("source\n", encoding="utf-8")
        self.component_inventory = self.root / "runtime-component-inventory.tsv"
        self.component_inventory.write_text(
            "component\trole\tsource\nWine\truntime\texample@commit\n",
            encoding="utf-8",
        )
        self.source_archive = self.root / "sources.tar.gz"
        with tarfile.open(self.source_archive, "w:gz") as archive:
            for name in ("wine-combined", "dxmt-combined"):
                archive.add(self.source_root / name, arcname=name)
            archive.add(
                self.component_inventory,
                arcname="runtime-component-inventory.tsv",
            )
        self.source_checksum = self.root / "sources.tar.gz.sha256"
        self._write_checksum(self.source_archive, self.source_checksum)
        self.validation_report = self.root / "validation.json"
        self.validation_report.write_text(
            json.dumps(
                {
                    "runtime": "/private/build/candidate/Libraries",
                    "deploymentTarget": "15.0",
                    "requiredArchitecturesChecked": 12,
                    "machoFilesChecked": 20,
                    "inheritedMachOAboveTarget": 0,
                    "releaseEligible": True,
                    "status": "valid",
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _write_repository(self) -> None:
        patch_definitions = (
            ("example-audio", "audio"),
            ("example-cursor", "cursor"),
            ("example-cn", "cn"),
        )
        patches = []
        for patch_id, family in patch_definitions:
            patch = self.root / f"patches/{patch_id}.patch"
            patch.parent.mkdir(parents=True, exist_ok=True)
            content = f"{patch_id}\n"
            patch.write_text(content, encoding="utf-8")
            patches.append(
                {
                    "id": patch_id,
                    "component": "wine" if family != "cursor" else "dxmt",
                    "family": family,
                    "path": str(patch.relative_to(self.root)),
                    "sha256": hashlib.sha256(content.encode()).hexdigest(),
                }
            )
        lock = {
            "schemaVersion": 2,
            "archiveSchemaVersion": 2,
            "deploymentTarget": "15.0",
            "sources": {
                "wine": {
                    "repository": "https://github.com/example/wine.git",
                    "commit": "a" * 40,
                },
                "dxmt": {
                    "repository": "https://github.com/example/dxmt.git",
                    "commit": "b" * 40,
                },
            },
            "baseArtifact": {
                "url": "https://github.com/example/runtime/releases/download/v1/Libraries.tar.gz",
                "sha256": "c" * 64,
                "recipe": {
                    "repository": "https://github.com/example/recipe.git",
                    "commit": "d" * 40,
                },
            },
            "baseProvenance": {
                "moltenvk": {
                    "repository": "https://github.com/example/moltenvk.git",
                    "commit": "e" * 40,
                },
                "gstreamer": {
                    "repository": "https://github.com/example/gstreamer.git",
                    "commit": "f" * 40,
                },
                "ffmpeg": {
                    "repository": "https://github.com/example/ffmpeg.git",
                    "commit": "0" * 40,
                },
                "wineGecko": {
                    "repository": "https://gitlab.winehq.org/wine/wine-gecko.git",
                    "commit": "1" * 40,
                },
            },
            "build": {
                "nixpkgs": {
                    "repository": "https://github.com/NixOS/nixpkgs.git",
                    "commit": "2" * 40,
                }
            },
            "patches": patches,
        }
        (self.root / "runtime.lock.json").write_text(json.dumps(lock), encoding="utf-8")
        for relative, content in {
            "LICENSE": "project license\n",
            "LICENSES/Wine-LGPL-2.1.txt": "wine license\n",
            "LICENSES/DXMT-LGPL-2.1.txt": "dxmt license\n",
            "docs/patch-registry.md": "example-audio example-cursor example-cn\n",
            "docs/legal/redistribution.md": "redistribution inventory\n",
            "LICENSES/runtime/Apache-2.0.txt": "apache license\n",
            "LICENSES/runtime/GPL-2.0.txt": "gpl2 license\n",
            "LICENSES/runtime/GPL-3.0.txt": "gpl3 license\n",
            "LICENSES/runtime/LGPL-2.1.txt": "lgpl21 license\n",
            "LICENSES/runtime/LGPL-3.0.txt": "lgpl3 license\n",
            "LICENSES/runtime/MIT-DXMT.txt": "mit license\n",
            "LICENSES/runtime/FDK-AAC.txt": "fdk notice\n",
        }.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    @staticmethod
    def _write_checksum(artifact: Path, checksum: Path) -> None:
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        checksum.write_text(f"{digest}  {artifact.name}\n", encoding="utf-8")

    def _verify(self) -> dict[str, Path]:
        return verify_release(
            repository_root=self.root,
            tag="v0.1.0",
            commit="3" * 40,
            archive=self.archive,
            checksum=self.checksum,
            source_root=self.source_root,
            source_archive=self.source_archive,
            source_checksum=self.source_checksum,
            validation_report=self.validation_report,
            output_directory=self.root / "release",
            component_inventory=self.component_inventory,
        )

    def test_writes_provenance_and_notices_after_all_gates_pass(self) -> None:
        outputs = self._verify()

        provenance = json.loads(outputs["provenance"].read_text(encoding="utf-8"))
        self.assertEqual(provenance["releaseTag"], "v0.1.0")
        self.assertEqual(provenance["sourceCommit"], "3" * 40)
        self.assertEqual(
            provenance["runtimeArchive"]["sha256"],
            hashlib.sha256(self.archive.read_bytes()).hexdigest(),
        )
        self.assertIn("wine license", outputs["notices"].read_text(encoding="utf-8"))
        self.assertIn("apache license", outputs["notices"].read_text(encoding="utf-8"))
        self.assertIn("fdk notice", outputs["notices"].read_text(encoding="utf-8"))
        self.assertIn(
            "redistribution inventory",
            outputs["notices"].read_text(encoding="utf-8"),
        )
        self.assertIn(
            "Wine\truntime\texample@commit",
            outputs["notices"].read_text(encoding="utf-8"),
        )

    def test_normalizes_a_semver_version_to_a_tag(self) -> None:
        self.assertEqual(normalize_version("0.5.0"), "v0.5.0")
        self.assertEqual(
            normalize_version("v1.2.3-rc.1+build.2"), "v1.2.3-rc.1+build.2"
        )

    def test_rejects_non_semver_versions(self) -> None:
        for value in ("", "01.2.3", "1.2", "1.2.3-01", "1.2.3+"):
            with self.subTest(value=value), self.assertRaises(ReleaseValidationError):
                normalize_version(value)

    def test_rejects_non_release_eligible_validation_report(self) -> None:
        report = json.loads(self.validation_report.read_text(encoding="utf-8"))
        report["releaseEligible"] = False
        report["status"] = "valid-canary"
        self.validation_report.write_text(json.dumps(report), encoding="utf-8")

        with self.assertRaisesRegex(ReleaseValidationError, "not release eligible"):
            self._verify()

    def test_rejects_a_release_lock_missing_a_patch_family(self) -> None:
        lock_path = self.root / "runtime.lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        lock["patches"] = [
            patch for patch in lock["patches"] if patch["family"] != "cn"
        ]
        lock_path.write_text(json.dumps(lock), encoding="utf-8")

        with self.assertRaisesRegex(ReleaseValidationError, "patch families"):
            self._verify()

    def test_rejects_checksum_that_names_another_artifact(self) -> None:
        self.checksum.write_text(
            f"{hashlib.sha256(self.archive.read_bytes()).hexdigest()}  other.tar.gz\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ReleaseValidationError, "names"):
            self._verify()

    def test_rejects_unsafe_source_archive_member(self) -> None:
        with tarfile.open(self.source_archive, "w:gz") as archive:
            source = tarfile.TarInfo("../escape")
            source.size = 0
            archive.addfile(source)
        self._write_checksum(self.source_archive, self.source_checksum)

        with self.assertRaisesRegex(ReleaseValidationError, "unsafe path"):
            self._verify()


class ReleaseWorkflowContractTests(unittest.TestCase):
    def test_workflow_is_manual_and_accepts_only_a_version(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[1] / ".github/workflows/release.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("version:", workflow)
        self.assertNotIn("\n      tag:", workflow)
        self.assertNotRegex(workflow, r"\n  push:")

    def test_workflow_creates_a_draft_at_the_built_sha(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[1] / ".github/workflows/release.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("ref: ${{ github.event.repository.default_branch }}", workflow)
        self.assertIn('gh release create "$RELEASE_TAG"', workflow)
        self.assertIn('-f sha="$BUILD_COMMIT"', workflow)
        self.assertIn("git/ref/tags/$RELEASE_TAG", workflow)
        self.assertIn("--verify-tag", workflow)
        self.assertNotIn('--target "$BUILD_COMMIT"', workflow)
        self.assertIn("--draft", workflow)
        self.assertIn("--latest=false", workflow)
        self.assertNotIn("git tag ", workflow)
        self.assertNotIn("git push ", workflow)
        self.assertGreaterEqual(workflow.count("git ls-remote"), 2)
        self.assertGreaterEqual(workflow.count("releases/tags/"), 2)

    def test_workflow_never_uses_the_overlay_builder_for_a_release(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[1] / ".github/workflows/release.yml"
        ).read_text(encoding="utf-8")

        self.assertNotIn("just build combined", workflow)
        self.assertNotIn("build-canary.sh", workflow)
        self.assertIn("just build-release", workflow)

    def test_workflow_exports_the_release_directory(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[1] / ".github/workflows/release.yml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "printf 'RELEASE_DIRECTORY=%s\\n' \"$RELEASE_DIRECTORY\"", workflow
        )

    def test_workflow_includes_the_legal_inventory_in_source_assets(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[1] / ".github/workflows/release.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("docs/legal LICENSE LICENSES", workflow)

    def test_workflow_uses_tagged_actions_and_minimal_write_scope(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[1] / ".github/workflows/release.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("permissions: {}", workflow)
        self.assertIn("contents: write", workflow)
        self.assertTrue(
            all(
                re.fullmatch(r"v[0-9A-Za-z.\-]+", version)
                for version in re.findall(r"uses: [^\s]+@(v[^\s]+)", workflow)
            )
        )


if __name__ == "__main__":
    unittest.main()
