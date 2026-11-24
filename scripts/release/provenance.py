# SPDX-License-Identifier: MPL-2.0

"""Build the provenance fragment that each runtime lane writes.

A fragment records one lane. `scripts/release/combine.py` merges the fragments into the
release `provenance.json`.
"""

import json
import re
from pathlib import Path
from typing import Any

from scripts.lanes import Target
from scripts.lib.artifact import sha256
from scripts.lock.model import ARCHIVE_SCHEMA_VERSION, LockError
from scripts.lock.parse import load_lock

LOCK_FILE_NAME = "runtime.lock.json"
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class ProvenanceInputError(ValueError):
    """A release provenance input is missing or invalid."""


def runtime_lock_provenance(repository_root: Path, target: str) -> dict[str, Any]:
    """Return the `runtimeLock` entry that every release lane records."""

    lock_path = repository_root / LOCK_FILE_NAME
    if lock_path.is_symlink() or not lock_path.is_file():
        raise ProvenanceInputError(f"runtime lock is not a regular file: {lock_path}")
    try:
        lane = load_lock(lock_path, repository_root=repository_root).lane(target)
        document = json.loads(lock_path.read_text(encoding="utf-8"))
    except (LockError, OSError) as error:
        raise ProvenanceInputError(
            f"runtime lock validation failed: {error}"
        ) from error
    return {
        "path": LOCK_FILE_NAME,
        "sha256": sha256(lock_path),
        "contents": _lane_contents(document, lane.name),
    }


def _lane_contents(document: dict[str, Any], target: str) -> dict[str, Any]:
    """Return the lane view that the release verifier and the client read."""

    lane = document["lanes"][target]
    return {
        "archiveSchemaVersion": ARCHIVE_SCHEMA_VERSION,
        "target": target,
        "buildMode": lane["build"],
        "deploymentTarget": lane["minimumMacOS"],
        "features": lane["interface"]["features"],
        "interface": lane["interface"],
        "patches": [
            {
                "id": patch["id"],
                "component": patch["component"],
                "number": patch["number"],
            }
            for patch in document["patches"]
            if target in patch["files"]
        ],
    }


def validation_provenance(
    path: Path,
    deployment_target: str,
    *,
    external: bool = False,
    gate: bool = True,
) -> dict[str, Any]:
    """Return the validation report that a fragment records.

    With `gate`, the report must match the lock, have no Mach-O above the target, and,
    for a built lane, be release eligible. An external lane is never release eligible,
    because its Wine tree is built upstream.
    """

    if path.is_symlink() or not path.is_file():
        raise ProvenanceInputError(f"validation report is not a regular file: {path}")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise ProvenanceInputError(f"cannot read validation report: {path}") from error
    if not isinstance(report, dict):
        raise ProvenanceInputError("validation report must be an object")
    if gate:
        if not external and (
            report.get("releaseEligible") is not True or report.get("status") != "valid"
        ):
            raise ProvenanceInputError(
                "candidate is not release eligible; a clean source build is required "
                f"(status={report.get('status')!r}, releaseEligible={report.get('releaseEligible')!r})"
            )
        if report.get("deploymentTarget") != deployment_target:
            raise ProvenanceInputError(
                "validation report deployment target does not match lock"
            )
        if report.get("inheritedMachOAboveTarget") != 0:
            raise ProvenanceInputError(
                "validation report contains inherited Mach-O targets"
            )
    result = {key: value for key, value in report.items() if key != "runtime"}
    if external:
        result["releaseEligible"] = False
        result["builtExternally"] = True
    return result


def archive_record(path: Path) -> dict[str, Any]:
    """Return the name, SHA-256, and size of one release archive."""

    return {
        "name": path.name,
        "sha256": sha256(path),
        "sizeBytes": path.stat().st_size,
    }


def runtime_fragment(
    *,
    target: Target,
    version: str,
    source_commit: str,
    runtime_lock: dict[str, Any],
    wine: dict[str, Any],
    dxmt: dict[str, Any],
    runtime_archive: Path,
    source_archive: Path,
    validation: dict[str, Any],
    build_toolchain: dict[str, Any],
) -> dict[str, Any]:
    """Return the provenance fragment of one lane.

    `wine` holds the lane-specific Wine data. The source kind comes from the target.
    Catalog URLs never appear in a fragment.
    """

    if COMMIT_PATTERN.fullmatch(source_commit) is None:
        raise ProvenanceInputError("release commit must be a full commit hash")
    return {
        "target": target.name,
        "arch": target.arch,
        "version": version,
        "buildCommit": source_commit,
        "runtimeLock": runtime_lock,
        "wine": {"source": target.wine_source, **wine},
        "dxmt": dxmt,
        "runtimeArchive": archive_record(runtime_archive),
        "correspondingSourceArchive": archive_record(source_archive),
        "validation": validation,
        "buildToolchain": build_toolchain,
    }


def write_fragment(path: Path, fragment: dict[str, Any]) -> Path:
    """Write one fragment as sorted, indented JSON."""

    path.write_text(
        json.dumps(fragment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path
