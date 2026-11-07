#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Build a runtime artifact from the pinned lock.

Lane code lives in scripts/build_x86.py; shared helpers live in
scripts/build_common.py. This entry point keeps one command surface for both.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_common import Builder, BuildError
from scripts.build_x86 import StageError, build_canary
from scripts.runtime import LockError


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    canary = commands.add_parser("canary", help="build one patch family overlay")
    canary.add_argument("stage", nargs="?", default="combined")
    canary.add_argument("--clean-release", action="store_true")
    commands.add_parser("release", help="build the clean release artifact")
    parsed = parser.parse_args(arguments)
    builder = Builder()
    try:
        if parsed.command == "canary":
            artifact = build_canary(
                builder, parsed.stage, clean_release=parsed.clean_release
            )
        else:
            artifact = build_canary(builder, "combined", clean_release=True)
    except StageError as failure:
        print(f"error: {failure}", file=sys.stderr)
        return 2
    except (BuildError, LockError, OSError, subprocess.CalledProcessError) as failure:
        from scripts.lib.console import error

        error(str(failure))
        return 1
    from scripts.lib.console import success

    success(f"artifact: {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
