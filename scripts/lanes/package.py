# SPDX-License-Identifier: MPL-2.0

"""Write the release outputs that every lane shares.

A lane supplies its runtime tree, its source members, and its inventory. This module writes
the archives and notices, runs the release gates, and records the provenance fragment.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from scripts.lanes import (
    RUNTIME_ROOT,
    Target,
    notices_name,
    provenance_name,
    runtime_archive_name,
    source_archive_name,
)
from scripts.lib.artifact import write_archive
from scripts.release.licenses import third_party_notices
from scripts.release.provenance import (
    runtime_fragment,
    runtime_lock_provenance,
    validation_provenance,
    write_fragment,
)
from scripts.release.toolchain import collect_toolchain
from scripts.release.verify import verify_release


def install_entries(content_root: Path) -> list[tuple[Path, str]]:
    """Map the staged tree to the members of the installed runtime root.

    The children of `Libraries/Wine` become children of `Runtime/`. Every other staged
    library directory keeps its name, such as `DXMT/`. `Licenses/` and `NOTICE.md` are
    included when the lane has them.
    """

    libraries = content_root / "Libraries"
    entries: list[tuple[Path, str]] = []
    for child in sorted(libraries.iterdir()):
        if child.name == "Wine":
            for grandchild in sorted(child.iterdir()):
                entries.append((grandchild, f"{RUNTIME_ROOT}/{grandchild.name}"))
        else:
            entries.append((child, f"{RUNTIME_ROOT}/{child.name}"))
    for name in ("Licenses", "NOTICE.md"):
        if (content_root / name).exists():
            entries.append((content_root / name, f"{RUNTIME_ROOT}/{name}"))
    return entries


def package_runtime(
    *,
    repository_root: Path,
    target: Target,
    version: str,
    release: bool,
    output: Path,
    content_root: Path,
    source_entries: Sequence[tuple[Path, str]],
    source_root: Path,
    inventory: Path,
    validation_report: Path,
    wine: dict[str, Any],
    dxmt: dict[str, Any],
    source_commit: str,
) -> Path:
    """Write the lane outputs and return the path of the provenance fragment.

    A release build runs the release gates. A candidate records its validation report
    without them.
    """

    output.mkdir(parents=True, exist_ok=True)
    runtime_archive = write_archive(
        output,
        runtime_archive_name(target.arch),
        install_entries(content_root),
    )
    source_archive = write_archive(
        output, source_archive_name(target.arch), source_entries
    )
    (output / notices_name(target.arch)).write_text(
        third_party_notices(repository_root, inventory, target.name),
        encoding="utf-8",
    )
    runtime_lock = runtime_lock_provenance(repository_root, target.name)
    if release:
        validation = verify_release(
            repository_root=repository_root,
            version=version,
            commit=source_commit,
            archive=runtime_archive,
            source_root=source_root,
            source_archive=source_archive,
            validation_report=validation_report,
            component_inventory=inventory,
            target=target.name,
        )
    else:
        validation = validation_provenance(
            validation_report,
            runtime_lock["contents"]["deploymentTarget"],
            external=target.wine_source == "external",
            gate=False,
        )
    fragment = runtime_fragment(
        target=target,
        version=version,
        source_commit=source_commit,
        runtime_lock=runtime_lock,
        wine=wine,
        dxmt=dxmt,
        runtime_archive=runtime_archive,
        source_archive=source_archive,
        validation=validation,
        build_toolchain=collect_toolchain(),
    )
    return write_fragment(output / provenance_name(target.arch), fragment)
