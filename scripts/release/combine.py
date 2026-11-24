# SPDX-License-Identifier: MPL-2.0

"""Combine the lane outputs into one release.

Each input directory holds `provenance-<ARCH>.json` fragments and the files they name. The
command checks every archive against its fragment. It then writes
one `provenance.json` and one `THIRD-PARTY-NOTICES.txt` for the release. It needs only the
standard library, so it runs on Linux.
"""

import argparse
import json
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from scripts.lanes import (
    REQUIRED_TARGETS,
    inventory_name,
    notices_name,
    release_tag,
)
from scripts.lib.artifact import sha256
from scripts.lib.console import error, success
from scripts.release.verify import (
    ReleaseValidationError,
    normalize_version,
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
    """Return an archive whose bytes and size match its fragment."""

    if not isinstance(record, dict) or not isinstance(record.get("name"), str):
        raise CombineError("fragment has no archive record")
    name = record["name"]
    if Path(name).name != name or name in ("", ".", ".."):
        raise CombineError(f"archive name is not a plain file name: {name!r}")
    archive = _regular(directory / name)
    if sha256(archive) != record.get("sha256"):
        raise CombineError(f"{name} SHA-256 does not match its fragment")
    if archive.stat().st_size != record.get("sizeBytes"):
        raise CombineError(f"{name} size does not match its fragment")
    return archive


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
            archive = _checked_archive(directory, fragment.get(record))
            shutil.copy2(archive, output / archive.name)
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
