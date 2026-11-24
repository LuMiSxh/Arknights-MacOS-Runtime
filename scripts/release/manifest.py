# SPDX-License-Identifier: MPL-2.0

"""Write the per-architecture runtime manifests and the release `SHA256SUMS`.

Run this last, after the deltas exist. A manifest tells the client everything it needs to
install one architecture: the archive, the deltas, the interface, the component versions,
and the provenance. `docs/runtime-format.md` documents the shape.
"""

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.lanes import manifest_name
from scripts.lib.artifact import ArtifactError, sha256, write_checksums
from scripts.lib.console import error, info, success
from scripts.lock.model import LOCK_PATH, Lock, LockError
from scripts.lock.parse import load_lock

SCHEMA_VERSION = 1
BUILD_REPOSITORY = "https://github.com/LuMiSxh/Arknights-MacOS-Runtime"
# The release notes are the release body, not an asset.
NOT_ASSETS = ("RELEASE-NOTES.md",)


class ManifestError(ValueError):
    """The release files cannot form a manifest."""


def _repository(url: str) -> str:
    return url.removesuffix(".git")


def delta_records(dist: Path, arch: str) -> list[dict[str, Any]]:
    """Return one record per delta archive of `arch` in `dist`, sorted by source version."""

    prefix, suffix = f"runtime-{arch}-from-", ".delta.tar.xz"
    records = []
    for path in sorted(dist.glob(f"{prefix}*{suffix}")):
        records.append(
            {
                "from": path.name.removeprefix(prefix).removesuffix(suffix),
                "name": path.name,
                "sha256": sha256(path),
                "sizeBytes": path.stat().st_size,
            }
        )
    return records


def _provenance(fragment: dict[str, Any], lock: Lock) -> dict[str, str]:
    """Return the flat provenance keys that the client stores per lane."""

    lane = lock.lane(fragment["target"])
    provenance = {
        "buildRepository": BUILD_REPOSITORY,
        "buildCommit": fragment["buildCommit"],
    }
    external = fragment["wine"].get("externalBuild")
    if external is not None:
        provenance["externalBuildRepository"] = external["repository"]
        provenance["externalBuildCommit"] = external["commit"]
    for name in ("wine", "dxmt"):
        provenance[f"{name}Repository"] = _repository(fragment[name]["repository"])
        provenance[f"{name}Commit"] = fragment[name]["commit"]
    if lane.base is not None:
        moltenvk = lane.base.provenance["moltenvk"]
        provenance["moltenvkRepository"] = _repository(moltenvk.repository)
        provenance["moltenvkCommit"] = moltenvk.commit
        provenance["nixpkgsRepository"] = _repository(lock.nixpkgs.repository)
        provenance["nixpkgsCommit"] = lock.nixpkgs.commit
        provenance["baseRecipeRepository"] = _repository(lane.base.recipe.repository)
        provenance["baseRecipeCommit"] = lane.base.recipe.commit
        provenance["baseArchiveUrl"] = lane.base.download.url
        provenance["baseArchiveSha256"] = lane.base.download.sha256
    return provenance


def build_manifest(
    fragment: dict[str, Any],
    deltas: list[dict[str, Any]],
    lock: Lock,
    document: dict[str, Any],
) -> dict[str, Any]:
    """Return the manifest of one lane from its provenance fragment and the lock.

    `document` is the raw lock JSON; the interface is copied from it verbatim.
    """

    target = fragment["target"]
    lane = lock.lane(target)
    components = {
        name: fragment[name]["version"]
        for name in ("wine", "dxmt")
        if fragment[name].get("version")
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "arch": fragment["arch"],
        "version": fragment["version"],
        "minimumMacOS": lane.minimum_macos,
        "archive": {
            key: fragment["runtimeArchive"][key]
            for key in ("name", "sha256", "sizeBytes")
        },
        "deltas": deltas,
        "interface": document["lanes"][target]["interface"],
        "components": components,
        "provenance": _provenance(fragment, lock),
    }


def write_manifests(dist: Path, lock_path: Path = LOCK_PATH) -> list[Path]:
    """Write `runtime-<arch>.json` for every runtime that `provenance.json` lists."""

    try:
        provenance = json.loads((dist / "provenance.json").read_text(encoding="utf-8"))
        document = json.loads(lock_path.read_text(encoding="utf-8"))
        lock = load_lock(lock_path)
    except (OSError, ValueError) as problem:
        raise ManifestError(f"cannot read the release inputs: {problem}") from problem
    paths = []
    for fragment in provenance["runtimes"]:
        recorded = fragment["runtimeLock"]["sha256"]
        if recorded != sha256(lock_path):
            raise ManifestError(
                f"{lock_path.name} differs from the lock that built {fragment['target']}"
            )
        arch = fragment["arch"]
        manifest = build_manifest(fragment, delta_records(dist, arch), lock, document)
        path = dist / manifest_name(arch)
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def finalize(dist: Path, lock_path: Path = LOCK_PATH) -> list[Path]:
    """Write the manifests, then `SHA256SUMS` over every asset in `dist`."""

    manifests = write_manifests(dist, lock_path)
    write_checksums(dist, exclude=NOT_ASSETS)
    return manifests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="-m scripts release manifest", description=__doc__
    )
    parser.add_argument(
        "--dist", type=Path, required=True, help="combined release directory"
    )
    arguments = parser.parse_args(argv)
    try:
        manifests = finalize(arguments.dist)
    except (ManifestError, LockError, ArtifactError, OSError) as problem:
        error(str(problem))
        return 1
    for path in manifests:
        info(f"wrote {path.name}")
    success("wrote SHA256SUMS")
    return 0
