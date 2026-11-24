# SPDX-License-Identifier: MPL-2.0

"""Validate, export, and prepare the runtime lock: `python -m scripts.lock COMMAND`."""

import argparse
import subprocess
from pathlib import Path

from scripts.lib.console import error, success
from scripts.lock.model import ROOT, LockError
from scripts.lock.parse import load_lock
from scripts.lock.patches import export_wine_build_new
from scripts.lock.sources import BUILD_ROOT, fetch_base, prepare

EXPORT_PATH = ROOT / "wine-build-new" / "lock.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.lock", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate the lock")
    validate.add_argument("--target")
    export = commands.add_parser("export", help="write wine-build-new/lock.json")
    export.add_argument(
        "--check",
        action="store_true",
        help="fail when the committed export differs from the lock",
    )
    prepare_parser = commands.add_parser("prepare", help="clone and patch the sources")
    prepare_parser.add_argument("--destination-root", type=Path)
    prepare_parser.add_argument("--target")
    prepare_parser.add_argument(
        "--all-sources",
        action="store_true",
        help="clone every source of the target, not only the ones the patches change",
    )
    prepare_parser.add_argument(
        "--skip-patch",
        action="append",
        default=[],
        metavar="ID",
        help="leave one patch out; report it in the build log (canary before a rebase)",
    )
    fetch = commands.add_parser("fetch-base", help="download the base archive")
    fetch.add_argument("--target")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "validate":
            lane = load_lock().lane(arguments.target)
            success(f"Validated runtime.lock.json for the {lane.name} target")
        elif arguments.command == "export":
            text = export_wine_build_new(load_lock())
            if not arguments.check:
                EXPORT_PATH.write_text(text, encoding="utf-8")
                success("Wrote wine-build-new/lock.json")
            elif EXPORT_PATH.read_text(encoding="utf-8") != text:
                error("wine-build-new/lock.json is stale; run `just lock-export`")
                return 1
            else:
                success("wine-build-new/lock.json matches runtime.lock.json")
        elif arguments.command == "prepare":
            prepare(
                arguments.destination_root or BUILD_ROOT / "sources",
                target=arguments.target,
                all_sources=arguments.all_sources,
                skip_patches=tuple(arguments.skip_patch),
            )
        else:
            print(fetch_base(target=arguments.target))
    except (LockError, OSError, subprocess.CalledProcessError) as caught:
        error(str(caught))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
