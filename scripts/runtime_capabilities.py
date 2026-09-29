# SPDX-License-Identifier: MPL-2.0

"""Validate the runtime capability manifest against its pinned patch recipe."""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Any

MAXIMUM_CAPABILITY_MANIFEST_BYTES = 4 * 1_024
CAPABILITY_KEYS = {"dxmtMaximumFrameLatency", "hardwareCursor"}
LATENCY_KEYS = {"minimum", "maximum", "defaultValue"}
LATENCY_PATTERN = re.compile(
    r'getEnvVar\("ARKNIGHTS_RUNTIME_DXMT_MAX_FRAME_LATENCY"\).*?'
    r"configured\.size\(\)\s*==\s*1\s*&&\s*"
    r"configured\.front\(\)\s*>=\s*'([0-3])'\s*&&\s*"
    r"configured\.front\(\)\s*<=\s*'([0-3])'.*?"
    r"return\s+uint32_t\{([0-3])\};",
    re.DOTALL,
)


class CapabilityContractError(ValueError):
    """The runtime capability manifest does not match the pinned recipe."""


def read_capability_manifest_bytes(path: Path) -> bytes:
    if path.is_symlink():
        raise CapabilityContractError("capability manifest must not be a symlink")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise CapabilityContractError(f"cannot read capability manifest: {error}") from error
    try:
        with os.fdopen(descriptor, "rb") as source:
            status = os.fstat(source.fileno())
            if not stat.S_ISREG(status.st_mode):
                raise CapabilityContractError(
                    "capability manifest must be a regular file"
                )
            if status.st_size < 0 or status.st_size > MAXIMUM_CAPABILITY_MANIFEST_BYTES:
                raise CapabilityContractError("capability manifest exceeds the size limit")
            data = source.read(MAXIMUM_CAPABILITY_MANIFEST_BYTES + 1)
            if len(data) > MAXIMUM_CAPABILITY_MANIFEST_BYTES:
                raise CapabilityContractError("capability manifest exceeds the size limit")
            return data
    except OSError as error:
        raise CapabilityContractError(f"cannot read capability manifest: {error}") from error


def load_capability_manifest(path: Path) -> dict[str, Any]:
    data = read_capability_manifest_bytes(path)
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CapabilityContractError(f"cannot decode capability manifest: {error}") from error
    return validate_manifest_shape(value)


def validate_manifest_shape(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"schemaVersion", "capabilities"}:
        raise CapabilityContractError("manifest must contain only schemaVersion and capabilities")
    schema_version = value["schemaVersion"]
    if type(schema_version) is not int or schema_version != 1:
        raise CapabilityContractError("capability manifest schemaVersion must be 1")

    capabilities = value["capabilities"]
    if not isinstance(capabilities, dict) or set(capabilities) != CAPABILITY_KEYS:
        raise CapabilityContractError("manifest capabilities have an invalid shape")
    latency = capabilities["dxmtMaximumFrameLatency"]
    if not isinstance(latency, dict) or set(latency) != LATENCY_KEYS:
        raise CapabilityContractError("frame latency capability has an invalid shape")
    minimum, maximum, default = (
        latency["minimum"],
        latency["maximum"],
        latency["defaultValue"],
    )
    if any(type(number) is not int for number in (minimum, maximum, default)):
        raise CapabilityContractError("frame latency values must be integers")
    if (
        minimum < 0
        or maximum > 3
        or minimum > maximum
        or default != 3
        or not minimum <= default <= maximum
    ):
        raise CapabilityContractError("frame latency range must include default 3 within 0..3")
    if type(capabilities["hardwareCursor"]) is not bool:
        raise CapabilityContractError("hardwareCursor capability must be a boolean")
    return value


