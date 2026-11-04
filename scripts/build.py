#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Build a runtime artifact from the pinned lock.

Lane code lives in scripts/x86 and scripts/arm; shared helpers live in
scripts/shared. This entry point keeps one command surface for both.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.arm.build import build_arm64
from scripts.shared.build import Builder, BuildError
from scripts.shared.runtime import LockError
from scripts.x86.build import build_canary


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    canary = commands.add_parser("canary", help="build one patch family overlay")
    canary.add_argument("stage", nargs="?", default="combined")
    canary.add_argument("--clean-release", action="store_true")
    commands.add_parser("release", help="build the clean release artifact")
    arm64 = commands.add_parser("arm64", help="build the native-arm64 canary")
    arm64.add_argument("--resume", action="store_true")
    arm64.add_argument(
        "--no-patches", action="store_true", help="build the unpatched base sources"
    )
    parsed = parser.parse_args(arguments)
    builder = Builder()
    try:
        if parsed.command == "canary":
            artifact = build_canary(
                builder, parsed.stage, clean_release=parsed.clean_release
            )
        elif parsed.command == "release":
            artifact = build_canary(builder, "combined", clean_release=True)
        else:
            artifact = build_arm64(
                builder, resume=parsed.resume, patched=not parsed.no_patches
            )
    except BuildError as failure:
        from scripts.x86.build import STAGE_HINT

        print(f"error: {failure}", file=sys.stderr)
        return 2 if str(failure) == STAGE_HINT else 1
    except (LockError, OSError, subprocess.CalledProcessError) as failure:
        from scripts.shared.lib.console import error

        error(str(failure))
        return 1
    from scripts.shared.lib.console import success

    success(f"artifact: {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
