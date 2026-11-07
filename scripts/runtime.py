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
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

if __package__:
    from .lib.console import Progress, error, info, success
else:
    from lib.console import Progress, error, info, success

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "runtime.lock.json"
BUILD_ROOT = ROOT / ".build"
STAGES = (
    "base",
    "audio",
    "hardware-cursor",
    "performance",
    "ace",
    "cef",
    "cn",
    "fullscreen",
    "combined",
)
PATCH_FAMILIES = frozenset(
    {
        "address-space",
        "audio",
        "hardware-cursor",
        "performance",
        "ace",
        "cef",
        "cn",
        "menu",
        "fullscreen",
        "fex",
        "mono",
        "arm64ec",
        "wx",
        "id-registers",
        "loader",
        "winsock",
        "appcontainer",
    }
)
SCHEMA_VERSION = 3
ARCHIVE_SCHEMA_VERSION = 2
# A target entry replaces these keys as a whole. Anything absent is inherited
# from the top level, which holds the default target's pins.
TARGET_OVERRIDE_KEYS = frozenset(
    {
        "buildMode",
        "deploymentTarget",
        "sources",
        "interface",
        "features",
        "baseArtifact",
        "artifact",
    }
)
SOURCE_COMPONENTS = ("wine", "dxmt", "fex")
REQUIRED_SOURCES = ("wine", "dxmt")
FEATURE_KEYS = frozenset(
    {"hardwareCursor", "metalFXSpatialUpscaling", "nativeFullscreenSpace"}
)
TARGET_NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")


class LockError(ValueError):
    """The runtime lock is unsafe or internally inconsistent."""


@dataclass(frozen=True)
class SourcePin:
    """One immutable upstream source identity monitored by this repository."""

    name: str
    repository: str
    commit: str


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
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"github.com", "gitlab.winehq.org"}
        or not parsed.path.endswith(".git")
        or parsed.query
        or parsed.fragment
    ):
        raise LockError(f"{context} must be an allowlisted HTTPS Git repository URL")


def _source_pin(value: Any, name: str) -> SourcePin:
    source = _require_mapping(value, name)
    repository = _require_string(source, "repository", name)
    commit = _require_string(source, "commit", name)
    _validated_repository(repository, f"{name}.repository")
    if COMMIT_PATTERN.fullmatch(commit) is None:
        raise LockError(f"{name}.commit must be a full commit hash")
    return SourcePin(name.rsplit(".", maxsplit=1)[-1], repository, commit)


def _require_path_list(mapping: dict[str, Any], key: str, context: str) -> list[str]:
    value = mapping.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or not value:
        raise LockError(f"{context}.{key} must be a non-empty array")
    entries = []
    for index, entry in enumerate(value):
        if not isinstance(entry, str) or not entry:
            raise LockError(f"{context}.{key}[{index}] must be a non-empty string")
        entries.append(_runtime_relative(entry, f"{context}.{key}[{index}]"))
    return entries


