# SPDX-License-Identifier: MPL-2.0

"""Resolve the lock and validation inputs shared by release provenance writers."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__:
    from ..build_common import sha256
    from ..runtime import LockError, load_lock
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.build_common import sha256
    from scripts.runtime import LockError, load_lock


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
        lock = load_lock(lock_path, repository_root=repository_root, target=target)
    except (LockError, OSError) as error:
        raise ProvenanceInputError(
            f"runtime lock validation failed: {error}"
        ) from error
    return {"path": LOCK_FILE_NAME, "sha256": sha256(lock_path), "contents": lock}


def validation_provenance(
    path: Path, deployment_target: str, *, external: bool = False
) -> dict[str, Any]:
    """Return the normalized validation report recorded in provenance."""

    if path.is_symlink() or not path.is_file():
        raise ProvenanceInputError(f"validation report is not a regular file: {path}")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise ProvenanceInputError(f"cannot read validation report: {path}") from error
    if not isinstance(report, dict):
        raise ProvenanceInputError("validation report must be an object")
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
