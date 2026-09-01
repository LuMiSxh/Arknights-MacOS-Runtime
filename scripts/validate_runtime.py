#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Read-only structural and Mach-O validation for an Arknights MacOS Runtime candidate."""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import re
import subprocess
from pathlib import Path

if __package__:
    from .lib.console import error, success
    from .runtime import BUILD_ROOT, LOCK_PATH, load_lock
else:
    from lib.console import error, success
    from runtime import BUILD_ROOT, LOCK_PATH, load_lock


MINOS_PATTERN = re.compile(r"\bminos\s+([0-9]+(?:\.[0-9]+){1,2})")


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


def validate_required_architectures(root: Path, required_paths: list[str]) -> int:
    checked = 0
    for relative in required_paths:
        path = root / relative
        kind = subprocess.run(
            ["file", "-b", str(path)], capture_output=True, check=True, text=True
        ).stdout.strip()
        if relative.startswith("DXMT/x32/"):
            expected = ("PE32 executable", "Intel 80386")
        elif relative.startswith("DXMT/x64/") or "/x86_64-windows/" in relative:
            expected = ("PE32+ executable", "x86-64")
        else:
            expected = ("Mach-O", "x86_64")
        if not all(fragment in kind for fragment in expected):
            raise RuntimeValidationError(
                f"{relative} has unexpected architecture: {kind}"
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
    arguments = parser.parse_args()
    lock = load_lock(LOCK_PATH)
    required_paths = [
        *lock["interface"]["executables"],
        *lock["interface"]["requiredFiles"],
    ]
    try:
        validate_structure(arguments.runtime, required_paths)
        architecture_count = validate_required_architectures(
            arguments.runtime, required_paths
        )
        macho_count, inherited_count = validate_macho_targets(
            arguments.runtime, lock["deploymentTarget"], arguments.baseline
        )
    except (
        RuntimeValidationError,
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
