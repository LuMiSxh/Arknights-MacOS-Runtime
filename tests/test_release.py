# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import hashlib
import io
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
        self._write_runtime_archive()
        self.checksum = self.root / "runtime.tar.gz.sha256"
        self._write_checksum(self.archive, self.checksum)
        self.source_root = self.root / "sources"
        for name in ("wine", "dxmt"):
            path = self.source_root / name
            path.mkdir(parents=True)
            (path / "source.c").write_text("source\n", encoding="utf-8")
        self.component_inventory = self.root / "runtime-component-inventory.tsv"
        self.component_inventory.write_text(
            "component\trole\tsource\nWine\truntime\texample@commit\n",
            encoding="utf-8",
        )
        self.source_archive = self.root / "sources.tar.gz"
        self._write_source_archive()
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

    def _write_source_archive(
        self,
        *,
        omit: tuple[str, ...] = (),
    ) -> None:
        for name in ("scripts", "Justfile", "pyproject.toml", "uv.lock"):
            path = self.root / name
            if name == "scripts":
                path.mkdir(exist_ok=True)
                (path / "runtime.py").write_text("script\n", encoding="utf-8")
            else:
                path.write_text("build file\n", encoding="utf-8")
        members = {
            "wine": self.source_root / "wine",
            "dxmt": self.source_root / "dxmt",
            "runtime-component-inventory.tsv": self.component_inventory,
            "scripts": self.root / "scripts",
            "Justfile": self.root / "Justfile",
            "pyproject.toml": self.root / "pyproject.toml",
            "uv.lock": self.root / "uv.lock",
        }
        with tarfile.open(self.source_archive, "w:gz") as archive:
            for arcname, path in members.items():
                if arcname not in omit:
                    archive.add(path, arcname=arcname)

    def _write_repository(self) -> None:
        patch_definitions = [("wine", number) for number in range(3, 16)]
        patch_definitions.append(("dxmt", 1))
        patches = []
        for component, number in patch_definitions:
            patch_id = f"example-{component}-{number:04d}"
            patch = self.root / f"patches/{patch_id}.patch"
            patch.parent.mkdir(parents=True, exist_ok=True)
            content = f"{patch_id}\n"
            patch.write_text(content, encoding="utf-8")
            patches.append(
                {
                    "id": patch_id,
                    "component": component,
                    "number": number,
                    "gate": None,
                    "default": True,
                    "targets": ["rosetta-x86_64"],
                    "path": str(patch.relative_to(self.root)),
                    "sha256": hashlib.sha256(content.encode()).hexdigest(),
                }
            )
        lock = {
            "schemaVersion": 3,
            "archiveSchemaVersion": 2,
            "defaultTarget": "rosetta-x86_64",
            "targets": {"rosetta-x86_64": {"buildMode": "build"}},
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
            "interface": {},
            "features": {
                "hardwareCursor": True,
                "metalFXSpatialUpscaling": True,
                "nativeFullscreenSpace": True,
            },
            "patches": patches,
        }
        (self.root / "runtime.lock.json").write_text(json.dumps(lock), encoding="utf-8")
        for relative, content in {
            "LICENSE": "project license\n",
            "LICENSES/Wine-LGPL-2.1.txt": "wine license\n",
            "LICENSES/DXMT-LGPL-2.1.txt": "dxmt license\n",
            "docs/patch-registry.md": " ".join(patch["id"] for patch in patches) + "\n",
            "docs/legal/redistribution.md": "redistribution inventory\n",
            "LICENSES/runtime/Apache-2.0.txt": "apache license\n",
            "LICENSES/runtime/GPL-2.0.txt": "gpl2 license\n",
            "LICENSES/runtime/GPL-3.0.txt": "gpl3 license\n",
            "LICENSES/runtime/LGPL-2.1.txt": "lgpl21 license\n",
            "LICENSES/runtime/LGPL-3.0.txt": "lgpl3 license\n",
            "LICENSES/runtime/MIT-DXMT.txt": "mit license\n",
        }.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def _write_runtime_archive(self) -> None:
        with tarfile.open(self.archive, "w:gz") as archive:
            root = tarfile.TarInfo("Libraries")
            root.type = tarfile.DIRTYPE
            archive.addfile(root)

    @staticmethod
    def _write_checksum(artifact: Path, checksum: Path) -> None:
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        checksum.write_text(f"{digest}  {artifact.name}\n", encoding="utf-8")

    def _verify(self, *, build_toolchain: Path | None = None) -> dict[str, Path]:
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
            build_toolchain=build_toolchain,
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
        self.assertIn("gpl3 license", outputs["notices"].read_text(encoding="utf-8"))
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

    def test_rejects_a_release_lock_missing_a_required_patch(self) -> None:
        lock_path = self.root / "runtime.lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        for missing in (("wine", 3), ("wine", 15), ("dxmt", 1)):
            with self.subTest(missing=missing):
                incomplete_lock = dict(lock)
                incomplete_lock["patches"] = [
                    patch
                    for patch in lock["patches"]
                    if (patch["component"], patch["number"]) != missing
                ]
                lock_path.write_text(json.dumps(incomplete_lock), encoding="utf-8")

                with self.assertRaisesRegex(ReleaseValidationError, "missing patches"):
                    self._verify()

    def test_rejects_checksum_that_names_another_artifact(self) -> None:
        self.checksum.write_text(
            f"{hashlib.sha256(self.archive.read_bytes()).hexdigest()}  other.tar.gz\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ReleaseValidationError, "names"):
            self._verify()

    def test_rejects_a_missing_or_symlinked_source_checkout(self) -> None:
        (self.source_root / "wine" / "source.c").unlink()
        (self.source_root / "wine").rmdir()
        with self.assertRaisesRegex(ReleaseValidationError, "missing source checkout"):
            self._verify()

        real_root = self.root / "real-sources"
        self.source_root.rename(real_root)
        self.source_root.symlink_to(real_root)
        with self.assertRaisesRegex(ReleaseValidationError, "not a directory"):
            self._verify()

    def test_rejects_a_source_archive_missing_a_build_member(self) -> None:
        for member in ("scripts", "Justfile", "pyproject.toml", "uv.lock"):
            with self.subTest(member=member):
                self._write_source_archive(omit=(member,))
                self._write_checksum(self.source_archive, self.source_checksum)

                with self.assertRaisesRegex(
                    ReleaseValidationError,
                    f"corresponding-source archive is missing.*{member}",
                ):
                    self._verify()

    def test_records_the_build_toolchain_in_provenance(self) -> None:
        toolchain = self.root / "build-toolchain.json"
        toolchain.write_text(
            json.dumps({"brew": {"meson": "1.9.0"}, "sdkVersion": "15.5"}),
            encoding="utf-8",
        )

        outputs = self._verify(build_toolchain=toolchain)

        provenance = json.loads(outputs["provenance"].read_text(encoding="utf-8"))
        self.assertEqual(provenance["buildToolchain"]["sdkVersion"], "15.5")

    def test_rejects_a_build_toolchain_report_that_is_not_an_object(self) -> None:
        toolchain = self.root / "build-toolchain.json"
        toolchain.write_text("[]", encoding="utf-8")

        with self.assertRaisesRegex(ReleaseValidationError, "JSON object"):
            self._verify(build_toolchain=toolchain)

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
        self.assertGreaterEqual(workflow.count("git ls-remote"), 1)
        self.assertGreaterEqual(workflow.count("git/ref/tags/"), 2)
        self.assertGreaterEqual(workflow.count("releases/tags/"), 2)

    def test_workflow_never_uses_the_overlay_builder_for_a_release(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[1] / ".github/workflows/release.yml"
        ).read_text(encoding="utf-8")

        self.assertNotIn("just build\n", workflow)
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

        self.assertIn(
            "docs/legal LICENSE LICENSES scripts Justfile pyproject.toml uv.lock",
            workflow,
        )

    def test_workflow_separates_the_read_only_build_from_the_publish_job(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[1] / ".github/workflows/release.yml"
        ).read_text(encoding="utf-8")
        build, publish = workflow.split("\n    publish:\n")

        self.assertIn("contents: read", build)
        self.assertNotIn("contents: write", build)
        self.assertNotIn("id-token", build)
        self.assertIn("persist-credentials: false", build)
        self.assertIn("contents: write", publish)
        self.assertIn("id-token: write", publish)
        self.assertIn("attestations: write", publish)
        self.assertIn("actions/attest-build-provenance@v", publish)
        self.assertNotIn("actions/checkout", publish)
        self.assertNotIn("just build-release", publish)

    def test_workflow_uses_tagged_actions_and_minimal_write_scope(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[1] / ".github/workflows/release.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("permissions: {}", workflow)
        self.assertEqual(workflow.count("contents: write"), 1)
        self.assertTrue(
            all(
                re.fullmatch(r"v[0-9A-Za-z.\-]+", version)
                for version in re.findall(r"uses: [^\s]+@(v[^\s]+)", workflow)
            )
        )


def _write_external_fixture(root: Path) -> None:
    lock = {
        "schemaVersion": 3,
        "archiveSchemaVersion": 2,
        "defaultTarget": "rosetta-x86_64",
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
            "wineGecko": {
                "repository": "https://gitlab.winehq.org/wine/wine-gecko.git",
                "commit": "f" * 40,
            },
        },
        "build": {
            "nixpkgs": {
                "repository": "https://github.com/NixOS/nixpkgs.git",
                "commit": "1" * 40,
            }
        },
        "interface": {},
        "features": {
            "hardwareCursor": True,
            "metalFXSpatialUpscaling": True,
            "nativeFullscreenSpace": True,
        },
        "targets": {
            "rosetta-x86_64": {"buildMode": "build"},
            "native-arm64": {
                "buildMode": "external",
                "deploymentTarget": "26.0",
                "sources": {
                    "wine": {
                        "repository": "https://gitlab.winehq.org/wine/wine.git",
                        "commit": "2" * 40,
                        "version": "11.18",
                    },
                    "fex": {
                        "repository": "https://github.com/FEX-Emu/FEX.git",
                        "commit": "3" * 40,
                        "version": "2610",
                    },
                    "dxmt": {
                        "repository": "https://github.com/3Shain/dxmt.git",
                        "commit": "4" * 40,
                        "version": "0.80",
                    },
                },
                "artifact": {
                    "catalog": "wine",
                    "release": "wine-11-18-arm64-v5",
                    "sha256": "5" * 64,
                },
                "baseArtifact": None,
                "interface": {
                    "wineDirectory": "Wine",
                    "dxmtDirectory": "DXMT",
                    "minimumMacOS": "26.0",
                    "executables": [
                        "Wine/bin/Arknights",
                        "Wine/bin/wine64",
                        "Wine/bin/wineserver",
                    ],
                    "requiredFiles": ["Wine/lib/wine/aarch64-unix/winemac.so"],
                },
                "features": {
                    "hardwareCursor": True,
                    "metalFXSpatialUpscaling": True,
                    "nativeFullscreenSpace": True,
                },
            },
        },
        "patches": [],
    }
    (root / "runtime.lock.json").write_text(json.dumps(lock), encoding="utf-8")
    (root / "wine-build-new").mkdir(parents=True)
    (root / "wine-build-new" / "source.c").write_text("source\n", encoding="utf-8")
    for relative, content in {
        "LICENSE": "project license\n",
        "LICENSES/Wine-LGPL-2.1.txt": "wine license\n",
        "LICENSES/DXMT-LGPL-2.1.txt": "dxmt license\n",
        "LICENSES/runtime/Apache-2.0.txt": "apache license\n",
        "LICENSES/runtime/GPL-2.0.txt": "gpl2 license\n",
        "LICENSES/runtime/GPL-3.0.txt": "gpl3 license\n",
        "LICENSES/runtime/LGPL-2.1.txt": "lgpl21 license\n",
        "LICENSES/runtime/LGPL-3.0.txt": "lgpl3 license\n",
        "LICENSES/runtime/MIT-DXMT.txt": "mit license\n",
        "LICENSES/runtime/MIT.txt": "mit license\n",
        "docs/patch-registry.md": "patch registry\n",
        "docs/legal/redistribution.md": "redistribution inventory\n",
    }.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _write_external_archives(root: Path) -> None:
    def add_file(tar: tarfile.TarFile, name: str, data: bytes) -> None:
        member = tarfile.TarInfo(name)
        member.size = len(data)
        tar.addfile(member, io.BytesIO(data))

    def add_dir(tar: tarfile.TarFile, name: str) -> None:
        member = tarfile.TarInfo(name)
        member.type = tarfile.DIRTYPE
        tar.addfile(member)

    runtime_archive = root / "runtime.tar.gz"
    with tarfile.open(runtime_archive, "w:gz") as tar:
        add_dir(tar, "Libraries")
        add_dir(tar, "Licenses")
        add_dir(tar, "Licenses/runtime")
        for name in (
            "Wine-LGPL-2.1.txt",
            "DXMT-LGPL-2.1.txt",
            "runtime/MIT.txt",
            "runtime/Apache-2.0.txt",
        ):
            add_file(tar, f"Licenses/{name}", b"license\n")
        add_file(tar, "NOTICE.md", b"# Third-party notices\n")

    source_archive = root / "sources.tar.gz"
    with tarfile.open(source_archive, "w:gz") as tar:
        add_dir(tar, "wine-build-new")
        add_file(tar, "wine-build-new/source.c", b"source\n")
        add_file(tar, "runtime.lock.json", (root / "runtime.lock.json").read_bytes())
        add_dir(tar, "docs")
        add_dir(tar, "docs/arm")
        add_file(tar, "docs/arm/provenance.md", b"provenance\n")

    for artifact in (runtime_archive, source_archive):
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        (root / f"{artifact.name}.sha256").write_text(
            f"{digest}  {artifact.name}\n", encoding="utf-8"
        )


def test_external_target_accepts_the_minimal_notice_set(tmp_path):
    root = tmp_path / "external"
    root.mkdir()
    _write_external_fixture(root)
    _write_external_archives(root)
    (root / "validation.json").write_text(
        json.dumps(
            {
                "runtime": "/private/build/external/Libraries",
                "deploymentTarget": "26.0",
                "inheritedMachOAboveTarget": 0,
                "releaseEligible": True,
                "status": "valid",
            }
        ),
        encoding="utf-8",
    )

    outputs = verify_release(
        repository_root=root,
        tag="v0.9.0+arm",
        commit="7" * 40,
        archive=root / "runtime.tar.gz",
        checksum=root / "runtime.tar.gz.sha256",
        source_root=root,
        source_archive=root / "sources.tar.gz",
        source_checksum=root / "sources.tar.gz.sha256",
        validation_report=root / "validation.json",
        output_directory=root / "release",
        target="native-arm64",
    )

    provenance = json.loads(outputs["provenance"].read_text(encoding="utf-8"))
    assert provenance["validation"]["releaseEligible"] is False
    assert provenance["validation"]["builtExternally"] is True

    with tarfile.open(root / "runtime.tar.gz", "r:gz") as archive:
        names = {member.name for member in archive.getmembers() if member.isfile()}
    assert {
        "NOTICE.md",
        "Licenses/Wine-LGPL-2.1.txt",
        "Licenses/DXMT-LGPL-2.1.txt",
        "Licenses/runtime/MIT.txt",
        "Licenses/runtime/Apache-2.0.txt",
    } <= names


if __name__ == "__main__":
    unittest.main()
