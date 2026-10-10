#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Update the upstream pins of the runtime and every mention of them.

`update` resolves the newest upstream state, rewrites `runtime.lock.json`, and
rewrites each mention of a pin. `check` verifies offline that every mention agrees
with the lock.

Components and their rule:

- wine: tip of the highest branch named `wine11<N>` in dappermint/winecx. The version
  is the content of the `VERSION` file at that commit.
- dxmt: head of the default branch of 3Shain/dxmt. The version has the form of
  `git describe`: `<latest tag>-<commits since tag>-g<short sha>`.
- base: newest dappermint/Whisky release with a `Libraries.tar.gz` asset. The hash is
  the `digest` of the asset, so the script never downloads the archive. The recipe
  commit is the commit of the tag `runtime-<release tag>` in dappermint/winecx-gptk.
- nixpkgs: tip of `NIXPKGS_CHANNEL`.

`NIXPKGS_CHANNEL` stays at `nixos-26.05`. This is the last NixOS release with
x86_64-darwin support, and the runtime build needs it. Raising the channel is a manual
decision: change the constant, then review the library closure.

The guard keeps the current pin of wine or dxmt when a patch of that component no
longer applies to the new commit.

Mentions use two mechanisms:

- Markdown files hold generated markers. `<!-- pin:KEY -->text<!-- /pin -->` holds one
  value. `KEY|code` wraps the value in a code span. `<!-- pin-block:NAME -->` holds a
  generated block. Fenced code blocks and code spans with a comment are ignored.
- Other files appear in `ALLOWLIST`. `update` replaces the old value of each listed pin
  with the new one. `check` fails when a file lacks the value of the lock.
