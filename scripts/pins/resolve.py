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
import re
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.build_common import NATIVE_ARM64_TARGET
from scripts.lib.github import Fetch, paged
from scripts.lock.model import DEFAULT_LANE
from scripts.pins import SHORT_LENGTH, PinError
from scripts.targets.arm64_external import (
    WINE_CATALOG_ENV,
    FetchError,
    catalog_releases,
    download_catalog,
)

# `update` moves these by default. `wine-arm64` needs the secret catalog URL, so it
# runs only when `--only` names it.
COMPONENTS = ("wine", "dxmt", "base", "nixpkgs")
ALL_COMPONENTS = (*COMPONENTS, "wine-arm64")
BUILD_NUMBER = re.compile(r"-v(\d+)$")
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


@dataclass(frozen=True)
class ArtifactState:
    release: str
    sha256: str


def _published_at(release: dict[str, Any]) -> datetime:
    value = release.get("published_at")
    if not isinstance(value, str):
        raise PinError(f"catalog release {release.get('id')} has no published_at")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as problem:
        raise PinError(
            f"catalog release {release.get('id')} has an invalid published_at"
        ) from problem
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _build_number(release: dict[str, Any]) -> int:
    match = BUILD_NUMBER.search(str(release.get("id", "")))
    return int(match.group(1)) if match else 0


def resolve_wine_arm64(fetch_catalog: Callable[[str], bytes] | None) -> ArtifactState:
    """Return the newest arm64 release of the external catalog.

    The catalog URL is a secret, so `ARM64_RUNTIME_CATALOG_URL` must be set.
    """

    try:
        releases = catalog_releases(download_catalog(WINE_CATALOG_ENV, fetch_catalog))
    except FetchError as problem:
        raise PinError(str(problem)) from problem
    arm64 = [
        release
        for release in releases
        if isinstance(release, dict) and release.get("arch") == "arm64"
    ]
    if not arm64:
        raise PinError("catalog has no arm64 release")
    newest = max(
        arm64, key=lambda release: (_published_at(release), _build_number(release))
    )
    digest = newest.get("sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise PinError(f"catalog release {newest.get('id')} has no valid SHA-256")
    return ArtifactState(str(newest["id"]), digest)


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
    if component == "wine-arm64":
        lock["lanes"][NATIVE_ARM64_TARGET]["artifact"].update(
            release=state.release, sha256=state.sha256
        )
    elif component in ("wine", "dxmt"):
        lane["sources"][component].update(commit=state.commit, version=state.version)
    elif component == "base":
        artifact = lane["base"]
        artifact.update(url=state.url, sha256=state.sha256)
        artifact["recipe"]["commit"] = state.recipe_commit
    else:
        lock["shared"]["nixpkgs"]["commit"] = state.commit


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
