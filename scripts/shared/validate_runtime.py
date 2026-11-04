#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Read-only structural and Mach-O validation for an Arknights MacOS Runtime candidate."""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import re
import struct
import subprocess
from pathlib import Path

if __package__:
    from .lib.console import error, success
    from .runtime import BUILD_ROOT, LOCK_PATH, load_lock
    from .runtime_capabilities import (
        CapabilityContractError,
        validate_packaged_capability_manifest,
        validate_packaged_metalfx_support,
        validate_source_capability_contract,
    )
else:
    from lib.console import error, success
    from runtime import BUILD_ROOT, LOCK_PATH, load_lock
    from runtime_capabilities import (
        CapabilityContractError,
        validate_packaged_capability_manifest,
        validate_packaged_metalfx_support,
        validate_source_capability_contract,
    )


MINOS_PATTERN = re.compile(r"\bminos\s+([0-9]+(?:\.[0-9]+){1,2})")
LEGACY_PAYLOADS = (
    "Wine/lib/wine/i386-windows",
    "Wine/lib/wine/i386-unix",
    "Wine/lib/gstreamer-1.0",
    "DXMT/x32",
)
PE_MACHINE_X86_64 = 0x8664
PE_MACHINE_ARM64EC = 0xA641
PE_MACHINE_ARM64 = 0xAA64
PE_MACHINE_NAMES = {
    PE_MACHINE_X86_64: "x86-64",
    PE_MACHINE_ARM64EC: "ARM64EC",
    PE_MACHINE_ARM64: "AArch64",
}
ARM64_PE_MACHINES = (PE_MACHINE_ARM64EC, PE_MACHINE_ARM64)
PE32_PLUS_MAGIC = 0x20B
PE_LOAD_CONFIG_DIRECTORY = 10
PE_DATA_DIRECTORY_OFFSET = 112
PE_CHPE_METADATA_OFFSET = 0xC8
MEDIA_LIBRARY_PATTERNS = ("libav*", "libsw*", "libx26[45]*", "libaom*", "libSvtAv1*")


class RuntimeValidationError(ValueError):
    """The candidate does not satisfy the locked archive contract."""


def validate_structure(root: Path, required_paths: list[str]) -> None:
    if not root.is_dir():
        raise RuntimeValidationError(f"runtime root is not a directory: {root}")
    resolved_root = root.resolve()
    for relative in required_paths:
        path = root / relative
        if not path.is_file():
            raise RuntimeValidationError(f"missing required file: {relative}")
        try:
            path.resolve(strict=True).relative_to(resolved_root)
        except ValueError as error:
            raise RuntimeValidationError(
                f"required path escapes runtime root: {relative}"
            ) from error

    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        for name in (*directory_names, *file_names):
            path = Path(directory) / name
            if not path.is_symlink():
                continue
            try:
                path.resolve(strict=True).relative_to(resolved_root)
            except (FileNotFoundError, ValueError) as error:
                raise RuntimeValidationError(
                    f"symlink escapes runtime root or is broken: {path.relative_to(root)}"
                ) from error


def _version(value: str) -> tuple[int, ...]:
    return tuple(int(component) for component in value.split("."))


def validate_64_bit_only(root: Path) -> None:
    """Reject the 32-bit Wine/DXMT payloads and the media stack dropped in 0.7.0."""

    for relative in LEGACY_PAYLOADS:
        if (root / relative).exists():
            raise RuntimeValidationError(f"legacy payload must be absent: {relative}")
    for pattern in MEDIA_LIBRARY_PATTERNS:
        for path in (root / "Wine/lib").glob(pattern):
            raise RuntimeValidationError(
                f"media library must be absent: {path.relative_to(root)}"
            )


def validate_link_references(path: Path, output: str) -> None:
    for line in output.splitlines()[1:]:
        reference = line.strip().split(" (", 1)[0]
        if not reference.startswith("/"):
            continue
        if reference.startswith(("/System/Library/", "/usr/lib/")):
            continue
        raise RuntimeValidationError(
            f"{path} has non-relocatable dependency: {reference}"
        )


