# SPDX-License-Identifier: MPL-2.0

"""Write delta archives from recent releases into a combined release directory.

For each architecture, the command takes the newest published releases before the new one.
It downloads each release's runtime archive, verifies it, and writes a delta that turns the
installed tree of that release into the new tree. The delta is applied again before it is
kept. A source that fails is logged and skipped, because deltas are best effort.
"""

import argparse
import hashlib
import json
import multiprocessing
import os
import posixpath
import shutil
import struct
import subprocess
import tarfile
import tempfile
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

import bsdiff4.core

from scripts.lanes import (
    ARCHIVE_SUFFIX,
    LEGACY_ARCHIVE_SUFFIX,
    RUNTIME_ROOT,
    delta_archive_name,
    legacy_runtime_archive_stem,
    release_tag,
    runtime_archive_name,
)
from scripts.lib.artifact import (
    CHECKSUMS_NAME,
    ArtifactError,
    sha256,
    verify_checksum,
    verify_listed,
    write_archive,
)
from scripts.lib.console import info, warning

ARCHITECTURES = ("x86_64", "arm64")
SOURCE_COUNT = 3
RELEASE_LIMIT = 100
SCHEMA_VERSION = 1
PATCH_MAGIC = b"RTBSDF01"
PATCH_HEADER_SIZE = 24
PATCH_WORKERS = 4
DELTA_ROOT = "Delta"
DATA_DIRECTORY = "data"
LEGACY_ROOT = "Libraries"
LEGACY_WINE = "Wine"
LEGACY_NOTICES = ("Licenses", "NOTICE.md")


class DeltaError(ValueError):
    """A delta cannot be built, or it does not reproduce its target tree."""


@dataclass(frozen=True)
class Entry:
    """One path of an installed tree. Files carry their mode, size, and SHA-256."""

    kind: str
    executable: bool = False
    size: int = 0
    sha256: str = ""
    target: str = ""


def select_sources(
    releases: Sequence[Mapping[str, Any]],
    current_version: str,
    count: int = SOURCE_COUNT,
) -> list[str]:
    """Return the versions of the newest published releases, other than the current one.

    Drafts, prereleases, and releases without a publication time are never sources.
    """

    current = release_tag(current_version)
    published = [
        release
        for release in releases
        if release.get("publishedAt")
        and not release.get("isDraft")
        and not release.get("isPrerelease")
        and release.get("tagName") != current
    ]
    published.sort(
        key=lambda release: datetime.fromisoformat(release["publishedAt"]),
        reverse=True,
    )
    return [release["tagName"].removeprefix("v") for release in published[:count]]


