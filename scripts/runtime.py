#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Validate, fetch, and prepare Arknights MacOS Runtime's pinned runtime sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

if __package__:
    from .lib.console import Progress, error, info, success
else:
    from lib.console import Progress, error, info, success

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "runtime.lock.json"
BUILD_ROOT = ROOT / ".build"
STAGES = ("base", "audio", "cursor", "cn", "combined")
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")


class LockError(ValueError):
    """The runtime lock is unsafe or internally inconsistent."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LockError(f"{name} must be an object")
    return value


def _require_string(mapping: dict[str, Any], key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise LockError(f"{context}.{key} must be a non-empty string")
    return value


def _validated_repository(url: str, context: str) -> None:
    if not url.startswith("https://github.com/") or not url.endswith(".git"):
        raise LockError(f"{context} must be an immutable GitHub HTTPS repository URL")


def _contained_file(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise LockError(f"patch path {relative!r} must be repository-relative")
    path = root / candidate
    if path.is_symlink():
        raise LockError(f"patch path {relative!r} must not be a symlink")
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise LockError(
            f"patch path {relative!r} must be repository-relative"
        ) from error
    if not path.is_file():
        raise LockError(f"patch file does not exist: {relative}")
    return path


def load_lock(
    path: Path = LOCK_PATH, *, repository_root: Path = ROOT
) -> dict[str, Any]:
    try:
        lock = _require_mapping(json.loads(path.read_text(encoding="utf-8")), "lock")
    except (OSError, json.JSONDecodeError) as error:
        raise LockError(f"cannot read {path}: {error}") from error

    if lock.get("schemaVersion") != 1:
        raise LockError("schemaVersion must be 1")
    if lock.get("archiveSchemaVersion") != 2:
        raise LockError("archiveSchemaVersion must be 2")
    if lock.get("deploymentTarget") != "15.0":
        raise LockError("deploymentTarget must be 15.0")

    sources = _require_mapping(lock.get("sources"), "sources")
    for component in ("wine", "dxmt"):
        source = _require_mapping(sources.get(component), f"sources.{component}")
        repository = _require_string(source, "repository", f"sources.{component}")
        commit = _require_string(source, "commit", f"sources.{component}")
        _validated_repository(repository, f"sources.{component}.repository")
        if COMMIT_PATTERN.fullmatch(commit) is None:
            raise LockError(f"sources.{component}.commit must be a full commit hash")

    artifact = _require_mapping(lock.get("baseArtifact"), "baseArtifact")
    artifact_url = _require_string(artifact, "url", "baseArtifact")
    artifact_hash = _require_string(artifact, "sha256", "baseArtifact")
    recipe_commit = _require_string(artifact, "recipeCommit", "baseArtifact")
    if not artifact_url.startswith("https://github.com/"):
        raise LockError("baseArtifact.url must use GitHub HTTPS")
    if HASH_PATTERN.fullmatch(artifact_hash) is None:
        raise LockError("baseArtifact.sha256 must be a lowercase SHA-256 hash")
    if COMMIT_PATTERN.fullmatch(recipe_commit) is None:
        raise LockError("baseArtifact.recipeCommit must be a full commit hash")

    base_provenance = _require_mapping(lock.get("baseProvenance"), "baseProvenance")
    for component in ("moltenvk", "gstreamer", "ffmpeg", "wineGecko"):
        commit = _require_string(base_provenance, component, "baseProvenance")
        if COMMIT_PATTERN.fullmatch(commit) is None:
            raise LockError(f"baseProvenance.{component} must be a full commit hash")

    build = _require_mapping(lock.get("build"), "build")
    nixpkgs_commit = _require_string(build, "nixpkgsCommit", "build")
    if COMMIT_PATTERN.fullmatch(nixpkgs_commit) is None:
        raise LockError("build.nixpkgsCommit must be a full commit hash")

    patches = lock.get("patches")
    if not isinstance(patches, list):
        raise LockError("patches must be an array")
    seen_ids: set[str] = set()
    for index, value in enumerate(patches):
        patch = _require_mapping(value, f"patches[{index}]")
        patch_id = _require_string(patch, "id", f"patches[{index}]")
        component = _require_string(patch, "component", f"patches[{index}]")
        family = _require_string(patch, "family", f"patches[{index}]")
        relative = _require_string(patch, "path", f"patches[{index}]")
        expected = _require_string(patch, "sha256", f"patches[{index}]")
        if patch_id in seen_ids:
            raise LockError(f"duplicate patch id: {patch_id}")
        seen_ids.add(patch_id)
        if component not in sources:
            raise LockError(f"unknown patch component: {component}")
        if family not in ("audio", "cursor", "cn"):
            raise LockError(f"unknown patch family: {family}")
        if HASH_PATTERN.fullmatch(expected) is None:
            raise LockError(f"patch {patch_id} has an invalid SHA-256 hash")
        actual = _sha256_file(_contained_file(repository_root, relative))
        if actual != expected:
            raise LockError(f"patch {patch_id} hash mismatch: {actual} != {expected}")

    return lock


def patches_for_stage(lock: dict[str, Any], stage: str) -> list[dict[str, Any]]:
    if stage not in STAGES:
        raise LockError(f"unknown stage {stage!r}; expected one of {', '.join(STAGES)}")
    if stage == "base":
        return []
    if stage == "combined":
        return list(lock["patches"])
    return [patch for patch in lock["patches"] if patch["family"] == stage]


def _run(*command: str, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def prepare(stage: str, destination_root: Path = BUILD_ROOT / "sources") -> None:
    lock = load_lock()
    selected = patches_for_stage(lock, stage)
    components = {patch["component"] for patch in selected}
    if stage == "base":
        components = set(lock["sources"])
    for component in sorted(components):
        source = lock["sources"][component]
        destination = destination_root / f"{component}-{stage}"
        if destination.exists():
            raise LockError(f"source destination already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        info(f"Preparing {component} source for the {stage} stage")
        _run(
            "git",
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            source["repository"],
            str(destination),
        )
        _run("git", "checkout", "--detach", source["commit"], cwd=destination)
        for patch in selected:
            if patch["component"] != component:
                continue
            patch_path = ROOT / patch["path"]
            _run("git", "apply", "--check", str(patch_path), cwd=destination)
            _run("git", "apply", str(patch_path), cwd=destination)
        success(f"Prepared pinned {component} source")


def fetch_base() -> Path:
    lock = load_lock()
    artifact = lock["baseArtifact"]
    downloads = BUILD_ROOT / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    destination = downloads / "Libraries.tar.gz"
    partial = downloads / "Libraries.tar.gz.part"
    if destination.is_file() and _sha256_file(destination) == artifact["sha256"]:
        success("Using verified base runtime archive from the local cache")
        return destination
    info("Downloading the pinned base runtime archive")
    with (
        urllib.request.urlopen(artifact["url"], timeout=60) as response,
        partial.open("wb") as output,
    ):
        content_length = response.headers.get("Content-Length", "")
        total = int(content_length) if content_length.isdigit() else 0
        progress = Progress("Downloading runtime", total)
        current = 0
        try:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                current += len(chunk)
                progress.update(current)
        finally:
            progress.finish()
    actual = _sha256_file(partial)
    if actual != artifact["sha256"]:
        raise LockError(
            f"base artifact hash mismatch: {actual} != {artifact['sha256']}"
        )
    partial.replace(destination)
    success("Verified the base runtime archive")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate-lock")
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("stage", choices=STAGES)
    prepare_parser.add_argument("--destination-root", type=Path)
    subparsers.add_parser("fetch-base")
    arguments = parser.parse_args()
    try:
        if arguments.command == "validate-lock":
            load_lock()
            success("Validated runtime.lock.json")
        elif arguments.command == "prepare":
            prepare(
                arguments.stage,
                arguments.destination_root or BUILD_ROOT / "sources",
            )
        else:
            print(fetch_base())
    except (LockError, OSError, subprocess.CalledProcessError) as caught_error:
        error(str(caught_error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
