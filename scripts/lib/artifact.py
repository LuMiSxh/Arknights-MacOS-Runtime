# SPDX-License-Identifier: MPL-2.0

"""Checksums, archives, and verified downloads that every runtime lane shares."""

from __future__ import annotations

import hashlib
import tarfile
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path, PurePosixPath

from .console import Progress

CHUNK_SIZE = 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 60


class ArtifactError(RuntimeError):
    """A download or archive does not match its declared size or SHA-256."""


def sha256(path: Path) -> str:
    """Return the SHA-256 of a file, read in blocks."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _keep(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """Leave version-control and bytecode caches out of every archive."""

    parts = PurePosixPath(info.name).parts
    if ".git" in parts or "__pycache__" in parts:
        return None
    return info


def write_archive(
    directory: Path, tar_name: str, entries: Sequence[tuple[Path, str]]
) -> Path:
    """Write `directory/tar_name` from (source, archive name) pairs.

    The shasum-compatible checksum goes beside it as `<tar_name>.sha256`.
    """

    path = directory / tar_name
    with tarfile.open(path, "w:gz") as tar:
        for source, arcname in entries:
            tar.add(source, arcname=arcname, filter=_keep)
    (directory / f"{tar_name}.sha256").write_text(
        f"{sha256(path)}  {tar_name}\n", encoding="utf-8"
    )
    return path


def fetch_verified(
    url: str,
    expected_sha256: str,
    destination: Path,
    *,
    label: str,
    size: int | None = None,
    fetch: Callable[[str], bytes] | None = None,
) -> Path:
    """Return `destination` holding the bytes that `url` serves.

    A file that already matches the digest is reused. Otherwise the download goes to a
    `.part` file. It replaces `destination` only after its size and digest match. `fetch`
    replaces the network read in tests.
    """

    if destination.is_file() and sha256(destination) == expected_sha256:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    if fetch is not None:
        partial.write_bytes(fetch(url))
    else:
        _download(url, partial, label)
    if size is not None and partial.stat().st_size != size:
        raise ArtifactError("archive size does not match the expected size")
    actual = sha256(partial)
    if actual != expected_sha256:
        raise ArtifactError(f"archive SHA-256 does not match: {actual}")
    partial.replace(destination)
    return destination


def _download(url: str, partial: Path, label: str) -> None:
    with (
        urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response,
        partial.open("wb") as output,
    ):
        content_length = response.headers.get("Content-Length", "")
        total = int(content_length) if content_length.isdigit() else 0
        progress = Progress(label, total)
        current = 0
        try:
            while chunk := response.read(CHUNK_SIZE):
                output.write(chunk)
                current += len(chunk)
                progress.update(current)
        finally:
            progress.finish()
