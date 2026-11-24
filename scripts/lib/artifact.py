# SPDX-License-Identifier: MPL-2.0

"""Checksums, archives, and verified downloads that every runtime lane shares."""

import hashlib
import lzma
import os
import re
import stat
import tarfile
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path, PurePosixPath

from .console import Progress

CHUNK_SIZE = 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 60
ARCHIVE_PRESET = 9 | lzma.PRESET_EXTREME
DIRECTORY_MODE = 0o755
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
EXCLUDED_NAMES = frozenset((".git", "__pycache__"))


class ArtifactError(RuntimeError):
    """A download, archive, or checksum does not match its declared size or SHA-256."""


def sha256(path: Path) -> str:
    """Return the SHA-256 of a file, read in blocks."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def read_checksum(checksum: Path, artifact_name: str) -> str:
    """Return the SHA-256 that a `.sha256` file records for `artifact_name`."""

    lines = [
        line.strip()
        for line in checksum.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(lines) != 1:
        raise ArtifactError(f"{checksum.name} must contain one record")
    fields = lines[0].split(maxsplit=1)
    if len(fields) != 2 or SHA256_PATTERN.fullmatch(fields[0]) is None:
        raise ArtifactError(f"{checksum.name} has invalid syntax")
    named = fields[1].removeprefix("*")
    if named != artifact_name:
        raise ArtifactError(
            f"{checksum.name} names {named!r}, expected {artifact_name!r}"
        )
    return fields[0]


def verify_checksum(artifact: Path, checksum: Path) -> str:
    """Return the SHA-256 of `artifact` after it matches its `.sha256` file."""

    expected = read_checksum(checksum, artifact.name)
    actual = sha256(artifact)
    if actual != expected:
        raise ArtifactError(
            f"{artifact.name} SHA-256 does not match its checksum: {actual} != {expected}"
        )
    return actual


def _walk(source: Path, name: str) -> Iterator[tuple[str, Path]]:
    if EXCLUDED_NAMES.intersection(PurePosixPath(name).parts):
        return
    yield name, source
    if stat.S_ISDIR(os.lstat(source).st_mode):
        for child in sorted(source.iterdir()):
            yield from _walk(child, f"{name}/{child.name}")


def _members(entries: Sequence[tuple[Path, str]]) -> dict[str, Path | None]:
    """Return every member by archive name. Parents that no entry names map to None."""

    members: dict[str, Path | None] = {}
    for source, arcname in entries:
        for name, path in _walk(source, arcname):
            if name in members:
                raise ArtifactError(f"duplicate archive member: {name}")
            members[name] = path
    for name in list(members):
        for parent in PurePosixPath(name).parents:
            if str(parent) != ".":
                members.setdefault(str(parent), None)
    return members


def _info(
    name: str, source: Path | None, hard_links: set[tuple[int, int]]
) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.mtime = 0
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    if source is None:
        info.type = tarfile.DIRTYPE
        info.mode = DIRECTORY_MODE
        return info
    status = os.lstat(source)
    if stat.S_ISLNK(status.st_mode):
        info.type = tarfile.SYMTYPE
        info.linkname = os.readlink(source)
        info.mode = 0o777
    elif stat.S_ISDIR(status.st_mode):
        info.type = tarfile.DIRTYPE
        info.mode = DIRECTORY_MODE
    elif stat.S_ISREG(status.st_mode):
        if status.st_nlink > 1:
            key = (status.st_dev, status.st_ino)
            if key in hard_links:
                raise ArtifactError(f"hard links are not allowed: {source}")
            hard_links.add(key)
        info.type = tarfile.REGTYPE
        info.size = status.st_size
        info.mode = 0o755 if status.st_mode & 0o111 else 0o644
    else:
        raise ArtifactError(f"unsupported file type: {source}")
    return info


def write_archive(
    directory: Path, tar_name: str, entries: Sequence[tuple[Path, str]]
) -> Path:
    """Write `directory/tar_name` from (source, archive name) pairs and return its path.

    Each source is added with everything below it. The output is deterministic: members
    are sorted by name, with mtime 0, uid and gid 0, and empty owner names. Modes are 0755
    for directories and executable files, and 0644 for other files. Hard links, devices,
    and FIFOs are rejected. The xz stream has a CRC64 check. The SHA-256 checksum goes
    beside it as `<tar_name>.sha256`.
    """

    members = _members(entries)
    path = directory / tar_name
    hard_links: set[tuple[int, int]] = set()
    with tarfile.open(path, "w:xz", preset=ARCHIVE_PRESET) as tar:
        for name in sorted(members):
            source = members[name]
            info = _info(name, source, hard_links)
            if source is not None and info.isreg():
                with source.open("rb") as content:
                    tar.addfile(info, content)
            else:
                tar.addfile(info)
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