"""

from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if __package__:
    from ..lib.console import error, info, success, warning
else:
    if str(REPOSITORY_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))
    from lib.console import error, info, success, warning

LOCK_NAME = "runtime.lock.json"
COMPONENTS = ("wine", "dxmt", "base", "nixpkgs")
NIXPKGS_CHANNEL = "nixos-26.05"
WINE_REPOSITORY = "dappermint/winecx"
WINE_BRANCH = re.compile(r"wine11([0-9]+)")
DXMT_REPOSITORY = "3Shain/dxmt"
BASE_REPOSITORY = "dappermint/Whisky"
BASE_ASSET = "Libraries.tar.gz"
RECIPE_REPOSITORY = "dappermint/winecx-gptk"
RECIPE_TAG_PREFIX = "runtime-"
NIXPKGS_REPOSITORY = "NixOS/nixpkgs"
API_ROOT = "https://api.github.com"
PAGE_SIZE = 100
SHORT_LENGTH = 7
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
SEMVER_TAG = re.compile(r"v?(\d+(?:\.\d+)*)")
DESCRIBE = re.compile(r"(?P<tag>.+)-(?P<count>\d+)-g[0-9a-f]+")
DOWNLOAD_TAG = re.compile(r"/releases/download/(?P<tag>[^/]+)/")

# Files that are not Markdown. Each entry lists the pins that the file states.
ALLOWLIST: dict[str, tuple[str, ...]] = {
    "LICENSES/index.json": (
        "wine.commit",
        "dxmt.commit",
        "nixpkgs.commit",
        "wine.version",
        "dxmt.version",
    ),
    "LICENSES/notices/wine.txt": ("wine.commit", "wine.version"),
    "LICENSES/notices/wine-bundled.txt": ("wine.commit",),
    "LICENSES/notices/dxmt.txt": ("dxmt.commit", "dxmt.version", "dxmt.build"),
    "LICENSES/notices/dxmt-toolchain.txt": ("dxmt.commit", "dxmt.version"),
    "LICENSES/notices/dxmt-unverified.txt": ("dxmt.commit", "dxmt.version"),
    "LICENSES/notices/dxmt-vendored.txt": ("dxmt.commit", "dxmt.version"),
}
SKIPPED_DIRECTORIES = frozenset((".git", ".venv", ".build", "node_modules"))

# Documentation may show marker syntax in a fenced block or in a code span.
FENCE = re.compile(r"^(```|~~~).*?^\1[^\n]*$|`[^`\n]*`", re.MULTILINE | re.DOTALL)
INLINE_MARKER = re.compile(
    r"<!-- pin:(?P<key>[\w.]+)(?:\|(?P<format>code))? -->(?P<body>.*?)<!-- /pin -->"
)
BLOCK_MARKER = re.compile(
    r"<!-- pin-block:(?P<name>[\w-]+) -->\n(?P<body>.*?)<!-- /pin-block -->",
    re.DOTALL,
)

Fetch = Callable[[str], Any]
Runner = Callable[[list[str]], tuple[int, str]]


class PinError(RuntimeError):
    """A pin cannot be resolved, rewritten, or verified."""


# --- GitHub access ---------------------------------------------------------------


def github_fetch(path: str) -> Any:
    """Return the decoded JSON of a GitHub API path. Use a token when one is set."""

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "arknights-macos-runtime-pins",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(API_ROOT + path, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as failure:
        if (
            failure.code in (403, 429)
            and failure.headers.get("X-RateLimit-Remaining") == "0"
        ):
            raise PinError(
                "GitHub API rate limit reached. Set GITHUB_TOKEN or GH_TOKEN and retry."
            ) from failure
        raise PinError(f"GitHub API returned {failure.code} for {path}") from failure
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as failure:
        raise PinError(f"cannot read {path}: {failure}") from failure


def paged(fetch: Fetch, path: str) -> list[Any]:
    """Collect every page of a list endpoint."""

    items: list[Any] = []
    separator = "&" if "?" in path else "?"
    page = 1
    while True:
        batch = fetch(f"{path}{separator}per_page={PAGE_SIZE}&page={page}")
        items.extend(batch)
        if len(batch) < PAGE_SIZE:
            return items
        page += 1


def _commit(value: Any, description: str) -> str:
    if not isinstance(value, str) or COMMIT_PATTERN.fullmatch(value) is None:
        raise PinError(f"{description} is not a full commit hash: {value!r}")
    return value


def branch_tip(fetch: Fetch, repository: str, branch: str) -> str:
    reference = fetch(f"/repos/{repository}/git/ref/heads/{branch}")
    return _commit(reference.get("object", {}).get("sha"), f"{repository}@{branch}")


# --- Resolution -------------------------------------------------------------------


@dataclass(frozen=True)
class WineState:
    commit: str
    version: str


@dataclass(frozen=True)
class DxmtState:
    commit: str
    version: str


@dataclass(frozen=True)
class BaseState:
    url: str
    sha256: str
    recipe_commit: str


@dataclass(frozen=True)
class NixpkgsState:
    commit: str


def resolve_wine(fetch: Fetch) -> WineState:
    branches = paged(fetch, f"/repos/{WINE_REPOSITORY}/branches")
    candidates = [
        (int(match[1]), branch)
        for branch in branches
        if (match := WINE_BRANCH.fullmatch(branch["name"]))
    ]
    if not candidates:
        raise PinError(f"{WINE_REPOSITORY} has no branch named wine11<N>")
    _, branch = max(candidates, key=lambda candidate: candidate[0])
    commit = _commit(branch["commit"]["sha"], f"{WINE_REPOSITORY}@{branch['name']}")
    content = fetch(f"/repos/{WINE_REPOSITORY}/contents/VERSION?ref={commit}")
    text = base64.b64decode(content["content"]).decode("utf-8")
    version = re.search(r"\d+(?:\.\d+)+", text)
    if version is None:
        raise PinError(f"the VERSION file of {WINE_REPOSITORY}@{commit} has no version")
    return WineState(commit, version[0])


def _tag_key(name: str) -> tuple[int, ...]:
    match = SEMVER_TAG.fullmatch(name)
    return tuple(int(part) for part in match[1].split(".")) if match else ()


def resolve_dxmt(fetch: Fetch) -> DxmtState:
    default = fetch(f"/repos/{DXMT_REPOSITORY}")["default_branch"]
    commit = branch_tip(fetch, DXMT_REPOSITORY, default)
    names = [tag["name"] for tag in paged(fetch, f"/repos/{DXMT_REPOSITORY}/tags")]
    for name in sorted(filter(_tag_key, names), key=_tag_key, reverse=True):
        comparison = fetch(f"/repos/{DXMT_REPOSITORY}/compare/{name}...{commit}")
        if comparison.get("status") not in ("ahead", "identical"):
            continue
        tag = name.removeprefix("v")
        count = int(comparison["ahead_by"])
        version = f"{tag}-{count}-g{commit[:SHORT_LENGTH]}" if count else tag
        return DxmtState(commit, version)
    raise PinError(f"no tag of {DXMT_REPOSITORY} is an ancestor of {commit}")


def resolve_base(fetch: Fetch) -> BaseState:
    for release in paged(fetch, f"/repos/{BASE_REPOSITORY}/releases"):
        if release.get("draft"):
            continue
        asset = next((a for a in release["assets"] if a["name"] == BASE_ASSET), None)
        if asset is not None:
            break
    else:
        raise PinError(f"no release of {BASE_REPOSITORY} has a {BASE_ASSET} asset")
    tag = release["tag_name"]
    digest = asset.get("digest")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise PinError(
            f"the {BASE_ASSET} asset of {tag} has no sha256 digest in the API. "
            "Compute the hash by hand and edit the lock."
        )
    reference = fetch(
        f"/repos/{RECIPE_REPOSITORY}/git/ref/tags/{RECIPE_TAG_PREFIX}{tag}"
    )
    target = reference.get("object", {})
    if target.get("type") == "tag":
        target = fetch(f"/repos/{RECIPE_REPOSITORY}/git/tags/{target['sha']}")["object"]
    recipe = _commit(
        target.get("sha"), f"{RECIPE_REPOSITORY} tag {RECIPE_TAG_PREFIX}{tag}"
    )
    return BaseState(
        asset["browser_download_url"], digest.removeprefix("sha256:"), recipe
    )


def resolve_nixpkgs(fetch: Fetch) -> NixpkgsState:
    return NixpkgsState(branch_tip(fetch, NIXPKGS_REPOSITORY, NIXPKGS_CHANNEL))


RESOLVERS: dict[str, Callable[[Fetch], Any]] = {
    "wine": resolve_wine,
    "dxmt": resolve_dxmt,
    "base": resolve_base,
    "nixpkgs": resolve_nixpkgs,
}


# --- Lock and pin values ----------------------------------------------------------


def apply_state(lock: dict[str, Any], component: str, state: Any) -> None:
    """Write a resolved state into the lock."""

    if component in ("wine", "dxmt"):
        lock["sources"][component].update(commit=state.commit, version=state.version)
    elif component == "base":
        artifact = lock["baseArtifact"]
        artifact.update(url=state.url, sha256=state.sha256)
        artifact["recipe"]["commit"] = state.recipe_commit
    else:
        lock["build"]["nixpkgs"]["commit"] = state.commit


def _slug(repository: str) -> str:
    return repository.removeprefix("https://github.com/").removesuffix(".git")


def _link(repository: str, commit: str) -> str:
    slug = _slug(repository)
    short = commit[:SHORT_LENGTH]
    return f"[`{slug}@{short}`](https://github.com/{slug}/tree/{commit})"


def pins_from_lock(lock: dict[str, Any]) -> dict[str, str]:
    """Derive every pin key that a marker or an allowlisted file may name."""

    pins: dict[str, str] = {}
    for name in ("wine", "dxmt"):
        source = lock["sources"][name]
        pins[f"{name}.commit"] = source["commit"]
        pins[f"{name}.short"] = source["commit"][:SHORT_LENGTH]
        pins[f"{name}.version"] = source["version"]
        pins[f"{name}.link"] = _link(source["repository"], source["commit"])
    describe = DESCRIBE.fullmatch(pins["dxmt.version"])
    pins["dxmt.tag"] = describe["tag"] if describe else pins["dxmt.version"]
    pins["dxmt.build"] = (
        f"{describe['tag']}-{describe['count']}" if describe else pins["dxmt.version"]
    )
    pins["dxmt.describe"] = "v" + pins["dxmt.version"]
    artifact = lock["baseArtifact"]
    release = DOWNLOAD_TAG.search(artifact["url"])
    if release is None:
        raise PinError(f"cannot read the release tag from {artifact['url']}")
    pins["base.tag"] = release["tag"]
    pins["base.version"] = release["tag"].removeprefix("v")
    pins["base.url"] = artifact["url"]
    pins["base.sha256"] = artifact["sha256"]
    pins["base.recipe"] = artifact["recipe"]["commit"]
    pins["base.recipeShort"] = artifact["recipe"]["commit"][:SHORT_LENGTH]
    nixpkgs = lock["build"]["nixpkgs"]
    pins["nixpkgs.commit"] = nixpkgs["commit"]
    pins["nixpkgs.short"] = nixpkgs["commit"][:SHORT_LENGTH]
    pins["nixpkgs.link"] = _link(nixpkgs["repository"], nixpkgs["commit"])
    return pins


def render_table(pins: dict[str, str]) -> str:
    rows = ["| Pin | Value |", "| --- | --- |"]
    rows += [f"| `{key}` | `{pins[key]}` |" for key in PIN_TABLE_KEYS]
    return "\n".join(rows) + "\n"


PIN_TABLE_KEYS = (
    "wine.commit",
    "wine.version",
    "dxmt.commit",
    "dxmt.version",
    "base.tag",
    "base.url",
    "base.sha256",
    "base.recipe",
    "nixpkgs.commit",
)
BLOCKS: dict[str, Callable[[dict[str, str]], str]] = {"table": render_table}


# --- Mentions ---------------------------------------------------------------------


def _rewrite_segment(
    text: str, start: int, end: int, pins: dict[str, str], name: str, stale: list[str]
) -> str:
    segment = text[start:end]

    def line_of(offset: int) -> int:
        return text.count("\n", 0, start + offset) + 1

    def inline(match: re.Match[str]) -> str:
        key = match["key"]
        if key not in pins:
            raise PinError(f"{name}:{line_of(match.start())}: unknown pin key '{key}'")
        value = f"`{pins[key]}`" if match["format"] else pins[key]
        if match["body"] != value:
            stale.append(f"{name}:{line_of(match.start())}: pin:{key} is stale")
        return f"<!-- pin:{key}{'|code' if match['format'] else ''} -->{value}<!-- /pin -->"

    def block(match: re.Match[str]) -> str:
        key = match["name"]
        if key not in BLOCKS:
            raise PinError(
                f"{name}:{line_of(match.start())}: unknown pin block '{key}'"
            )
        value = BLOCKS[key](pins)
        if match["body"] != value:
            stale.append(f"{name}:{line_of(match.start())}: pin-block:{key} is stale")
        return f"<!-- pin-block:{key} -->\n{value}<!-- /pin-block -->"

    segment = INLINE_MARKER.sub(inline, segment)
    segment = BLOCK_MARKER.sub(block, segment)
    openers = len(re.findall(r"<!-- pin(?:-block)?:", segment))
    closers = len(re.findall(r"<!-- /pin(?:-block)? -->", segment))
    matched = len(INLINE_MARKER.findall(segment)) + len(BLOCK_MARKER.findall(segment))
    if openers != matched or closers != matched:
        raise PinError(f"{name}: unbalanced or malformed pin marker")
    return segment


def rewrite_markdown(
    text: str, pins: dict[str, str], name: str, stale: list[str]
) -> str:
    """Return the text with every marker regenerated. Fenced code blocks stay as is."""

    parts: list[str] = []
    cursor = 0
    for fence in FENCE.finditer(text):
        span = fence[0]
        if not span.startswith(("```", "~~~")) and "<!--" not in span:
            continue
        parts.append(_rewrite_segment(text, cursor, fence.start(), pins, name, stale))
        parts.append(fence.group())
        cursor = fence.end()
    parts.append(_rewrite_segment(text, cursor, len(text), pins, name, stale))
    return "".join(parts)


def _token(value: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\w.-])" + re.escape(value) + r"(?![\w-]|\.\d)")


def rewrite_allowlisted(
    text: str,
    keys: tuple[str, ...],
    old: dict[str, str],
    new: dict[str, str],
    name: str,
) -> str:
    """Replace the old value of each listed pin. Fail when the new value is missing."""

    for key in keys:
        if old[key] != new[key]:
            text = _token(old[key]).sub(new[key].replace("\\", r"\\"), text)
        if _token(new[key]).search(text) is None:
            raise PinError(f"{name}: lacks the value of {key} ({new[key]})")
    return text


def markdown_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.md")
        if not SKIPPED_DIRECTORIES.intersection(path.relative_to(root).parts)
    )


def plan_rewrites(
    root: Path,
    old: dict[str, str],
    new: dict[str, str],
    allowlist: dict[str, tuple[str, ...]],
) -> tuple[dict[Path, str], list[str]]:
    """Return the new text of every changed mention and the list of stale markers."""

    changes: dict[Path, str] = {}
    stale: list[str] = []
    for path in markdown_files(root):
        text = path.read_text(encoding="utf-8")
        rewritten = rewrite_markdown(
            text, new, path.relative_to(root).as_posix(), stale
        )
        if rewritten != text:
            changes[path] = rewritten
    for relative, keys in allowlist.items():
        path = root / relative
        if not path.is_file():
            raise PinError(f"{relative}: allowlisted file is missing")
        text = path.read_text(encoding="utf-8")
        rewritten = rewrite_allowlisted(text, keys, old, new, relative)
        if rewritten != text:
            changes[path] = rewritten
    return changes, stale


# --- Guard ------------------------------------------------------------------------


def run_process(command: list[str]) -> tuple[int, str]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return result.returncode, (result.stdout + result.stderr).strip()


def guard_patches(
    root: Path,
    lock: dict[str, Any],
    component: str,
    commit: str,
    run: Runner = run_process,
) -> str | None:
    """Apply the patches of a component in lock order to a shallow clone of `commit`.

    Return None when all patches apply, else the reason. Like `runtime.py prepare`,
    each patch is checked and then applied, so later patches see earlier ones.
    """

    repository = lock["sources"][component]["repository"]
    patches = [patch for patch in lock["patches"] if patch["component"] == component]
    with tempfile.TemporaryDirectory(prefix=f"pins-{component}-") as directory:
        git = ["git", "-C", directory]
        for step in (
            ["git", "init", "-q", directory],
            [*git, "fetch", "-q", "--depth", "1", repository, commit],
            [*git, "checkout", "-q", "--detach", "FETCH_HEAD"],
        ):
            status, output = run(step)
            if status != 0:
                return f"cannot fetch {commit[:SHORT_LENGTH]}: {output}"
        for patch in patches:
            path = str(root / patch["path"])
            for action in (["--check"], []):
                status, output = run([*git, "apply", *action, path])
                if status != 0:
                    return f"patch {patch['id']} does not apply: {output}"
    return None


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
    }[component]


def _read_lock(root: Path) -> dict[str, Any]:
    try:
        return json.loads((root / LOCK_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as failure:
        raise PinError(f"cannot read {LOCK_NAME}: {failure}") from failure


def run_update(
    root: Path,
    only: tuple[str, ...],
    *,
    dry_run: bool,
    fetch: Fetch,
    run: Runner = run_process,
    allowlist: dict[str, tuple[str, ...]] = ALLOWLIST,
) -> UpdateResult:
    """Resolve, guard, and rewrite. Raise PinError before any write on a failure."""

    old_lock = _read_lock(root)
    old_pins = pins_from_lock(old_lock)
    new_lock = copy.deepcopy(old_lock)
    outcomes: list[Outcome] = []
    for component in COMPONENTS:
        if component not in only:
            continue
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


def run_check(
    root: Path, allowlist: dict[str, tuple[str, ...]] = ALLOWLIST
) -> list[str]:
    """Return one line per mention that disagrees with the lock."""

    pins = pins_from_lock(_read_lock(root))
    problems: list[str] = []
    for path in markdown_files(root):
        rewrite_markdown(
            path.read_text(encoding="utf-8"),
            pins,
            path.relative_to(root).as_posix(),
            problems,
        )
    for relative, keys in allowlist.items():
        path = root / relative
        if not path.is_file():
            problems.append(f"{relative}: allowlisted file is missing")
            continue
        text = path.read_text(encoding="utf-8")
        problems += [
            f"{relative}: lacks the value of {key} ({pins[key]})"
            for key in keys
            if _token(pins[key]).search(text) is None
        ]
    return problems


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
    "Update the client pin with the update command of the client repository.",
)


def _post_checks(root: Path) -> bool:
    commands = (
        [sys.executable, "scripts/runtime.py", "validate-lock"],
        [sys.executable, "scripts/release/licenses.py", "generate", "--check"],
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


def main(argv: list[str] | None = None, fetch: Fetch = github_fetch) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    update = commands.add_parser(
        "update", help="resolve the newest pins and rewrite mentions"
    )
    update.add_argument("--dry-run", action="store_true", help="write nothing")
    update.add_argument(
        "--only", default=",".join(COMPONENTS), help="comma-separated components"
    )
    commands.add_parser("check", help="verify that all mentions agree with the lock")
    arguments = parser.parse_args(argv)

    try:
        if arguments.command == "check":
            problems = run_check(REPOSITORY_ROOT)
            for problem in problems:
                error(problem)
            if problems:
                return 1
            success("All pin mentions agree with runtime.lock.json.")
            return 0

        only = tuple(name.strip() for name in arguments.only.split(",") if name.strip())
        unknown = sorted(set(only) - set(COMPONENTS))
        if unknown or not only:
            parser.error(
                f"--only takes {', '.join(COMPONENTS)}; got {unknown or 'nothing'}"
            )
        result = run_update(
            REPOSITORY_ROOT, only, dry_run=arguments.dry_run, fetch=fetch
        )
    except PinError as failure:
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
    if not _post_checks(REPOSITORY_ROOT):
        return 1
    success("Lock validation and the license check pass.")
    for step in FOLLOW_UPS:
        info(f"Next: {step}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