def _runtime_relative(value: str, context: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise LockError(f"{context} must be a runtime-relative path")
    return value


def _target_name(value: Any, context: str) -> str:
    if not isinstance(value, str) or TARGET_NAME.fullmatch(value) is None:
        raise LockError(f"{context} must be a lowercase target name")
    return value


def monitored_sources(lock: dict[str, Any]) -> tuple[SourcePin, ...]:
    """Return every source pin owned and monitored by the runtime repository."""

    sources = _require_mapping(lock.get("sources"), "sources")
    pins = [
        _source_pin(sources.get(component), f"sources.{component}")
        for component in REQUIRED_SOURCES
    ]
    if "fex" in sources:
        pins.append(_source_pin(sources["fex"], "sources.fex"))
    if lock.get("baseArtifact") is not None:
        recipe = _source_pin(
            lock["baseArtifact"].get("recipe"), "baseArtifact.buildRecipe"
        )
        pins.append(SourcePin("buildRecipe", recipe.repository, recipe.commit))
        provenance = _require_mapping(lock.get("baseProvenance"), "baseProvenance")
        for component in ("moltenvk", "wineGecko"):
            pin = _source_pin(provenance.get(component), f"baseProvenance.{component}")
            pins.append(SourcePin(component, pin.repository, pin.commit))
    build = _require_mapping(lock.get("build"), "build")
    pin = _source_pin(build.get("nixpkgs"), "build.nixpkgs")
    pins.append(SourcePin("nixpkgs", pin.repository, pin.commit))
    return tuple(pins)


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


def _validate_sources(value: Any, context: str) -> dict[str, Any]:
    sources = _require_mapping(value, context)
    missing = [component for component in REQUIRED_SOURCES if component not in sources]
    if missing:
        raise LockError(f"{context} must pin {', '.join(missing)}")
    unknown = sorted(set(sources) - set(SOURCE_COMPONENTS))
    if unknown:
        raise LockError(f"{context} has unknown components: {', '.join(unknown)}")
    for component, pin in sources.items():
        _source_pin(pin, f"{context}.{component}")
    return sources


def _validate_base_artifact(value: Any, context: str) -> dict[str, Any]:
    artifact = _require_mapping(value, context)
    url = _require_string(artifact, "url", context)
    digest = _require_string(artifact, "sha256", context)
    if not url.startswith("https://github.com/"):
        raise LockError(f"{context}.url must use GitHub HTTPS")
    if HASH_PATTERN.fullmatch(digest) is None:
        raise LockError(f"{context}.sha256 must be a lowercase SHA-256 hash")
    _source_pin(artifact.get("recipe"), f"{context}.buildRecipe")
    return artifact


def _build_mode(value: Any, context: str) -> str:
    if value not in ("build", "external"):
        raise LockError(f"{context} must be build or external")
    return value


def _validate_artifact(value: Any, context: str) -> dict[str, Any]:
    artifact = _require_mapping(value, context)
    for key in ("catalog", "release"):
        _require_string(artifact, key, context)
    digest = _require_string(artifact, "sha256", context)
    if HASH_PATTERN.fullmatch(digest) is None:
        raise LockError(f"{context}.sha256 must be a lowercase SHA-256 hash")
    return artifact


def _validate_interface(value: Any, context: str) -> dict[str, Any]:
    interface = _require_mapping(value, context)
    for key in ("wineDirectory", "dxmtDirectory"):
        if key in interface:
            _require_string(interface, key, context)
    for key in ("executables", "requiredFiles"):
        _require_path_list(interface, key, context)
    return interface


def _validate_features(value: Any, context: str) -> dict[str, Any]:
    features = _require_mapping(value, context)
    if set(features) != FEATURE_KEYS:
        raise LockError(f"{context} must contain exactly the runtime features")
    for key in FEATURE_KEYS:
        if type(features[key]) is not bool:
            raise LockError(f"{context}.{key} must be a boolean")
    return features


def _validate_targets(lock: dict[str, Any]) -> dict[str, dict[str, Any]]:
    declared = _require_mapping(lock.get("targets"), "targets")
    if not declared:
        raise LockError("targets must name at least one target")
    targets: dict[str, dict[str, Any]] = {}
    for name, value in declared.items():
        _target_name(name, f"targets.{name}")
        overrides = _require_mapping(value, f"targets.{name}")
        unknown = sorted(set(overrides) - TARGET_OVERRIDE_KEYS)
        if unknown:
            raise LockError(f"targets.{name} has unknown keys: {', '.join(unknown)}")
        targets[name] = overrides
    default_target = _target_name(lock.get("defaultTarget"), "defaultTarget")
    if default_target not in targets:
        raise LockError("defaultTarget must name a declared target")
    return targets


def _selected_target(
    lock: dict[str, Any], targets: dict[str, dict[str, Any]], target: str | None
) -> str:
    if target is None:
        return lock["defaultTarget"]
    _target_name(target, "target")
    if target not in targets:
        raise LockError(
            f"unknown target {target!r}; expected one of {', '.join(sorted(targets))}"
        )
    return target


def _patch_targets(
    patch: dict[str, Any], targets: dict[str, dict[str, Any]], context: str
) -> list[str]:
    declared = patch.get("targets")
    if declared is None:
        return sorted(targets)
    if not isinstance(declared, list) or not declared:
        raise LockError(f"{context}.targets must be a non-empty array")
    names: list[str] = []
    for index, name in enumerate(declared):
        _target_name(name, f"{context}.targets[{index}]")
        if name not in targets:
            raise LockError(
                f"{context}.targets[{index}] names an undeclared target: {name}"
            )
        if name in names:
            raise LockError(f"{context}.targets repeats the target {name}")
        names.append(name)
    return names


def _resolve_target(
    lock: dict[str, Any], name: str, overrides: dict[str, Any]
) -> dict[str, Any]:
    """Flatten the document for one target. A target entry replaces whole keys."""

    resolved: dict[str, Any] = {
        "schemaVersion": lock["schemaVersion"],
        "archiveSchemaVersion": lock["archiveSchemaVersion"],
        "defaultTarget": lock["defaultTarget"],
        "target": name,
        "baseProvenance": lock.get("baseProvenance"),
        "build": lock.get("build"),
        "patches": [],
    }
    for key in (
        "buildMode",
        "deploymentTarget",
        "sources",
        "interface",
        "features",
        "baseArtifact",
        "artifact",
    ):
        resolved[key] = overrides[key] if key in overrides else lock.get(key)
    return resolved


def load_lock(
    path: Path = LOCK_PATH,
    *,
    repository_root: Path = ROOT,
    target: str | None = None,
) -> dict[str, Any]:
    """Validate the lock and return its resolved view for one build target."""

    try:
        lock = _require_mapping(json.loads(path.read_text(encoding="utf-8")), "lock")
    except (OSError, json.JSONDecodeError) as error:
        raise LockError(f"cannot read {path}: {error}") from error

    if lock.get("schemaVersion") != SCHEMA_VERSION:
        raise LockError(f"schemaVersion must be {SCHEMA_VERSION}")
    if lock.get("archiveSchemaVersion") != ARCHIVE_SCHEMA_VERSION:
        raise LockError(f"archiveSchemaVersion must be {ARCHIVE_SCHEMA_VERSION}")

    targets = _validate_targets(lock)
    selected = _selected_target(lock, targets, target)

    provenance = _require_mapping(lock.get("baseProvenance"), "baseProvenance")
    for component in ("moltenvk", "wineGecko"):
        _source_pin(provenance.get(component), f"baseProvenance.{component}")
    build = _require_mapping(lock.get("build"), "build")
    _source_pin(build.get("nixpkgs"), "build.nixpkgs")

    resolved = {
        name: _resolve_target(lock, name, overrides)
        for name, overrides in targets.items()
    }
    for name, view in resolved.items():
        _build_mode(view["buildMode"], f"{name}.buildMode")
        if view["buildMode"] == "external":
            if view["deploymentTarget"] != "26.0":
                raise LockError(f"{name}.deploymentTarget must be 26.0")
            _validate_artifact(view["artifact"], f"{name}.artifact")
            if view["baseArtifact"] is not None:
                raise LockError(
                    f"{name}.baseArtifact must be null for an external target"
                )
        else:
            if view["deploymentTarget"] != "15.0":
                raise LockError(f"{name}.deploymentTarget must be 15.0")
            if view["artifact"] is not None:
                raise LockError(f"{name} must not pin an artifact for a build target")
            _validate_base_artifact(view["baseArtifact"], f"{name}.baseArtifact")
        _validate_sources(view["sources"], f"{name}.sources")
        _validate_interface(view["interface"], f"{name}.interface")
        _validate_features(view["features"], f"{name}.features")

    patches = lock.get("patches")
    if not isinstance(patches, list):
        raise LockError("patches must be an array")
    seen_ids: set[str] = set()
    applicability: dict[str, list[str]] = {}
    for index, value in enumerate(patches):
        context = f"patches[{index}]"
        patch = _require_mapping(value, context)
        patch_id = _require_string(patch, "id", context)
        component = _require_string(patch, "component", context)
        family = _require_string(patch, "family", context)
        relative = _require_string(patch, "path", context)
        expected = _require_string(patch, "sha256", context)
        if patch_id in seen_ids:
            raise LockError(f"duplicate patch id: {patch_id}")
        seen_ids.add(patch_id)
        if family not in PATCH_FAMILIES:
            raise LockError(f"unknown patch family: {family}")
        names = _patch_targets(patch, targets, context)
        for name in names:
            if component not in resolved[name]["sources"]:
                raise LockError(
                    f"patch {patch_id} uses {component}, "
                    f"which the {name} target does not build"
                )
        if HASH_PATTERN.fullmatch(expected) is None:
            raise LockError(f"patch {patch_id} has an invalid SHA-256 hash")
        actual = _sha256_file(_contained_file(repository_root, relative))
        if actual != expected:
            raise LockError(f"patch {patch_id} hash mismatch: {actual} != {expected}")
        applicability[patch_id] = names

    for name, view in resolved.items():
        view["patches"] = [
            patch for patch in patches if name in applicability[patch["id"]]
        ]
        if view["buildMode"] == "external" and view["patches"]:
            raise LockError(f"{name} is external and must not receive patches")
    return resolved[selected]


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


def source_directory(component: str, stage: str, lock: dict[str, Any]) -> str:
    """Name a prepared source directory. The default target keeps the legacy name."""

    target = "" if lock["target"] == lock["defaultTarget"] else f"-{lock['target']}"
    return f"{component}{target}-{stage}"


def prepare(
    stage: str,
    destination_root: Path = BUILD_ROOT / "sources",
    *,
    target: str | None = None,
    all_sources: bool = False,
    skip_patches: tuple[str, ...] = (),
) -> None:
    lock = load_lock(target=target)
    if lock["buildMode"] == "external":
        raise LockError(
            f"the {lock['target']} target is built externally; use the arm64 wrapper"
        )
    selected = patches_for_stage(lock, stage)
    declared = {patch["id"] for patch in lock["patches"]}
    unknown = sorted(set(skip_patches) - declared)
    if unknown:
        raise LockError(f"unknown patch to skip: {', '.join(unknown)}")
    components = {patch["component"] for patch in selected}
    if stage == "base" or all_sources:
        components = set(lock["sources"])
    for component in sorted(components):
        source = lock["sources"][component]
        destination = destination_root / source_directory(component, stage, lock)
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
            if patch["id"] in skip_patches:
                info(f"Skipping patch {patch['id']} by request")
                continue
            patch_path = ROOT / patch["path"]
            _run("git", "apply", "--check", str(patch_path), cwd=destination)
            _run("git", "apply", str(patch_path), cwd=destination)
        success(f"Prepared pinned {component} source")


def fetch_base(*, target: str | None = None) -> Path:
    lock = load_lock(target=target)
    artifact = lock["baseArtifact"]
    if artifact is None:
        raise LockError(
            f"the {lock['target']} target builds every component and has no base artifact"
        )
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
    validate_parser = subparsers.add_parser("validate-lock")
    validate_parser.add_argument("--target")
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("stage", choices=STAGES)
    prepare_parser.add_argument("--destination-root", type=Path)
    prepare_parser.add_argument("--target")
    prepare_parser.add_argument(
        "--all-sources",
        action="store_true",
        help="clone every source of the target, not only the ones the stage patches",
    )
    prepare_parser.add_argument(
        "--skip-patch",
        action="append",
        default=[],
        metavar="ID",
        help="leave one patch out; report it in the build log (canary before a rebase)",
    )
    fetch_parser = subparsers.add_parser("fetch-base")
    fetch_parser.add_argument("--target")
    arguments = parser.parse_args()
    try:
        if arguments.command == "validate-lock":
            lock = load_lock(target=arguments.target)
            if arguments.target is None:
                success("Validated runtime.lock.json")
            else:
                success(f"Validated runtime.lock.json for the {lock['target']} target")
        elif arguments.command == "prepare":
            prepare(
                arguments.stage,
                arguments.destination_root or BUILD_ROOT / "sources",
                target=arguments.target,
                all_sources=arguments.all_sources,
                skip_patches=tuple(arguments.skip_patch),
            )
        else:
            print(fetch_base(target=arguments.target))
    except (LockError, OSError, subprocess.CalledProcessError) as caught_error:
        error(str(caught_error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
