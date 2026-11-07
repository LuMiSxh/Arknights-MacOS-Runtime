#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Fetch and verify the external native-arm64 Wine artifact.

The catalog URL lives only in the `release-arm64` environment. This script reads it
from an environment variable and never writes a URL to output, logs, or error messages.
DXMT is built locally by `build_dxmt.py`, not downloaded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tarfile
import urllib.request
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

if __package__:
    from ..lib.console import error, info, success
    from ..runtime import LockError, load_lock
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.lib.console import error, info, success
    from scripts.runtime import LockError, load_lock


ARM64_TARGET = "native-arm64"

# The catalog URL is a secret. It is never logged, so a leaked catalog or archive
# location stays out of CI output.
WINE_CATALOG_ENV = "ARM64_RUNTIME_CATALOG_URL"

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


class FetchError(RuntimeError):
    """The external artifact cannot be fetched or verified."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


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


def fetch_release(
    env_name: str,
    release_id: str,
    expected_sha256: str,
    output: Path,
    fetch: Callable[[str], bytes] | None = None,
) -> Path:
    """Download one pinned release after its catalog fields and bytes are verified."""

    catalog = download_catalog(env_name, fetch)
    releases = catalog.get("releases")
    if not isinstance(releases, list):
        raise FetchError("catalog must name a releases array")
    release = _select_release(releases, release_id)
    _require_arm64(release)

    declared = release.get("sha256")
    if declared != expected_sha256:
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

    actual = _sha256_file(partial)
    if actual != expected_sha256:
        raise FetchError("archive SHA-256 does not match the locked SHA-256")
    partial.replace(output)
    return output


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
        except (tarfile.FilterError, tarfile.TarError, OSError, ValueError) as problem:
            raise FetchError("archive member escapes the destination") from problem


def _fetch_target(lock: dict[str, Any], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    artifact = lock["artifact"]
    if artifact["catalog"] != "wine":
        raise FetchError("the external target must pin the wine catalog")
    archive = fetch_release(
        WINE_CATALOG_ENV,
        artifact["release"],
        artifact["sha256"],
        output / "wine.tar.xz",
    )
    info("Verifying the wine archive")
    _extract_archive(archive, output)
    if not (output / "wine").is_dir():
        raise FetchError("extracted archive has no wine directory")
    success("Fetched and verified the wine archive")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=ARM64_TARGET)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        lock = load_lock(target=arguments.target)
        if lock["buildMode"] != "external":
            error(f"the {lock['target']} target is not an external target")
            return 1
        _fetch_target(lock, arguments.output)
    except (FetchError, LockError, KeyError, OSError) as caught_error:
        error(str(caught_error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
