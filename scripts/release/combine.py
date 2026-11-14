#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Combine the lane outputs into one release.

Each input directory holds `provenance-<ARCH>.json` fragments and the files they name. The
command checks every archive against its `.sha256` file and its fragment. It then writes
one `provenance.json` and one `THIRD-PARTY-NOTICES.txt` for the release. It needs only the
standard library, so it runs on Linux.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lib.artifact import sha256
from scripts.lib.console import error, success
from scripts.release.verify import (
    ReleaseValidationError,
    normalize_version,
)
from scripts.targets import (
    REQUIRED_TARGETS,
    inventory_name,
    notices_name,
    release_tag,
)

SCHEMA_VERSION = 2
ARCHIVE_RECORDS = ("runtimeArchive", "correspondingSourceArchive")


class CombineError(ValueError):
    """The lane outputs cannot form one release."""


def _regular(path: Path) -> Path:
    if path.is_symlink() or not path.is_file():
        raise CombineError(f"required file is missing or not regular: {path}")
    return path


def _read_fragments(
    version: str, inputs: Sequence[Path]
) -> dict[str, tuple[Path, dict[str, Any]]]:
    fragments: dict[str, tuple[Path, dict[str, Any]]] = {}
    for directory in inputs:
        for path in sorted(directory.glob("provenance-*.json")):
            try:
                fragment = json.loads(_regular(path).read_text(encoding="utf-8"))
            except (OSError, ValueError) as problem:
                raise CombineError(f"cannot read fragment: {path}") from problem
            if not isinstance(fragment, dict) or not isinstance(
                fragment.get("target"), str
            ):
                raise CombineError(f"fragment has no target: {path}")
            if fragment.get("version") != version:
                raise CombineError(
                    f"{path.name} records version {fragment.get('version')!r}, "
                    f"expected {version!r}"
                )
            target = fragment["target"]
            if target in fragments:
                raise CombineError(f"target appears in two fragments: {target}")
            fragments[target] = (directory, fragment)
    return fragments


def _checked_archive(directory: Path, record: Any) -> Path:
    """Return an archive whose bytes, size, and checksum file match its fragment."""

    if not isinstance(record, dict) or not isinstance(record.get("name"), str):
        raise CombineError("fragment has no archive record")
    name = record["name"]
    if Path(name).name != name or name in ("", ".", ".."):
        raise CombineError(f"archive name is not a plain file name: {name!r}")
    archive = _regular(directory / name)
    digest = sha256(archive)
    if digest != record.get("sha256"):
        raise CombineError(f"{name} SHA-256 does not match its fragment")
    if archive.stat().st_size != record.get("sizeBytes"):
        raise CombineError(f"{name} size does not match its fragment")
    checksum = _regular(archive.with_name(f"{name}.sha256"))
    fields = checksum.read_text(encoding="utf-8").split()
    if len(fields) != 2 or fields[0] != digest or fields[1].removeprefix("*") != name:
        raise CombineError(f"{name}.sha256 does not match the archive")
    return archive


def _copy_with_checksum(archive: Path, output: Path) -> None:
    for path in (archive, archive.with_name(f"{archive.name}.sha256")):
        shutil.copy2(_regular(path), output / path.name)


def combine(
    *,
    version: str,
    inputs: Sequence[Path],
    output: Path,
    required: Sequence[str],
) -> dict[str, Any]:
    """Write the combined release files to `output` and return the merged provenance."""

    if normalize_version(version) != version:
        raise CombineError(f"release version must be plain SemVer: {version!r}")
    fragments = _read_fragments(version, inputs)
    missing = sorted(set(required) - set(fragments))
    if missing:
        raise CombineError("missing required targets: " + ", ".join(missing))

    output.mkdir(parents=True, exist_ok=True)
    runtimes: list[dict[str, Any]] = []
    notice_sections: list[str] = []
    for directory, fragment in sorted(
        fragments.values(), key=lambda item: str(item[1].get("arch"))
    ):
        arch = fragment.get("arch")
        if not isinstance(arch, str) or not arch:
            raise CombineError(f"fragment has no arch: {fragment['target']}")
        for record in ARCHIVE_RECORDS:
            _copy_with_checksum(
                _checked_archive(directory, fragment.get(record)), output
            )
        shutil.copy2(
            _regular(directory / inventory_name(arch)), output / inventory_name(arch)
        )
        notices = _regular(directory / notices_name(arch)).read_text(encoding="utf-8")
        notice_sections.append(
            f"===== {fragment['target']} ({arch}) =====\n\n{notices.rstrip()}\n"
        )
        runtimes.append(fragment)

    provenance = {
        "schemaVersion": SCHEMA_VERSION,
        "releaseTag": release_tag(version),
        "runtimes": runtimes,
    }
    (output / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    header = f"Arknights macOS Runtime {release_tag(version)} third-party notices\n"
    (output / "THIRD-PARTY-NOTICES.txt").write_text(
        "\n".join([header, *notice_sections]), encoding="utf-8"
    )
    return provenance


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="plain SemVer version")
    parser.add_argument(
        "--input",
        type=Path,
        action="append",
        required=True,
        dest="inputs",
        help="directory of lane outputs; repeat for each lane",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--require",
        default=",".join(REQUIRED_TARGETS),
        help="comma-separated targets that must be present",
    )
    parsed = parser.parse_args(arguments)
    required = [name for name in parsed.require.split(",") if name]
    try:
        combine(
            version=parsed.version,
            inputs=parsed.inputs,
            output=parsed.output,
            required=required,
        )
    except (CombineError, ReleaseValidationError, OSError, ValueError) as failure:
        error(str(failure))
        return 1
    success(f"combined release written to {parsed.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
