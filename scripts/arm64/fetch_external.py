#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Fetch and verify the external native-arm64 Wine artifact.

The catalog URL lives only in the GitHub Actions secret `ARM64_RUNTIME_CATALOG_URL`.
This script reads it from an environment variable and never writes a URL to output, logs,
or error messages.
DXMT is built locally by `build_dxmt.py`, not downloaded.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tarfile
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

if __package__:
    from ..build_common import NATIVE_ARM64_TARGET, ROOT, sha256
    from ..lib.console import error, info, success, warning
    from ..release.pins import write_artifact_pin
    from ..runtime import LockError, load_lock
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.build_common import NATIVE_ARM64_TARGET, ROOT, sha256
    from scripts.lib.console import error, info, success, warning
    from scripts.release.pins import write_artifact_pin
    from scripts.runtime import LockError, load_lock


# The catalog URL is a secret. It is never logged, so a leaked catalog or archive
# location stays out of CI output.
WINE_CATALOG_ENV = "ARM64_RUNTIME_CATALOG_URL"

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_BUILD_NUMBER = re.compile(r"-v(\d+)$")


class FetchError(RuntimeError):
    """The external artifact cannot be fetched or verified."""


def _urlopen_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def download_catalog(
    env_name: str, fetch: Callable[[str], bytes] | None = None
) -> dict[str, Any]:
    """Return the parsed catalog object named by one environment variable."""

    url = os.environ.get(env_name)
    if not url:
        raise FetchError(f"{env_name} is not set")
    data = fetch(url) if fetch is not None else _urlopen_bytes(url)
    try:
        catalog = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as problem:
        raise FetchError("catalog is not valid JSON") from problem
    if not isinstance(catalog, dict):
        raise FetchError("catalog must be a JSON object")
    return catalog


def _select_release(releases: list[Any], release_id: str) -> dict[str, Any]:
    matches = [
        entry
        for entry in releases
        if isinstance(entry, dict) and entry.get("id") == release_id
    ]
    if not matches:
        raise FetchError("catalog has no release with the pinned id")
    if len(matches) > 1:
        raise FetchError("catalog repeats the pinned release id")
    return matches[0]


def _require_arm64(release: dict[str, Any]) -> None:
    if release.get("arch") != "arm64":
        raise FetchError("catalog release architecture is not arm64")


def _releases(catalog: dict[str, Any]) -> list[Any]:
    releases = catalog.get("releases")
    if not isinstance(releases, list):
        raise FetchError("catalog must name a releases array")
    return releases


def _published_at(release: dict[str, Any]) -> datetime:
    value = release.get("published_at")
    if not isinstance(value, str):
        raise FetchError("catalog release has no published_at")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as problem:
        raise FetchError("catalog release has an invalid published_at") from problem
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _build_number(release: dict[str, Any]) -> int:
    match = _BUILD_NUMBER.search(str(release.get("id", "")))
    return int(match.group(1)) if match else 0


def select_release(releases: list[Any], release_id: str) -> dict[str, Any]:
    """Return the named release, or the newest ARM64 release when no id is given."""

    if release_id:
        return _select_release(releases, release_id)
    arm64 = [
        release
        for release in releases
        if isinstance(release, dict) and release.get("arch") == "arm64"
    ]
    if not arm64:
        raise FetchError("catalog has no arm64 release")
    return max(
        arm64, key=lambda release: (_published_at(release), _build_number(release))
    )


def _download_archive(
    url: str, partial: Path, fetch: Callable[[str], bytes] | None
) -> None:
    if fetch is not None:
        partial.write_bytes(fetch(url))
        return
    with (
        urllib.request.urlopen(url, timeout=60) as response,
        partial.open("wb") as output,
    ):
        while chunk := response.read(1024 * 1024):
            output.write(chunk)