def _runtime_architecture(required_paths: list[str]) -> str:
    """A lane is ARM64 when its interface names aarch64 Wine module directories."""

    if any("/aarch64-" in path for path in required_paths):
        return "aarch64"
    return "x86_64"


def _pe_section_offset(table: bytes, rva: int) -> int | None:
    """Map a virtual address to a file offset through the section table."""

    for start in range(0, len(table) - 39, 40):
        virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from(
            "<IIII", table, start + 8
        )
        span = max(virtual_size, raw_size)
        if virtual_address <= rva < virtual_address + span:
            return raw_offset + rva - virtual_address
    return None


def _pe_machine(path: Path) -> int:
    """Read the machine type from the PE header.

    An ARM64EC image keeps the x86-64 machine value and marks itself with CHPE
    metadata in the load configuration, so the pointer decides the architecture.
    """

    try:
        with path.open("rb") as file:
            dos = file.read(0x40)
            if len(dos) < 0x40 or dos[:2] != b"MZ":
                raise RuntimeValidationError(f"{path.name} is not a PE file")
            file.seek(int.from_bytes(dos[0x3C:0x40], "little"))
            header = file.read(24)
            if len(header) != 24 or header[:4] != b"PE\0\0":
                raise RuntimeValidationError(f"{path.name} has no PE header")
            machine = int.from_bytes(header[4:6], "little")
            sections = int.from_bytes(header[6:8], "little")
            optional = file.read(int.from_bytes(header[20:22], "little"))
            table = file.read(sections * 40)
            if machine != PE_MACHINE_X86_64:
                return machine
            if len(optional) < PE_DATA_DIRECTORY_OFFSET + 8 * (
                PE_LOAD_CONFIG_DIRECTORY + 1
            ):
                return machine
            if int.from_bytes(optional[:2], "little") != PE32_PLUS_MAGIC:
                return machine
            directory = PE_DATA_DIRECTORY_OFFSET + PE_LOAD_CONFIG_DIRECTORY * 8
            rva, size = struct.unpack_from("<II", optional, directory)
            if not rva or size < PE_CHPE_METADATA_OFFSET + 8:
                return machine
            offset = _pe_section_offset(table, rva)
            if offset is None:
                return machine
            file.seek(offset + PE_CHPE_METADATA_OFFSET)
            if int.from_bytes(file.read(8), "little"):
                return PE_MACHINE_ARM64EC
            return machine
    except OSError as error:
        raise RuntimeValidationError(f"cannot read PE header: {error}") from error


def validate_required_architectures(root: Path, required_paths: list[str]) -> int:
    architecture = _runtime_architecture(required_paths)
    checked = 0
    for relative in required_paths:
        path = root / relative
        kind = subprocess.run(
            ["file", "-b", str(path)], capture_output=True, check=True, text=True
        ).stdout.strip()
        is_pe = relative.startswith("DXMT/") or any(
            f"/{module}-windows/" in relative for module in ("x86_64", "aarch64")
        )
        if is_pe and architecture == "aarch64":
            machine = _pe_machine(path)
            if machine not in ARM64_PE_MACHINES:
                raise RuntimeValidationError(
                    f"{relative} has unexpected PE architecture: "
                    f"{PE_MACHINE_NAMES.get(machine, hex(machine))}"
                )
        else:
            expected = (
                ("PE32+ executable", "x86-64")
                if is_pe
                else ("Mach-O", "arm64" if architecture == "aarch64" else "x86_64")
            )
            if not all(fragment in kind for fragment in expected):
                raise RuntimeValidationError(
                    f"{relative} has unexpected architecture: {kind}"
                )
        if relative.startswith("DXMT/") and path.name in (
            "d3d10core.dll",
            "d3d11.dll",
            "dxgi.dll",
        ):
            # Wine's DOS-stub marker overrides native-first DLL loading. The
            # build recipe clears it for these payloads, but keeps winemetal builtin.
            with path.open("rb") as file:
                file.seek(64)
                marker = file.read(32)
            if marker.startswith((b"Wine builtin DLL\0", b"Wine placeholder DLL\0")):
                raise RuntimeValidationError(
                    f"{relative}: native DXMT payload retains a Wine loader marker; "
                    "apply the build recipe's DOS-stub preparation"
                )
        checked += 1
    return checked