def _gh(*arguments: str) -> str:
    result = subprocess.run(
        ["gh", *arguments], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise DeltaError(f"gh failed: {result.stderr.strip()}")
    return result.stdout


def list_releases() -> list[dict[str, Any]]:
    """Return the releases of this repository as `gh release list` reports them."""

    return json.loads(
        _gh(
            "release",
            "list",
            "--limit",
            str(RELEASE_LIMIT),
            "--json",
            "tagName,isDraft,isPrerelease,publishedAt",
        )
    )


def download_runtime_archive(version: str, arch: str, directory: Path) -> Path:
    """Download the runtime archive of a release and verify it against its checksum.

    The delta sources are the three newest releases, so they reach back across the asset
    rename. A release since archive schema 3 publishes `runtime-<arch>.tar.xz` and one
    `SHA256SUMS`. Older releases publish `Arknights-MacOS-Runtime-v<version>-<arch>.tar.gz`
    with a `.sha256` sidecar. Try the current names first, then fall back to the old ones.
    """

    directory.mkdir(parents=True)
    tag = release_tag(version)
    archive = directory / runtime_archive_name(arch)
    try:
        _download_assets(tag, directory, archive.name, CHECKSUMS_NAME)
    except DeltaError:
        info(f"{tag} has no {archive.name}; trying the legacy asset names")
    else:
        verify_listed(archive, directory / CHECKSUMS_NAME)
        return archive
    stem = legacy_runtime_archive_stem(version, arch)
    _download_assets(tag, directory, f"{stem}.tar.*")
    for suffix in (ARCHIVE_SUFFIX, LEGACY_ARCHIVE_SUFFIX):
        legacy = directory / f"{stem}{suffix}"
        if legacy.is_file():
            verify_checksum(legacy, legacy.with_name(f"{legacy.name}.sha256"))
            return legacy
    raise DeltaError(f"release {tag} has no {arch} runtime archive")


def _download_assets(tag: str, directory: Path, *patterns: str) -> None:
    arguments = ["release", "download", tag, "--dir", str(directory)]
    for pattern in patterns:
        arguments += ["--pattern", pattern]
    _gh(*arguments)


def _safe_relative(name: str) -> str:
    """Return `name` if it is a relative, `/`-separated path with no `.` or `..` parts."""

    parts = PurePosixPath(name).parts
    if (
        "\\" in name
        or PurePosixPath(name).is_absolute()
        or not parts
        or any(part in ("", ".", "..") for part in parts)
    ):
        raise DeltaError(f"unsafe path: {name!r}")
    return name


def _extract_safely(tar: tarfile.TarFile, destination: Path) -> None:
    members = tar.getmembers()
    for member in members:
        _safe_relative(member.name)
        if not (member.isdir() or member.isfile() or member.issym()):
            raise DeltaError(f"unsupported archive member: {member.name!r}")
    tar.extractall(destination, members=members, filter="data")


def _flatten_legacy(destination: Path) -> None:
    """Move a legacy `Libraries/` tree to the installed root, as the client does."""

    libraries = destination / LEGACY_ROOT
    root = destination / RUNTIME_ROOT
    root.mkdir()
    for child in sorted(libraries.iterdir()):
        if child.name == LEGACY_WINE:
            for grandchild in sorted(child.iterdir()):
                grandchild.rename(root / grandchild.name)
        else:
            child.rename(root / child.name)
    for name in LEGACY_NOTICES:
        if (destination / name).exists():
            (destination / name).rename(root / name)


def extract_install_root(archive: Path, destination: Path) -> Path:
    """Extract a runtime archive and return the installed root inside `destination`.

    A schema 3 archive holds `Runtime/`. A legacy archive holds `Libraries/`, `Licenses/`,
    and `NOTICE.md`, and its Wine tree moves to the root.
    """

    if archive.name.endswith(ARCHIVE_SUFFIX):
        mode = "r:xz"
    elif archive.name.endswith(LEGACY_ARCHIVE_SUFFIX):
        mode = "r:gz"
    else:
        raise DeltaError(f"not a runtime archive: {archive.name}")
    destination.mkdir(parents=True)
    with tarfile.open(archive, mode) as tar:
        _extract_safely(tar, destination)
    if (destination / LEGACY_ROOT).is_dir():
        _flatten_legacy(destination)
    root = destination / RUNTIME_ROOT
    if not root.is_dir():
        raise DeltaError(f"{archive.name} has no {RUNTIME_ROOT}/ root")
    return root


def _contained(relative: str, target: str) -> bool:
    """Return whether a symlink at `relative` resolves inside the installed root."""

    if not target or target.startswith("/") or "\\" in target:
        return False
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(relative), target))
    return resolved != ".." and not resolved.startswith("../")


def tree_entries(root: Path) -> dict[str, Entry]:
    """Describe every path below `root` by its kind and, for files, its digest."""

    entries: dict[str, Entry] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            target = os.readlink(path)
            if not _contained(relative, target):
                raise DeltaError(f"symlink leaves the root: {relative} -> {target}")
            entries[relative] = Entry("symlink", target=target)
        elif path.is_dir():
            entries[relative] = Entry("directory")
        elif path.is_file():
            status = path.stat()
            entries[relative] = Entry(
                "file",
                executable=bool(status.st_mode & 0o111),
                size=status.st_size,
                sha256=sha256(path),
            )
        else:
            raise DeltaError(f"unsupported file: {relative}")
    return entries


def _offtin(field: bytes) -> int:
    """Decode the 8-byte sign-and-magnitude integer that bsdiff writes."""

    value = field[7] & 0x7F
    for byte in reversed(field[:7]):
        value = value * 256 + byte
    return -value if field[7] & 0x80 else value


def diff_bytes(old: bytes, new: bytes) -> bytes:
    """Return the RTBSDF01 patch that turns `old` into `new`.

    The bsdiff control block is re-encoded as little-endian two's complement int64 values.
    """

    control, diff, extra = bsdiff4.core.diff(old, new)
    fields = [
        _offtin(control[offset : offset + 8]) for offset in range(0, len(control), 8)
    ]
    triples = [tuple(fields[index : index + 3]) for index in range(0, len(fields), 3)]
    if sum(add for add, _, _ in triples) != len(diff) or sum(
        copy for _, copy, _ in triples
    ) != len(extra):
        raise DeltaError("bsdiff output does not match its control block")
    header = struct.pack("<8sQQ", PATCH_MAGIC, len(new), len(triples))
    controls = b"".join(struct.pack("<3q", *triple) for triple in triples)
    return header + controls + diff + extra


def _add_bytes(left: bytes, right: bytes) -> bytes:
    """Add two equal-length byte strings lane by lane modulo 256, without carries."""

    size = len(left)
    if size == 0:
        return b""
    low = int.from_bytes(b"\x7f" * size, "little")
    high = int.from_bytes(b"\x80" * size, "little")
    first = int.from_bytes(left, "little")
    second = int.from_bytes(right, "little")
    total = ((first & low) + (second & low)) ^ ((first ^ second) & high)
    return total.to_bytes(size, "little")


