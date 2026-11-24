# SPDX-License-Identifier: MPL-2.0

"""Prepare the pinned source checkouts of a lane and fetch its base archive."""

import subprocess
from pathlib import Path

from scripts.lib.artifact import ArtifactError, fetch_verified
from scripts.lib.console import info, success
from scripts.lock.model import DEFAULT_LANE, ROOT, Lane, LockError, load_lock
from scripts.lock.patches import lane_patches

BUILD_ROOT = ROOT / ".build"


def _run(*command: str, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def source_directory(component: str, lane: Lane) -> str:
    """Name a prepared source directory. The default lane adds no suffix."""

    suffix = "" if lane.name == DEFAULT_LANE else f"-{lane.name}"
    return f"{component}{suffix}"


def prepare(
    destination_root: Path = BUILD_ROOT / "sources",
    *,
    target: str | None = None,
    all_sources: bool = False,
    skip_patches: tuple[str, ...] = (),
) -> None:
    lock = load_lock()
    lane = lock.lane(target)
    if lane.build == "external":
        raise LockError(
            f"the {lane.name} target is built externally; use the arm64 wrapper"
        )
    patches = lane_patches(lock, lane.name)
    unknown = sorted(set(skip_patches) - {patch.id for patch in patches})
    if unknown:
        raise LockError(f"unknown patch to skip: {', '.join(unknown)}")
    components = {patch.component for patch in patches}
    if all_sources:
        components = set(lane.sources)
    for component in sorted(components):
        source = lane.sources[component]
        destination = destination_root / source_directory(component, lane)
        if destination.exists():
            raise LockError(f"source destination already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        info(f"Preparing {component} source")
        _run(
            "git",
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            source.repository,
            str(destination),
        )
        _run("git", "checkout", "--detach", source.commit, cwd=destination)
        for patch in patches:
            if patch.component != component:
                continue
            if patch.id in skip_patches:
                info(f"Skipping patch {patch.id} by request")
                continue
            patch_path = ROOT / patch.files[lane.name].path
            _run("git", "apply", "--check", str(patch_path), cwd=destination)
            _run("git", "apply", str(patch_path), cwd=destination)
        success(f"Prepared pinned {component} source")


def fetch_base(*, target: str | None = None) -> Path:
    lane = load_lock().lane(target)
    if lane.base is None:
        raise LockError(
            f"the {lane.name} target builds every component and has no base artifact"
        )
    destination = BUILD_ROOT / "downloads" / "Libraries.tar.gz"
    try:
        path = fetch_verified(
            lane.base.download.url,
            lane.base.download.sha256,
            destination,
            label="Downloading runtime",
        )
    except ArtifactError as problem:
        raise LockError(f"base artifact: {problem}") from problem
    success("Verified the base runtime archive")
    return path
