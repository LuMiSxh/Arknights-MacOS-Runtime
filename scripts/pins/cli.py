# SPDX-License-Identifier: MPL-2.0

"""Commands of the pins package: `-m scripts pins update|check|export`.

`update` resolves the newest upstream state, rewrites `runtime.lock.json`, and
rewrites each mention of a pin. `check` verifies offline that every mention agrees
with the lock. `export` regenerates `wine-build-new/lock.json` from the lock.
"""

import argparse
import copy
import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from scripts.lib.console import error, info, success, warning
from scripts.lib.github import Fetch, GitHubError
from scripts.lib.github import fetch as github_fetch
from scripts.lock.model import LockError
from scripts.lock.parse import load_lock
from scripts.lock.patches import export_wine_build_new
from scripts.pins import LOCK_NAME, ROOT, SHORT_LENGTH, PinError, read_lock
from scripts.pins.mentions import (
    ALLOWLIST,
    pins_from_lock,
    plan_rewrites,
    run_check,
)
from scripts.pins.resolve import (
    ALL_COMPONENTS,
    COMPONENTS,
    RESOLVERS,
    Runner,
    apply_state,
    guard_patches,
    resolve_wine_arm64,
    run_process,
)

# --- Update and check -------------------------------------------------------------


@dataclass(frozen=True)
class Outcome:
    component: str
    old: str
    new: str
    status: str
    reason: str = ""


@dataclass(frozen=True)
class UpdateResult:
    outcomes: list[Outcome]
    written: list[str]


def _describe(component: str, pins: dict[str, str]) -> str:
    return {
        "wine": f"{pins['wine.version']} ({pins['wine.short']})",
        "dxmt": pins["dxmt.version"],
        "base": f"{pins['base.tag']} ({pins['base.sha256'][:SHORT_LENGTH]})",
        "nixpkgs": pins["nixpkgs.short"],
        "wine-arm64": f"{pins['wine-arm64.release']} ({pins['wine-arm64.sha256'][:SHORT_LENGTH]})",
    }[component]


def run_update(
    root: Path,
    only: tuple[str, ...],
    *,
    dry_run: bool,
    fetch: Fetch,
    fetch_catalog: Callable[[str], bytes] | None = None,
    fetch_archive: Callable[[str, Path], None] | None = None,
    release_id: str | None = None,
    run: Runner = run_process,
    allowlist: dict[str, tuple[str, ...]] = ALLOWLIST,
) -> UpdateResult:
    """Resolve, guard, and rewrite. Raise PinError before any write on a failure."""

    old_lock = read_lock(root)
    old_pins = pins_from_lock(old_lock)
    new_lock = copy.deepcopy(old_lock)
    outcomes: list[Outcome] = []
    for component in ALL_COMPONENTS:
        if component not in only:
            continue
        if component == "wine-arm64":
            state = resolve_wine_arm64(
                fetch_catalog, release_id=release_id, fetch_archive=fetch_archive
            )
        else:
            state = RESOLVERS[component](fetch)
        trial = copy.deepcopy(old_lock)
        apply_state(trial, component, state)
        before = _describe(component, old_pins)
        after = _describe(component, pins_from_lock(trial))
        if before == after and trial == old_lock:
            outcomes.append(Outcome(component, before, after, "current"))
            continue
        if component in ("wine", "dxmt"):
            reason = guard_patches(root, old_lock, component, state.commit, run)
            if reason is not None:
                outcomes.append(Outcome(component, before, before, "kept", reason))
                continue
        apply_state(new_lock, component, state)
        outcomes.append(Outcome(component, before, after, "updated"))

    new_pins = pins_from_lock(new_lock)
    changes, _ = plan_rewrites(root, old_pins, new_pins, allowlist)
    lock_text = json.dumps(new_lock, indent=2) + "\n"
    if lock_text != (root / LOCK_NAME).read_text(encoding="utf-8"):
        changes[root / LOCK_NAME] = lock_text
    if not dry_run:
        for path, text in changes.items():
            path.write_text(text, encoding="utf-8")
    written = sorted(path.relative_to(root).as_posix() for path in changes)
    return UpdateResult(outcomes, written)


def format_table(outcomes: list[Outcome]) -> str:
    rows = [("component", "old", "new", "status", "reason")]
    rows += [(o.component, o.old, o.new, o.status, o.reason) for o in outcomes]
    widths = [max(len(row[column]) for row in rows) for column in range(4)]
    return "\n".join(
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths)) + "  " + row[4]
        for row in rows
    ).rstrip()