def apply_patch(old: bytes, patch: bytes) -> bytes:
    """Return the file that the RTBSDF01 `patch` produces from `old`."""

    if len(patch) < PATCH_HEADER_SIZE or patch[:8] != PATCH_MAGIC:
        raise DeltaError("patch is not RTBSDF01")
    _, new_size, count = struct.unpack_from("<8sQQ", patch)
    controls_end = PATCH_HEADER_SIZE + 24 * count
    if controls_end > len(patch):
        raise DeltaError("patch control block is truncated")
    controls = [
        struct.unpack_from("<3q", patch, PATCH_HEADER_SIZE + 24 * index)
        for index in range(count)
    ]
    if any(value < 0 for add, copy, _ in controls for value in (add, copy)):
        raise DeltaError("patch has a negative add or copy count")
    diff_size = sum(add for add, _, _ in controls)
    extra_size = sum(copy for _, copy, _ in controls)
    if controls_end + diff_size + extra_size != len(patch):
        raise DeltaError("patch diff or extra data has the wrong size")
    diff = patch[controls_end : controls_end + diff_size]
    extra = patch[controls_end + diff_size :]

    output = bytearray()
    old_position = diff_position = extra_position = 0
    for add, copy, seek in controls:
        if len(output) + add + copy > new_size:
            raise DeltaError("patch writes past the new size")
        if add and (old_position < 0 or old_position + add > len(old)):
            raise DeltaError("patch reads outside the old file")
        output += _add_bytes(
            old[old_position : old_position + add],
            diff[diff_position : diff_position + add],
        )
        diff_position += add
        old_position += add
        output += extra[extra_position : extra_position + copy]
        extra_position += copy
        old_position += seek
    if len(output) != new_size:
        raise DeltaError("patch produces the wrong size")
    return bytes(output)


def _patch_file(old_path: Path, new_path: Path) -> bytes:
    return diff_bytes(old_path.read_bytes(), new_path.read_bytes())


def _patchable(previous: Entry | None, entry: Entry) -> bool:
    return (
        previous is not None
        and previous.kind == "file"
        and entry.kind == "file"
        and previous.sha256 != entry.sha256
        and previous.size > 0
        and entry.size > 0
    )


def _describe(path: str, entry: Entry) -> dict[str, Any]:
    if entry.kind == "directory":
        return {"path": path, "type": "directory"}
    if entry.kind == "symlink":
        return {"path": path, "type": "symlink", "target": entry.target}
    return {
        "path": path,
        "type": "file",
        "executable": entry.executable,
        "size": entry.size,
        "sha256": entry.sha256,
    }


