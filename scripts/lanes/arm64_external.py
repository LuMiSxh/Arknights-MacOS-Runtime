# SPDX-License-Identifier: MPL-2.0

"""Fetch and verify the external native-arm64 Wine artifact.

The catalog URL lives only in the GitHub Actions secret `ARM64_RUNTIME_CATALOG_URL`.
This script reads it from an environment variable and never writes a URL to output, logs,
or error messages.
DXMT is built locally by `scripts/lanes/arm64_dxmt.py`, not downloaded.
"""

import json
import os
import re
import tarfile
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.build_common import NATIVE_ARM64_TARGET
from scripts.lib.artifact import ArtifactError, fetch_verified
from scripts.lib.console import info, success, warning
from scripts.lock.model import Lane, LockError
from scripts.lock.parse import load_lock

# The catalog URL is a secret. It is never logged, so a leaked catalog or archive
# location stays out of CI output.
WINE_CATALOG_ENV = "ARM64_RUNTIME_CATALOG_URL"

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_BUILD_NUMBER = re.compile(r"-v(\d+)$")


class FetchError(RuntimeError):
    """The external artifact cannot be fetched or verified."""


@dataclass(frozen=True)
class FetchedArtifact:
    """The catalog release that the build downloaded and the bytes it served."""

    id: str
    sha256: str
    size: int


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


def _published_at(release: dict[str, Any]) -> datetime:
    value = release.get("published_at")
    if not isinstance(value, str):
        raise FetchError(f"catalog release {release.get('id')} has no published_at")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as problem:
        raise FetchError(
            f"catalog release {release.get('id')} has an invalid published_at"
        ) from problem
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _build_number(release: dict[str, Any]) -> int:
    match = _BUILD_NUMBER.search(str(release.get("id", "")))
    return int(match.group(1)) if match else 0


def newest_release(releases: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Return the most recently published release; a later build number breaks a tie."""

    return max(
        releases, key=lambda release: (_published_at(release), _build_number(release))
    )


def select_release(releases: list[Any], release_id: str) -> dict[str, Any]:
    """Return the newest release with the locked id.

    The catalog can list a rebuilt release more than once under one id. The newest
    entry wins here and in the pin command, and the locked SHA-256 decides which bytes
    the build accepts.
    """

    matches = [
        entry
        for entry in releases
        if isinstance(entry, dict) and entry.get("id") == release_id
    ]
    if not matches:
        raise FetchError("catalog has no release with the pinned id")
    if len(matches) == 1:
        return matches[0]
    return newest_release(matches)


def _require_arm64(release: dict[str, Any]) -> None:
    if release.get("arch") != "arm64":
        raise FetchError("catalog release architecture is not arm64")


def catalog_releases(catalog: dict[str, Any]) -> list[Any]:
    releases = catalog.get("releases")
    if not isinstance(releases, list):
        raise FetchError("catalog must name a releases array")
    return releases


def fetch_selected_release(
    env_name: str,
    release_id: str,
    output: Path,
    expected_sha256: str,
    fetch: Callable[[str], bytes] | None = None,
) -> tuple[dict[str, Any], Path]:
    """Download the locked release and verify its bytes against the locked SHA-256.

    The catalog's own digest and size are advisory: this repository pins the archive it
    reviewed, so stale catalog metadata never decides what the build accepts.
    """

    catalog = download_catalog(env_name, fetch)
    release = select_release(catalog_releases(catalog), release_id)
    _require_arm64(release)

    declared = release.get("sha256")
    if isinstance(declared, str) and declared != expected_sha256:
        warning(
            f"the catalog digest of {release_id} differs from the lock; "
            "the locked bytes are verified instead"
        )

    archive_url = release.get("url")
    if not isinstance(archive_url, str) or not archive_url:
        raise FetchError("catalog release has no archive URL")
    try:
        archive = fetch_verified(
            archive_url,
            expected_sha256,
            output,
            label="Downloading the wine archive",
            fetch=fetch,
        )
    except ArtifactError as problem:
        raise FetchError(str(problem)) from problem
    return release, archive


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


def fetch_target(
    lane: Lane,
    output: Path,
    *,
    fetch: Callable[[str], bytes] | None = None,
) -> FetchedArtifact:
    """Fetch, verify, and extract the locked Wine archive into `output`.

    Return the catalog id and the verified bytes. The build never writes the lock.
    """

    output.mkdir(parents=True, exist_ok=True)
    artifact = lane.artifact
    if artifact is None or artifact.catalog != "wine":
        raise FetchError("the external target must pin the wine catalog")
    release, archive = fetch_selected_release(
        WINE_CATALOG_ENV,
        artifact.release,
        output / "wine.tar.xz",
        artifact.sha256,
        fetch=fetch,
    )
    info(f"Fetched catalog release {release['id']}")
    _extract_archive(archive, output)
    if not (output / "wine").is_dir():
        raise FetchError("extracted archive has no wine directory")
    success("Fetched and verified the wine archive")
    return FetchedArtifact(
        id=str(release["id"]), sha256=artifact.sha256, size=archive.stat().st_size
    )


def require_external_lock(target: str = NATIVE_ARM64_TARGET) -> Lane:
    """Load the lane for one target and require an external build with an artifact pin."""

    lane = load_lock().lane(target)
    if lane.build != "external" or lane.artifact is None:
        raise LockError(f"the {lane.name} target is not an external target")
    return lane
