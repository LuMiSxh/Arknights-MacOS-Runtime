# SPDX-License-Identifier: MPL-2.0

"""Resolve the newest upstream state of each pin and write it into the lock.

Components and their rule:

- wine: tip of the highest branch named `wine11<N>` in dappermint/winecx. The version
  is the content of the `VERSION` file at that commit.
- dxmt: head of the default branch of 3Shain/dxmt. The version has the form of
  `git describe`: `<latest tag>-<commits since tag>-g<short sha>`.
- base: newest dappermint/Whisky release with a `Libraries.tar.gz` asset. The hash is
  the `digest` of the asset, so the script never downloads the archive. The recipe
  commit is the commit of the tag `runtime-<release tag>` in dappermint/winecx-gptk.
- nixpkgs: tip of `NIXPKGS_CHANNEL`.

`NIXPKGS_CHANNEL` stays at `nixos-25.05`. The DXMT build needs `llvmPackages_15`, and
nixpkgs removed it after this release. Raising the channel is a manual decision: move
the LLVM version first, change the constant, then review the library closure.

The guard keeps the current pin of wine or dxmt when a patch of that component no
longer applies to the new commit.
"""

import base64
import json
import re
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.lib.github import Fetch, paged
from scripts.lock.model import DEFAULT_LANE
from scripts.pins import LOCK_NAME, SHORT_LENGTH, PinError, read_lock

COMPONENTS = ("wine", "dxmt", "base", "nixpkgs")
NIXPKGS_CHANNEL = "nixos-25.05"
WINE_REPOSITORY = "dappermint/winecx"
WINE_BRANCH = re.compile(r"wine11([0-9]+)")
DXMT_REPOSITORY = "3Shain/dxmt"
BASE_REPOSITORY = "dappermint/Whisky"
BASE_ASSET = "Libraries.tar.gz"
RECIPE_REPOSITORY = "dappermint/winecx-gptk"
RECIPE_TAG_PREFIX = "runtime-"
NIXPKGS_REPOSITORY = "NixOS/nixpkgs"
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
SEMVER_TAG = re.compile(r"v?(\d+(?:\.\d+)*)")

Runner = Callable[[list[str]], tuple[int, str]]


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

    lane = lock["lanes"][DEFAULT_LANE]
    if component in ("wine", "dxmt"):
        lane["sources"][component].update(commit=state.commit, version=state.version)
    elif component == "base":
        artifact = lane["base"]
        artifact.update(url=state.url, sha256=state.sha256)
        artifact["recipe"]["commit"] = state.recipe_commit
    else:
        lock["shared"]["nixpkgs"]["commit"] = state.commit


def write_artifact_pin(root: Path, target: str, release: str, sha256: str) -> bool:
    """Update one external target's artifact pin and rewrite the lock in place.

    Return True when the lock changed. The text keeps the same
    ``json.dumps(lock, indent=2)`` formatting that `run_update` writes, so
    `pins.py check` and `scripts.lock validate` keep passing.
    """

    lock = read_lock(root)
    artifact = lock["lanes"][target]["artifact"]
    if artifact.get("release") == release and artifact.get("sha256") == sha256:
        return False
    artifact.update(release=release, sha256=sha256)
    (root / LOCK_NAME).write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    return True


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

    Return None when all patches apply, else the reason. Like `scripts.lock prepare`,
    each patch is checked and then applied, so later patches see earlier ones.
    """

    lane = lock["lanes"][DEFAULT_LANE]
    repository = lane["sources"][component]["repository"]
    patches = [
        patch
        for patch in lock["patches"]
        if patch["component"] == component and DEFAULT_LANE in patch["files"]
    ]
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
            path = str(root / patch["files"][DEFAULT_LANE]["path"])
            for action in (["--check"], []):
                status, output = run([*git, "apply", *action, path])
                if status != 0:
                    return f"patch {patch['id']} does not apply: {output}"
    return None