def fetch_selected_release(
    env_name: str,
    release_id: str,
    output: Path,
    expected_sha256: str | None = None,
    fetch: Callable[[str], bytes] | None = None,
) -> tuple[dict[str, Any], Path]:
    """Download the selected release after its catalog fields and bytes are verified."""

    catalog = download_catalog(env_name, fetch)
    release = select_release(_releases(catalog), release_id)
    _require_arm64(release)

    declared = release.get("sha256")
    if not isinstance(declared, str) or _SHA256.fullmatch(declared) is None:
        raise FetchError("catalog release has no valid SHA-256")
    if expected_sha256 is not None and declared != expected_sha256:
        raise FetchError("catalog SHA-256 does not match the locked SHA-256")

    archive_url = release.get("url")
    if not isinstance(archive_url, str) or not archive_url:
        raise FetchError("catalog release has no archive URL")

    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.name + ".part")
    _download_archive(archive_url, partial, fetch)

    size = release.get("size")
    if size is not None:
        try:
            expected_size = int(size)
        except (TypeError, ValueError) as problem:
            raise FetchError("catalog release has an invalid size") from problem
        if partial.stat().st_size != expected_size:
            raise FetchError("archive size does not match the catalog size")

    actual = sha256(partial)
    if actual != declared:
        raise FetchError("archive SHA-256 does not match the catalog SHA-256")
    partial.replace(output)
    return release, output


def _validate_member(member: tarfile.TarInfo) -> None:
    name = member.name
    if name.startswith("/") or "\\" in name or _WINDOWS_DRIVE.match(name):
        raise FetchError("archive member has an absolute or Windows path")
    parts = PurePosixPath(name).parts
    if ".." in parts:
        raise FetchError("archive member escapes the destination")
    if any(part == "__MACOSX" or part.startswith("._") for part in parts):
        raise FetchError("archive member is macOS metadata")
    if member.issym() or member.islnk():
        target = member.linkname
        if target.startswith("/") or "\\" in target or _WINDOWS_DRIVE.match(target):
            raise FetchError("archive link escapes the destination")


def _extract_archive(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, mode="r:*") as tar:
        for member in tar.getmembers():
            _validate_member(member)
        try:
            # The "data" filter resolves symlink and hardlink targets and rejects
            # any that escape the destination. The checks above reject absolute
            # paths, "..", Windows drive prefixes, and macOS metadata entries.
            tar.extractall(destination, filter="data")
        except tarfile.FilterError as problem:
            raise FetchError("archive member escapes the destination") from problem
        except (tarfile.TarError, OSError, ValueError) as problem:
            raise FetchError(f"cannot extract the wine archive: {problem}") from problem


def _fetch_target(lock: dict[str, Any], output: Path, release_id: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    artifact = lock["artifact"]
    if artifact["catalog"] != "wine":
        raise FetchError("the external target must pin the wine catalog")
    release, archive = fetch_selected_release(
        WINE_CATALOG_ENV, release_id, output / "wine.tar.xz"
    )
    metadata = {
        key: release[key]
        for key in ("id", "arch", "sha256", "size", "published_at")
        if key in release
    }
    (output / "external.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    info(f"Selected catalog release {release['id']}")
    info("Verifying the wine archive")
    _extract_archive(archive, output)
    if not (output / "wine").is_dir():
        raise FetchError("extracted archive has no wine directory")
    # The upstream catalog sometimes replaces a release's archive under the same id, so a
    # new SHA-256 for the pinned id is re-pinned with a warning instead of failing.
    if release["id"] == artifact["release"] and release["sha256"] != artifact["sha256"]:
        warning(
            f"The catalog archive for {release['id']} changed since it was pinned "
            f"({artifact['sha256']} -> {release['sha256']})"
        )
    if (
        release["id"] != artifact["release"] or release["sha256"] != artifact["sha256"]
    ) and write_artifact_pin(ROOT, lock["target"], release["id"], release["sha256"]):
        warning(
            f"Updated the {lock['target']} artifact pin to {release['id']} "
            f"({release['sha256']})"
        )
    success("Fetched and verified the wine archive")


def require_external_lock(target: str = NATIVE_ARM64_TARGET) -> dict[str, Any]:
    """Load the lock for one target and require its external build mode."""

    lock = load_lock(target=target)
    if lock["buildMode"] != "external":
        raise LockError(f"the {lock['target']} target is not an external target")
    return lock


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=NATIVE_ARM64_TARGET)
    parser.add_argument(
        "--release-id",
        default="",
        help="catalog release id; defaults to the newest ARM64 release",
    )
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        lock = require_external_lock(arguments.target)
        _fetch_target(lock, arguments.output, arguments.release_id.strip())
    except (FetchError, LockError, KeyError, OSError) as caught_error:
        error(str(caught_error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