FOLLOW_UPS = (
    "Review the patch registry gates in docs/patch-registry.md for the new commits.",
    "Review the DXMT and Wine license statements if the upstream license can change.",
    "Dispatch the release workflow, as docs/releasing.md describes.",
    "Pin the new release in the client repository with `just runtime update TAG`.",
)


def _post_checks(root: Path) -> bool:
    commands = (
        [sys.executable, "-m", "scripts", "lock", "validate"],
        [sys.executable, "-m", "scripts", "release", "licenses", "generate", "--check"],
    )
    clean = True
    for command in commands:
        result = subprocess.run(
            command, cwd=root, capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            clean = False
            error(f"{' '.join(command[1:])} failed:\n{result.stdout}{result.stderr}")
    return clean


EXPORT_PATH = ROOT / "wine-build-new" / "lock.json"


def run_export(*, check: bool) -> int:
    """Write `wine-build-new/lock.json`, or with `check` fail when it is stale."""

    try:
        text = export_wine_build_new(load_lock())
    except (LockError, OSError) as failure:
        error(str(failure))
        return 1
    if not check:
        EXPORT_PATH.write_text(text, encoding="utf-8")
        success("Wrote wine-build-new/lock.json")
    elif EXPORT_PATH.read_text(encoding="utf-8") != text:
        error("wine-build-new/lock.json is stale; run `just pins export`")
        return 1
    else:
        success("wine-build-new/lock.json matches runtime.lock.json")
    return 0


def main(argv: list[str] | None = None, fetch: Fetch = github_fetch) -> int:
    parser = argparse.ArgumentParser(
        prog="-m scripts pins", description=__doc__.split("\n\n")[0]
    )
    commands = parser.add_subparsers(dest="command", required=True)
    update = commands.add_parser(
        "update", help="resolve the newest pins and rewrite mentions"
    )
    update.add_argument("--dry-run", action="store_true", help="write nothing")
    update.add_argument(
        "--only",
        default=",".join(COMPONENTS),
        help=f"comma-separated components of {', '.join(ALL_COMPONENTS)}",
    )
    update.add_argument(
        "--release",
        metavar="ID",
        help="arm64 catalog release id to pin instead of the newest one",
    )
    commands.add_parser("check", help="verify that all mentions agree with the lock")
    export = commands.add_parser("export", help="write wine-build-new/lock.json")
    export.add_argument(
        "--check",
        action="store_true",
        help="fail when the committed export differs from the lock",
    )
    arguments = parser.parse_args(argv)

    if arguments.command == "export":
        return run_export(check=arguments.check)
    try:
        if arguments.command == "check":
            problems = run_check(ROOT)
            for problem in problems:
                error(problem)
            if problems:
                return 1
            success("All pin mentions agree with runtime.lock.json.")
            return 0

        only = tuple(name.strip() for name in arguments.only.split(",") if name.strip())
        unknown = sorted(set(only) - set(ALL_COMPONENTS))
        if unknown or not only:
            parser.error(
                f"--only takes {', '.join(ALL_COMPONENTS)}; got {unknown or 'nothing'}"
            )
        if arguments.release and "wine-arm64" not in only:
            parser.error("--release needs --only wine-arm64")
        result = run_update(
            ROOT,
            only,
            dry_run=arguments.dry_run,
            fetch=fetch,
            release_id=arguments.release,
        )
    except (PinError, GitHubError) as failure:
        error(str(failure))
        error("Nothing was written.")
        return 1

    print(format_table(result.outcomes))
    for outcome in result.outcomes:
        if outcome.status == "kept":
            warning(f"{outcome.component} kept at {outcome.old}: {outcome.reason}")
    if "base" in only and any(
        o.component == "base" and o.status == "updated" for o in result.outcomes
    ):
        warning(
            "baseProvenance (MoltenVK, Wine Gecko) is unchanged. The release does not expose it."
        )
    verb = "Would write" if arguments.dry_run else "Wrote"
    info(f"{verb} {len(result.written)} file(s): {', '.join(result.written) or 'none'}")
    if arguments.dry_run or not result.written:
        return 0
    if not _post_checks(ROOT):
        return 1
    success("Lock validation and the license check pass.")
    for step in FOLLOW_UPS:
        info(f"Next: {step}")
    return 0
