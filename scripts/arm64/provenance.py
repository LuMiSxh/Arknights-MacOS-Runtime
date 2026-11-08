#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Write the external native-arm64 release provenance.

The provenance records the selected catalog artifact, the pinned Wine revision, and the
SHA-256 of the two release archives. It never records the secret-backed catalog URL or the
external artifact URL.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__:
    from ..build_common import (
        NATIVE_ARM64_TARGET,
        ROOT,
        WINE_BUILD_NEW_REPOSITORY,
        sha256,
    )
    from ..lib.console import error, success
    from ..release.provenance import (
        COMMIT_PATTERN,
        ProvenanceInputError,
        runtime_lock_provenance,
        validation_provenance,
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.build_common import (
        NATIVE_ARM64_TARGET,
        ROOT,
        WINE_BUILD_NEW_REPOSITORY,
        sha256,
    )
    from scripts.lib.console import error, success
    from scripts.release.provenance import (
        COMMIT_PATTERN,
        ProvenanceInputError,
        runtime_lock_provenance,
        validation_provenance,
    )


class ProvenanceError(RuntimeError):
    """Provenance cannot be produced."""


def write_provenance(
    lock: dict[str, Any],
    tag: str,
    runtime_archive: Path,
    source_archive: Path,
    output: Path,
    *,
    source_commit: str,
    runtime_lock: dict[str, Any],
    validation: dict[str, Any] | None = None,
    external_artifact: Path | None = None,
) -> dict[str, Any]:
    """Write `provenance.json` for the external target and return its contents."""

    if lock.get("buildMode") != "external":
        raise ProvenanceError("provenance requires an external target")
    if COMMIT_PATTERN.fullmatch(source_commit) is None:
        raise ProvenanceError("release commit must be a full commit hash")

    interface = lock.get("interface") or {}
    minimum_macos = interface.get("minimumMacOS")
    if not isinstance(minimum_macos, str) or not minimum_macos:
        raise ProvenanceError("the lock interface must state minimumMacOS")
    revision = lock["sources"]["wine"]["commit"]

    provenance = {
        "schemaVersion": 1,
        "releaseTag": tag,
        "sourceCommit": source_commit,
        "runtimeLock": runtime_lock,
        "target": lock["target"],
        "minimumMacOS": minimum_macos,
        "features": lock["features"],
        "externalBuild": {
            "repository": WINE_BUILD_NEW_REPOSITORY,
            "revision": revision,
        },
        "runtimeArchive": {
            "name": runtime_archive.name,
            "sha256": sha256(runtime_archive),
        },
        "correspondingSourceArchive": {
            "name": source_archive.name,
            "sha256": sha256(source_archive),
        },
    }
    if validation is not None:
        provenance["validation"] = validation
    if external_artifact is not None:
        try:
            artifact = json.loads(external_artifact.read_text(encoding="utf-8"))
            artifact_id = artifact["id"]
            artifact_sha256 = artifact["sha256"]
            artifact_size = artifact.get("size")
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as problem:
            raise ProvenanceError(
                "external artifact metadata is incomplete"
            ) from problem
        locked = lock.get("artifact") or {}
        if artifact_id != locked.get("release") or artifact_sha256 != locked.get(
            "sha256"
        ):
            raise ProvenanceError(
                "external artifact metadata does not match the lock pin"
            )
        provenance["externalArtifact"] = {
            "id": artifact_id,
            "sha256": artifact_sha256,
            "size": artifact_size,
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return provenance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=NATIVE_ARM64_TARGET)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--runtime-archive", type=Path, required=True)
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--external-artifact", type=Path)
    parser.add_argument("--validation-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        runtime_lock = runtime_lock_provenance(ROOT, arguments.target)
        lock = runtime_lock["contents"]
        validation = validation_provenance(
            arguments.validation_report,
            lock["deploymentTarget"],
            external=True,
        )
        write_provenance(
            lock,
            arguments.tag,
            arguments.runtime_archive,
            arguments.source_archive,
            arguments.output,
            source_commit=arguments.commit,
            runtime_lock=runtime_lock,
            validation=validation,
            external_artifact=arguments.external_artifact,
        )
    except (ProvenanceError, ProvenanceInputError, OSError) as caught_error:
        error(str(caught_error))
        return 1
    success(f"wrote {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
