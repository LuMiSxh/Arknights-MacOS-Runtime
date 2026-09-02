#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Verify and describe the immutable inputs of a runtime release."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if __package__:
    from ..runtime import LockError, _sha256_file, load_lock
else:
    if str(REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(REPOSITORY_ROOT))
    from scripts.runtime import LockError, _sha256_file, load_lock


SEMVER_CORE_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
IDENTIFIER_PATTERN = re.compile(r"^[0-9A-Za-z-]+$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
NOTICE_FILES = (
    "LICENSE",
    "LICENSES/Wine-LGPL-2.1.txt",
    "LICENSES/DXMT-LGPL-2.1.txt",
    "docs/patch-registry.md",
    "docs/legal/redistribution.md",
    "LICENSES/runtime/Apache-2.0.txt",
    "LICENSES/runtime/GPL-2.0.txt",
    "LICENSES/runtime/GPL-3.0.txt",
    "LICENSES/runtime/LGPL-2.1.txt",
    "LICENSES/runtime/LGPL-3.0.txt",
    "LICENSES/runtime/MIT-DXMT.txt",
    "LICENSES/runtime/FDK-AAC.txt",
)
SOURCE_ARCHIVE_MEMBERS = (
    "wine-combined",
    "dxmt-combined",
    "runtime-component-inventory.tsv",
)
SOURCE_DIRECTORIES = SOURCE_ARCHIVE_MEMBERS[:2]
REQUIRED_PATCH_FAMILIES = frozenset(("audio", "cursor", "cn"))


class ReleaseValidationError(ValueError):
    """The candidate is not safe to attach to a release."""


def _valid_semver_identifiers(value: str, *, reject_numeric_leading_zero: bool) -> bool:
    identifiers = value.split(".")
    return all(
        IDENTIFIER_PATTERN.fullmatch(identifier)
        and not (
            reject_numeric_leading_zero
            and identifier.isdigit()
            and len(identifier) > 1
            and identifier.startswith("0")
        )
        for identifier in identifiers
    )


def normalize_version(value: str) -> str:
    """Return a canonical v-prefixed SemVer tag for a release version."""

    normalized = value.strip()
    normalized = normalized.removeprefix("v")
    if not normalized:
        raise ReleaseValidationError("release version must not be empty")

    version_and_build = normalized.split("+", maxsplit=1)
    if len(version_and_build) == 2 and not _valid_semver_identifiers(
        version_and_build[1], reject_numeric_leading_zero=False
    ):
        raise ReleaseValidationError(f"invalid SemVer build metadata: {value!r}")
    main = version_and_build[0]
    version_and_prerelease = main.split("-", maxsplit=1)
    core = version_and_prerelease[0]
    if SEMVER_CORE_PATTERN.fullmatch(core) is None:
        raise ReleaseValidationError(f"invalid SemVer release version: {value!r}")
    if len(version_and_prerelease) == 2 and not _valid_semver_identifiers(
        version_and_prerelease[1], reject_numeric_leading_zero=True
    ):
        raise ReleaseValidationError(f"invalid SemVer prerelease: {value!r}")
    return f"v{normalized}"


def _regular_file(path: Path, description: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ReleaseValidationError(f"{description} is not a regular file: {path}")
    return path


def _sha256(path: Path) -> str:
    return _sha256_file(_regular_file(path, "file"))


def _verify_checksum(artifact: Path, checksum: Path, description: str) -> str:
    artifact = _regular_file(artifact, description)
    checksum = _regular_file(checksum, f"{description} checksum")
    lines = [
        line.strip()
        for line in checksum.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(lines) != 1:
        raise ReleaseValidationError(f"{description} checksum must contain one record")
    fields = lines[0].split(maxsplit=1)
    if len(fields) != 2 or SHA256_PATTERN.fullmatch(fields[0]) is None:
        raise ReleaseValidationError(f"{description} checksum has invalid syntax")
    referenced_name = fields[1].removeprefix("*")
    if referenced_name != artifact.name:
        raise ReleaseValidationError(
            f"{description} checksum names {referenced_name!r}, expected {artifact.name!r}"
        )
    actual = _sha256(artifact)
    if actual != fields[0]:
        raise ReleaseValidationError(
            f"{description} checksum mismatch: {actual} != {fields[0]}"
        )
    return actual


def _validate_source_archive(path: Path, checksum: Path) -> str:
    digest = _verify_checksum(path, checksum, "corresponding-source archive")
    found: set[str] = set()
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            for member in archive.getmembers():
                member_path = PurePosixPath(member.name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ReleaseValidationError(
                        f"corresponding-source archive contains unsafe path: {member.name}"
                    )
                if member.issym() or member.islnk():
                    target = PurePosixPath(member.linkname)
                    if target.is_absolute() or ".." in target.parts:
                        raise ReleaseValidationError(
                            "corresponding-source archive contains unsafe link: "
                            f"{member.name} -> {member.linkname}"
                        )
                if member_path.parts:
                    found.add(member_path.parts[0])
    except (OSError, tarfile.TarError) as error:
        raise ReleaseValidationError(
            f"cannot inspect corresponding-source archive: {path}"
        ) from error
    missing = sorted(set(SOURCE_ARCHIVE_MEMBERS) - found)
    if missing:
        raise ReleaseValidationError(
            "corresponding-source archive is missing: " + ", ".join(missing)
        )
    return digest


def _validate_source_directories(source_root: Path) -> None:
    if source_root.is_symlink() or not source_root.is_dir():
        raise ReleaseValidationError(f"source root is not a directory: {source_root}")
    for name in SOURCE_DIRECTORIES:
        path = source_root / name
        if path.is_symlink() or not path.is_dir():
            raise ReleaseValidationError(f"missing source checkout: {path}")


def _validate_notices(repository_root: Path, lock: dict[str, Any]) -> None:
    for relative in NOTICE_FILES:
        path = _regular_file(repository_root / relative, "release notice")
        if not path.read_text(encoding="utf-8").strip():
            raise ReleaseValidationError(f"release notice is empty: {relative}")
    registry = (repository_root / "docs/patch-registry.md").read_text(encoding="utf-8")
    missing = [patch["id"] for patch in lock["patches"] if patch["id"] not in registry]
    if missing:
        raise ReleaseValidationError("patch registry is missing: " + ", ".join(missing))


def _validate_patch_families(lock: dict[str, Any]) -> None:
    families = {patch["family"] for patch in lock["patches"]}
    missing = sorted(REQUIRED_PATCH_FAMILIES - families)
    if missing:
        raise ReleaseValidationError(
            "release lock is missing patch families: " + ", ".join(missing)
        )


def _validation_report(path: Path, deployment_target: str) -> dict[str, Any]:
    try:
        report = json.loads(
            _regular_file(path, "validation report").read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, OSError) as error:
        raise ReleaseValidationError(
            f"cannot read validation report: {path}"
        ) from error
    if not isinstance(report, dict):
        raise ReleaseValidationError("validation report must be an object")
    if report.get("releaseEligible") is not True or report.get("status") != "valid":
        raise ReleaseValidationError(
            "candidate is not release eligible; a clean source build is required "
            f"(status={report.get('status')!r}, releaseEligible={report.get('releaseEligible')!r})"
        )
    if report.get("deploymentTarget") != deployment_target:
        raise ReleaseValidationError(
            "validation report deployment target does not match lock"
        )
    if report.get("inheritedMachOAboveTarget") != 0:
        raise ReleaseValidationError(
            "validation report contains inherited Mach-O targets"
        )
    return {key: value for key, value in report.items() if key != "runtime"}


def _write_notices(repository_root: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    sections = [
        "Arknights macOS Runtime third-party notices",
        "",
        "Source and patch provenance is recorded in provenance.json and runtime.lock.json.",
        "The patch registry is included in the source repository.",
        "Canonical license texts and the realised runtime component inventory follow.",
    ]
    for relative in (path for path in NOTICE_FILES if path.startswith("LICENSES/")):
        sections.extend(
            [
                "",
                f"===== {relative} =====",
                (repository_root / relative).read_text(encoding="utf-8").rstrip(),
            ]
        )
    sections.extend(
        [
            "",
            "===== docs/legal/redistribution.md =====",
            (repository_root / "docs/legal/redistribution.md")
            .read_text(encoding="utf-8")
            .rstrip(),
        ]
    )
    destination.write_text("\n".join(sections) + "\n", encoding="utf-8")


def verify_release(
    *,
    repository_root: Path,
    tag: str,
    commit: str,
    archive: Path,
    checksum: Path,
    source_root: Path,
    source_archive: Path,
    source_checksum: Path,
    validation_report: Path,
    output_directory: Path,
    component_inventory: Path,
) -> dict[str, Path]:
    try:
        canonical_tag = normalize_version(tag)
    except ReleaseValidationError as error:
        raise ReleaseValidationError(
            f"release tag is not an explicit SemVer tag: {tag!r}"
        ) from error
    if canonical_tag != tag:
        raise ReleaseValidationError(
            f"release tag is not an explicit SemVer tag: {tag!r}"
        )
    if COMMIT_PATTERN.fullmatch(commit) is None:
        raise ReleaseValidationError("release commit must be a full commit hash")

    lock_path = _regular_file(repository_root / "runtime.lock.json", "runtime lock")
    try:
        lock = load_lock(lock_path, repository_root=repository_root)
    except (LockError, OSError) as error:
        raise ReleaseValidationError(
            f"runtime lock validation failed: {error}"
        ) from error
    _validate_notices(repository_root, lock)
    _validate_patch_families(lock)
    inventory_text = _regular_file(
        component_inventory, "runtime component inventory"
    ).read_text(encoding="utf-8")
    if not inventory_text.startswith("component\trole\tsource\n"):
        raise ReleaseValidationError("runtime component inventory has invalid syntax")
    report = _validation_report(validation_report, lock["deploymentTarget"])
    _validate_source_directories(source_root)
    archive_digest = _verify_checksum(archive, checksum, "runtime archive")
    source_digest = _validate_source_archive(source_archive, source_checksum)

    output_directory.mkdir(parents=True, exist_ok=True)
    provenance_path = output_directory / "provenance.json"
    notices_path = output_directory / "THIRD-PARTY-NOTICES.txt"
    provenance = {
        "schemaVersion": 1,
        "releaseTag": tag,
        "sourceCommit": commit,
        "runtimeLock": {
            "path": "runtime.lock.json",
            "sha256": _sha256(lock_path),
            "contents": lock,
        },
        "runtimeArchive": {"name": archive.name, "sha256": archive_digest},
        "correspondingSourceArchive": {
            "name": source_archive.name,
            "sha256": source_digest,
        },
        "validation": report,
    }
    provenance_path.write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_notices(repository_root, notices_path)
    with notices_path.open("a", encoding="utf-8") as notices:
        notices.write("\n===== runtime-component-inventory.tsv =====\n")
        notices.write(inventory_text)
    return {"provenance": provenance_path, "notices": notices_path}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--checksum", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--source-checksum", type=Path, required=True)
    parser.add_argument("--validation-report", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--component-inventory", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        outputs = verify_release(
            repository_root=REPOSITORY_ROOT,
            tag=arguments.tag,
            commit=arguments.commit,
            archive=arguments.archive,
            checksum=arguments.checksum,
            source_root=arguments.source_root,
            source_archive=arguments.source_archive,
            source_checksum=arguments.source_checksum,
            validation_report=arguments.validation_report,
            output_directory=arguments.output_directory,
            component_inventory=arguments.component_inventory,
        )
    except (ReleaseValidationError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for path in outputs.values():
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
