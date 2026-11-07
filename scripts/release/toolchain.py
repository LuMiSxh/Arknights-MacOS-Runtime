#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Record the unpinned host toolchain that a release build used."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

BREW_FORMULAE = ("ccache", "just", "mingw-w64", "meson", "ninja")
UNAVAILABLE = "unavailable"

Runner = Callable[[list[str]], str | None]


def run_command(command: list[str]) -> str | None:
    """Return the stripped output of a command, or None if it fails."""

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def collect_toolchain(run: Runner = run_command) -> dict[str, Any]:
    """Collect brew, Xcode, SDK, and macOS versions. Missing values read `unavailable`."""

    brew: dict[str, str] = {name: UNAVAILABLE for name in BREW_FORMULAE}
    listing = run(["brew", "list", "--versions", *BREW_FORMULAE])
    for line in (listing or "").splitlines():
        name, _, versions = line.partition(" ")
        if name in brew and versions.strip():
            brew[name] = versions.strip()
    xcode = run(["xcodebuild", "-version"])
    return {
        "brew": brew,
        "xcode": " ".join(xcode.split("\n")) if xcode else UNAVAILABLE,
        "sdkVersion": run(["xcrun", "--show-sdk-version"]) or UNAVAILABLE,
        "sdkPath": run(["xcrun", "--show-sdk-path"]) or UNAVAILABLE,
        "macOS": run(["sw_vers", "-productVersion"]) or UNAVAILABLE,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    arguments.output.write_text(
        json.dumps(collect_toolchain(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