def validate_macho_targets(
    root: Path, maximum: str, baseline_root: Path | None = None
) -> tuple[int, int]:
    checked = 0
    inherited = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        kind = subprocess.run(
            ["file", "-b", str(path)], capture_output=True, check=True, text=True
        ).stdout
        if "Mach-O" not in kind:
            continue
        checked += 1
        links = subprocess.run(
            ["otool", "-L", str(path)], capture_output=True, check=True, text=True
        ).stdout
        validate_link_references(path.relative_to(root), links)
        output = subprocess.run(
            ["vtool", "-show-build", str(path)],
            capture_output=True,
            check=True,
            text=True,
        ).stdout
        versions = MINOS_PATTERN.findall(output)
        if not versions:
            raise RuntimeValidationError(
                f"Mach-O has no readable minimum target: {path.relative_to(root)}"
            )
        for minimum in versions:
            if _version(minimum) > _version(maximum):
                baseline = (
                    baseline_root / path.relative_to(root) if baseline_root else None
                )
                if (
                    baseline
                    and baseline.is_file()
                    and filecmp.cmp(path, baseline, shallow=False)
                ):
                    inherited += 1
                    continue
                raise RuntimeValidationError(
                    f"{path.relative_to(root)} requires macOS {minimum}, newer than {maximum}"
                )
    return checked, inherited


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--target")
    parser.add_argument("--require-capabilities", action="store_true")
    parser.add_argument(
        "--require-64-bit-only",
        action="store_true",
        help="reject i386, DXMT x32, GStreamer, and FFmpeg payloads (clean builds)",
    )
    arguments = parser.parse_args()
    lock = load_lock(LOCK_PATH, target=arguments.target)
    required_paths = [
        *lock["interface"]["executables"],
        *lock["interface"]["requiredFiles"],
    ]
    try:
        source_manifest = validate_source_capability_contract(lock, LOCK_PATH.parent)
        validate_packaged_capability_manifest(
            arguments.runtime,
            manifest_path=lock["interface"]["runtimeCapabilities"],
            source_manifest=source_manifest,
            required=arguments.require_capabilities,
        )
        validate_structure(arguments.runtime, required_paths)
        if arguments.require_64_bit_only:
            validate_64_bit_only(arguments.runtime)
        architecture_count = validate_required_architectures(
            arguments.runtime, required_paths
        )
        validate_packaged_metalfx_support(arguments.runtime, source_manifest)
        macho_count, inherited_count = validate_macho_targets(
            arguments.runtime, lock["deploymentTarget"], arguments.baseline
        )
    except (
        RuntimeValidationError,
        CapabilityContractError,
        OSError,
        subprocess.CalledProcessError,
    ) as caught_error:
        error(str(caught_error))
        return 1
    reports = BUILD_ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    report = reports / f"{arguments.runtime.parent.name}-validation.json"
    report.write_text(
        json.dumps(
            {
                "runtime": str(arguments.runtime.resolve()),
                "target": lock["target"],
                "deploymentTarget": lock["deploymentTarget"],
                "requiredArchitecturesChecked": architecture_count,
                "machoFilesChecked": macho_count,
                "inheritedMachOAboveTarget": inherited_count,
                "releaseEligible": inherited_count == 0,
                "status": "valid" if inherited_count == 0 else "valid-canary",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    success(f"Validated {macho_count} Mach-O files")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
