# SPDX-License-Identifier: MPL-2.0

"""Validate and prepare the runtime lock: `-m scripts lock COMMAND`."""

import argparse
import subprocess
from pathlib import Path

from scripts.lib.console import error, success
from scripts.lock.model import LockError
from scripts.lock.parse import load_lock
from scripts.lock.sources import BUILD_ROOT, fetch_base, prepare


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="-m scripts lock", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate the lock")
    validate.add_argument("--target")
    commands.add_parser(
        "llvm-mingw", help="print the llvm-mingw URL and SHA-256, empty if unpinned"
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
        elif arguments.command == "llvm-mingw":
            toolchain = load_lock().llvm_mingw
            print(toolchain.url if toolchain else "")
            print(toolchain.sha256 if toolchain else "")
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