def validate_capability_contract(
    manifest: dict[str, Any], *, latency_patch: str, hardware_cursor_patch: str
) -> None:
    value = validate_manifest_shape(manifest)
    latency = value["capabilities"]["dxmtMaximumFrameLatency"]
    match = LATENCY_PATTERN.search(latency_patch)
    if match is None or "max_latency_(configured_max_latency())" not in latency_patch:
        raise CapabilityContractError("pinned DXMT latency patch has unknown semantics")
    actual = tuple(int(component) for component in match.groups())
    expected = (latency["minimum"], latency["maximum"], latency["defaultValue"])
    if actual != expected:
        raise CapabilityContractError(
            "manifest frame latency range does not match the pinned DXMT latency patch"
        )

    if value["capabilities"]["hardwareCursor"]:
        added_source = "\n".join(
            line[1:]
            for line in hardware_cursor_patch.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        gate = re.search(
            r"static BOOL arknights_runtime_hardware_cursor_enabled\(void\)\s*\{(.*?)\n\}",
            added_source,
            re.DOTALL,
        )
        if (
            gate is None
            or 'getenv( "ARKNIGHTS_RUNTIME_HARDWARE_CURSOR" )' not in gate.group(1)
            or '!strcmp( setting, "1" )' not in gate.group(1)
            or "arknights_runtime_hardware_cursor_enabled()" not in added_source
            or "a9d41799f1af1868f2db495671227cd4.bin" not in added_source
            or "f7bcd64480c4566f25d65d642f5fba95.bin" not in added_source
        ):
            raise CapabilityContractError(
                "pinned Wine hardware-cursor patch has unknown semantics"
            )


def _manifest_path(lock: dict[str, Any]) -> str:
    interface = lock.get("interface")
    if not isinstance(interface, dict):
        raise CapabilityContractError("runtime lock has no interface object")
    value = interface.get("runtimeCapabilities")
    if not isinstance(value, str) or not value:
        raise CapabilityContractError("runtime lock has no runtimeCapabilities path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise CapabilityContractError("runtimeCapabilities path must be safe and relative")
    return value


def validate_source_capability_contract(
    lock: dict[str, Any], repository_root: Path
) -> dict[str, Any]:
    relative_path = _manifest_path(lock)
    manifest = load_capability_manifest(repository_root / relative_path)
    patches = lock.get("patches")
    if not isinstance(patches, list):
        raise CapabilityContractError("runtime lock patches must be an array")
    by_family: dict[str, dict[str, Any]] = {}
    for family in ("cursor", "hardware-cursor"):
        matches = [
            patch
            for patch in patches
            if isinstance(patch, dict) and patch.get("family") == family
        ]
        if len(matches) != 1:
            raise CapabilityContractError(
                f"runtime lock must contain one {family} patch for capability validation"
            )
        by_family[family] = matches[0]
    try:
        latency_patch = (
            repository_root / by_family["cursor"]["path"]
        ).read_text(encoding="utf-8")
        hardware_cursor_patch = (
            repository_root / by_family["hardware-cursor"]["path"]
        ).read_text(encoding="utf-8")
    except (KeyError, OSError, TypeError) as error:
        raise CapabilityContractError(f"cannot read pinned capability patch: {error}") from error
    validate_capability_contract(
        manifest,
        latency_patch=latency_patch,
        hardware_cursor_patch=hardware_cursor_patch,
    )
    return manifest


def validate_packaged_capability_manifest(
    runtime_root: Path,
    *,
    manifest_path: str,
    source_manifest: dict[str, Any],
    required: bool,
) -> None:
    relative_path = PurePosixPath(manifest_path)
    if relative_path.is_absolute() or any(
        part in ("", ".", "..") for part in relative_path.parts
    ):
        raise CapabilityContractError("runtime capability path must be safe and relative")
    package_path = runtime_root.joinpath(*relative_path.parts)
    if not package_path.exists() and not package_path.is_symlink():
        if required:
            raise CapabilityContractError("runtime package is missing its capability manifest")
        return
    manifest = load_capability_manifest(package_path)
    if manifest != source_manifest:
        raise CapabilityContractError(
            "packaged capability manifest does not match the pinned runtime recipe"
        )