def write_delta(
    *,
    version: str,
    source_version: str,
    arch: str,
    source_root: Path,
    target_root: Path,
    directory: Path,
) -> Path:
    """Write the delta from `source_root` to `target_root` into `directory`.

    Patches of changed files are computed in parallel. Returns the archive path.
    """

    source = tree_entries(source_root)
    target = tree_entries(target_root)
    changed = [path for path in target if _patchable(source.get(path), target[path])]
    # spawn keeps the pool off the forkserver socket, which the offline test harness blocks.
    with ProcessPoolExecutor(
        max_workers=PATCH_WORKERS, mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        futures = {
            pool.submit(_patch_file, source_root / path, target_root / path): path
            for path in changed
        }
        patches = {futures[future]: future.result() for future in as_completed(futures)}

    with tempfile.TemporaryDirectory() as scratch:
        delta_root = Path(scratch) / DELTA_ROOT
        data_root = delta_root / DATA_DIRECTORY
        data_root.mkdir(parents=True)
        entries: list[dict[str, Any]] = []
        data_count = 0
        for path in sorted(target):
            item = _describe(path, target[path])
            entry = target[path]
            previous = source.get(path)
            if entry.kind == "file":
                if previous is not None and previous.sha256 == entry.sha256:
                    item |= {"op": "keep", "sourceSha256": previous.sha256}
                else:
                    data = data_root / str(data_count)
                    if path in patches:
                        data.write_bytes(patches[path])
                        item |= {
                            "op": "patch",
                            "sourceSha256": source[path].sha256,
                        }
                    else:
                        shutil.copyfile(target_root / path, data)
                        item |= {"op": "add"}
                    item["data"] = f"{DATA_DIRECTORY}/{data_count}"
                    data_count += 1
            entries.append(item)
        document = {
            "schemaVersion": SCHEMA_VERSION,
            "arch": arch,
            "from": source_version,
            "to": version,
            "entries": entries,
        }
        (delta_root / "delta.json").write_text(
            json.dumps(document, indent=2) + "\n", encoding="utf-8"
        )
        return write_archive(
            directory,
            delta_archive_name(arch, source_version),
            [(delta_root, DELTA_ROOT)],
        )


def _file_content(item: dict[str, Any], source_root: Path, delta_root: Path) -> bytes:
    operation = item.get("op")
    if operation == "add":
        return (delta_root / item["data"]).read_bytes()
    if operation in ("keep", "patch"):
        old = (source_root / item["path"]).read_bytes()
        if hashlib.sha256(old).hexdigest() != item["sourceSha256"]:
            raise DeltaError(f"source of {item['path']} does not match its SHA-256")
        if operation == "keep":
            return old
        return apply_patch(old, (delta_root / item["data"]).read_bytes())
    raise DeltaError(f"unknown file operation: {operation!r}")


def apply_delta(delta_root: Path, source_root: Path, destination: Path) -> None:
    """Build `destination` from `source_root` and the `Delta/` directory `delta_root`.

    The result holds exactly the listed paths, so unlisted source paths are dropped. Every
    file must match its size, its SHA-256, and its executable bit.
    """

    document = json.loads((delta_root / "delta.json").read_text(encoding="utf-8"))
    if document.get("schemaVersion") != SCHEMA_VERSION:
        raise DeltaError("unsupported delta schema")
    destination.mkdir(parents=True)
    for item in document["entries"]:
        path = _safe_relative(item["path"])
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if item["type"] == "directory":
            target.mkdir(exist_ok=True)
        elif item["type"] == "symlink":
            if not _contained(path, item["target"]):
                raise DeltaError(f"symlink leaves the root: {path}")
            os.symlink(item["target"], target)
        elif item["type"] == "file":
            content = _file_content(item, source_root, delta_root)
            if len(content) != item["size"] or (
                hashlib.sha256(content).hexdigest() != item["sha256"]
            ):
                raise DeltaError(f"{path} does not match its size or SHA-256")
            target.write_bytes(content)
            target.chmod(0o755 if item["executable"] else 0o644)
        else:
            raise DeltaError(f"unknown entry type: {item['type']!r}")


def apply_delta_archive(archive: Path, source_root: Path, destination: Path) -> None:
    """Extract a delta archive and apply it to `source_root` into `destination`."""

    with tempfile.TemporaryDirectory() as scratch:
        with tarfile.open(archive, "r:xz") as tar:
            _extract_safely(tar, Path(scratch))
        apply_delta(Path(scratch) / DELTA_ROOT, source_root, destination)


def check_delta(archive: Path, source_root: Path, target_root: Path) -> None:
    """Raise `DeltaError` unless the published archive rebuilds the target tree."""

    with tempfile.TemporaryDirectory() as scratch:
        result = Path(scratch) / "result"
        apply_delta_archive(archive, source_root, result)
        if tree_entries(result) != tree_entries(target_root):
            raise DeltaError("applied delta does not match the target tree")


def _write_checked_delta(
    version: str, source_version: str, arch: str, dist: Path, target_root: Path
) -> Path:
    with tempfile.TemporaryDirectory() as scratch_name:
        scratch = Path(scratch_name)
        archive = download_runtime_archive(source_version, arch, scratch / "download")
        source_root = extract_install_root(archive, scratch / "source")
        delta = write_delta(
            version=version,
            source_version=source_version,
            arch=arch,
            source_root=source_root,
            target_root=target_root,
            directory=dist,
        )
        try:
            check_delta(delta, source_root, target_root)
        except Exception:
            # An unverified delta must never reach the release upload.
            delta.unlink()
            raise
        return delta


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="plain SemVer release version")
    parser.add_argument(
        "--dist",
        type=Path,
        required=True,
        help="combined release directory; the delta archives are written here",
    )
    parsed = parser.parse_args(arguments)
    try:
        sources = select_sources(list_releases(), parsed.version)
    except (DeltaError, OSError, ValueError) as problem:
        warning(f"deltas skipped: cannot list releases: {problem}")
        return 0
    if not sources:
        info("no published release to build deltas from")
        return 0
    for arch in ARCHITECTURES:
        archive = parsed.dist / runtime_archive_name(arch)
        if not archive.is_file():
            warning(f"deltas skipped for {arch}: {archive.name} is missing")
            continue
        with tempfile.TemporaryDirectory() as scratch:
            target_root = extract_install_root(archive, Path(scratch) / "target")
            for source in sources:
                try:
                    delta = _write_checked_delta(
                        parsed.version, source, arch, parsed.dist, target_root
                    )
                except (
                    DeltaError,
                    ArtifactError,
                    OSError,
                    tarfile.TarError,
                    # A bsdiff worker killed for memory must not block the release.
                    BrokenProcessPool,
                    MemoryError,
                ) as problem:
                    warning(f"skipping {arch} delta from v{source}: {problem}")
                else:
                    info(f"wrote {delta.name}")
    return 0
