# SPDX-License-Identifier: MPL-2.0


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
from tests.lock_fixture import patch_entry, synthetic_lock


class ReleaseVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self._write_repository()
        self.archive = self.root / "runtime.tar.xz"
        self._write_runtime_archive()
        self.checksum = self.root / "runtime.tar.xz.sha256"
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
        self.source_archive = self.root / "sources.tar.xz"
        self._write_source_archive()
        self.source_checksum = self.root / "sources.tar.xz.sha256"
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
        with tarfile.open(self.source_archive, "w:xz") as archive:
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
                patch_entry(
                    patch_id,
                    component,
                    number,
                    str(patch.relative_to(self.root)),
                    hashlib.sha256(content.encode()).hexdigest(),
                )
            )
        lock = synthetic_lock(patches)
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

    def _write_runtime_archive(self, *, omit: str | None = None) -> None:
        components = ("Wine", "DXMT", "MoltenVK")
        index = {
            "components": [
                {"name": name, "files": [f"{name}.txt"], "notice": None}
                for name in components
            ]
        }
        files = {
            "Runtime/Licenses/index.json": json.dumps(index).encode(),
            "Runtime/NOTICE.md": b"# Third-party notices\n",
            **{
                f"Runtime/Licenses/{name}.txt": b"license\n"
                for name in components
                if name != omit
            },
        }
        with tarfile.open(self.archive, "w:xz") as archive:
            root = tarfile.TarInfo("Runtime")
            root.type = tarfile.DIRTYPE
            archive.addfile(root)
            for name, data in files.items():
                member = tarfile.TarInfo(name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))

    @staticmethod
    def _write_checksum(artifact: Path, checksum: Path) -> None:
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        checksum.write_text(f"{digest}  {artifact.name}\n", encoding="utf-8")

    def _verify(self) -> dict[str, object]:
        return verify_release(
            repository_root=self.root,
            version="0.1.0",
            commit="3" * 40,
            archive=self.archive,
            checksum=self.checksum,
            source_root=self.source_root,
            source_archive=self.source_archive,
            source_checksum=self.source_checksum,
            validation_report=self.validation_report,
            component_inventory=self.component_inventory,
        )

    def test_returns_the_validation_record_after_all_gates_pass(self) -> None:
        validation = self._verify()

        self.assertTrue(validation["releaseEligible"])

    def test_rejects_a_runtime_archive_missing_a_listed_license_file(self) -> None:
        self._write_runtime_archive(omit="DXMT")
        self._write_checksum(self.archive, self.checksum)

        with self.assertRaisesRegex(ReleaseValidationError, "missing a license file"):
            self._verify()

    def test_normalizes_a_bare_semver_version(self) -> None:
        self.assertEqual(normalize_version("0.5.0"), "0.5.0")
        self.assertEqual(normalize_version("1.2.3-rc.1"), "1.2.3-rc.1")

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
            f"{hashlib.sha256(self.archive.read_bytes()).hexdigest()}  other.tar.xz\n",
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

    def test_rejects_unsafe_source_archive_member(self) -> None:
        with tarfile.open(self.source_archive, "w:xz") as archive:
            source = tarfile.TarInfo("../escape")
            source.size = 0
            archive.addfile(source)
        self._write_checksum(self.source_archive, self.source_checksum)

        with self.assertRaisesRegex(ReleaseValidationError, "unsafe path"):
            self._verify()


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/release.yml"


def _job(workflow: str, name: str) -> str:
    """Return the text of one top-level job."""

    match = re.search(
        rf"\n    {re.escape(name)}:\n(.*?)(?=\n    \S|\Z)", workflow, re.DOTALL
    )
    assert match is not None, name
    return match.group(1)


class ReleaseWorkflowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_release_requires_both_lanes_and_the_default_branch(self) -> None:
        plan = _job(self.workflow, "prepare")

        self.assertIn('"$TARGET" != both', plan)
        self.assertIn('"$REF_NAME" != "$DEFAULT_BRANCH"', plan)
        self.assertIn("--require rosetta-x86_64,native-arm64", self.workflow)

    def test_workflow_creates_a_draft_at_the_built_sha(self) -> None:
        self.assertIn('gh release create "$RELEASE_TAG"', self.workflow)
        self.assertIn('-f sha="$BUILD_COMMIT"', self.workflow)
        self.assertIn("BUILD_COMMIT: ${{ github.sha }}", self.workflow)
        self.assertIn("--verify-tag", self.workflow)
        self.assertNotIn('--target "$BUILD_COMMIT"', self.workflow)
        self.assertIn("--draft", self.workflow)
        self.assertIn("--latest=false", self.workflow)
        self.assertNotIn("git tag ", self.workflow)
        self.assertNotIn("git push ", self.workflow)

    def test_absence_is_probed_before_the_build_and_before_publishing(self) -> None:
        probe = 'release assert-absent --tag "$RELEASE_TAG"'
        self.assertIn(probe, _job(self.workflow, "prepare"))
        self.assertIn(probe, _job(self.workflow, "recheck"))
        self.assertIn("recheck", _job(self.workflow, "publish"))

    def test_release_channel_uses_the_release_gated_build(self) -> None:
        self.assertIn('just build rosetta-x86_64 "$VERSION" release', self.workflow)
        self.assertIn('just build native-arm64 "$VERSION" release', self.workflow)

    def test_only_publish_writes_and_it_never_checks_out_code(self) -> None:
        publish = _job(self.workflow, "publish")

        self.assertIn("contents: write", publish)
        self.assertIn("id-token: write", publish)
        self.assertIn("attestations: write", publish)
        self.assertIn("actions/attest-build-provenance@v", publish)
        self.assertNotIn("actions/checkout", publish)
        self.assertNotIn("just build", publish)
        self.assertEqual(self.workflow.count("contents: write"), 1)
        self.assertEqual(self.workflow.count("id-token: write"), 1)

    def test_lane_jobs_are_read_only_and_arm64_alone_uses_its_environment(
        self,
    ) -> None:
        for name in ("build-x86_64", "build-arm64"):
            job = _job(self.workflow, name)
            self.assertIn("contents: read", job)
            self.assertIn("persist-credentials: false", job)
        self.assertEqual(self.workflow.count("environment:"), 1)
        self.assertIn("environment: release-arm64", _job(self.workflow, "build-arm64"))
        self.assertEqual(self.workflow.count("secrets.ARM64_RUNTIME_CATALOG_URL"), 1)

    def test_workflow_uses_tagged_actions_and_no_inline_inputs(self) -> None:
        self.assertIn("permissions: {}", self.workflow)
        self.assertTrue(
            all(
                re.fullmatch(r"v[0-9A-Za-z.\-]+", version)
                for version in re.findall(r"uses: [^\s]+@(v[^\s]+)", self.workflow)
            )
        )
        for block in re.findall(
            r"run: \|\n(.*?)(?=\n            - |\n    \S|\Z)", self.workflow, re.DOTALL
        ):
            self.assertNotIn("${{", block)


def _write_external_fixture(root: Path) -> None:
    lock = synthetic_lock([])
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

    runtime_archive = root / "runtime.tar.xz"
    with tarfile.open(runtime_archive, "w:xz") as tar:
        add_dir(tar, "Runtime")
        add_dir(tar, "Runtime/Licenses")
        add_dir(tar, "Runtime/Licenses/runtime")
        for name in (
            "Wine-LGPL-2.1.txt",
            "DXMT-LGPL-2.1.txt",
            "runtime/MIT.txt",
            "runtime/Apache-2.0.txt",
        ):
            add_file(tar, f"Runtime/Licenses/{name}", b"license\n")
        add_file(tar, "Runtime/NOTICE.md", b"# Third-party notices\n")

    source_archive = root / "sources.tar.xz"
    with tarfile.open(source_archive, "w:xz") as tar:
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

    validation = verify_release(
        repository_root=root,
        version="0.9.0",
        commit="7" * 40,
        archive=root / "runtime.tar.xz",
        checksum=root / "runtime.tar.xz.sha256",
        source_root=root,
        source_archive=root / "sources.tar.xz",
        source_checksum=root / "sources.tar.xz.sha256",
        validation_report=root / "validation.json",
        component_inventory=root / "inventory.tsv",
        target="native-arm64",
    )

    assert validation["releaseEligible"] is False
    assert validation["builtExternally"] is True

    with tarfile.open(root / "runtime.tar.xz", "r:xz") as archive:
        names = {member.name for member in archive.getmembers() if member.isfile()}
    assert {
        "Runtime/NOTICE.md",
        "Runtime/Licenses/Wine-LGPL-2.1.txt",
        "Runtime/Licenses/DXMT-LGPL-2.1.txt",
        "Runtime/Licenses/runtime/MIT.txt",
        "Runtime/Licenses/runtime/Apache-2.0.txt",
    } <= names


if __name__ == "__main__":
    unittest.main()
