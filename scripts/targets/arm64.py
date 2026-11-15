# SPDX-License-Identifier: MPL-2.0

"""The native-arm64 lane: Wine from the external catalog and DXMT built for ARM64EC.

The catalog URL comes from `ARM64_RUNTIME_CATALOG_URL` and is never printed. The optional
`ARM64_RELEASE_ID` pins one catalog release. Leave it empty for the newest ARM64 release.
"""

import os
import shutil
import sys
from pathlib import Path

from scripts.build_common import (
    NATIVE_ARM64_TARGET,
    ROOT,
    VALIDATE_CLI,
    WINE_BUILD_NEW_REPOSITORY,
    Builder,
    BuildError,
)
from scripts.runtime import BUILD_ROOT
from scripts.targets import Target, inventory_name
from scripts.targets.arm64_assemble import assemble, verify_interface
from scripts.targets.arm64_dxmt import build_dxmt_arm64
from scripts.targets.arm64_external import fetch_target, require_external_lock
from scripts.targets.package import package_runtime

TARGET = Target(
    name=NATIVE_ARM64_TARGET,
    arch="arm64",
    wine_source="external",
    dxmt_cross_file="build-arm64ec.txt",
    pe_compiler="arm64ec-w64-mingw32",
)

RELEASE_ID_ENVIRONMENT = "ARM64_RELEASE_ID"
# Repository paths that the corresponding-source archive carries.
SOURCE_REPOSITORY_MEMBERS = (
    "wine-build-new",
    "runtime.lock.json",
    "docs/arm/README.md",
)


def write_inventory(path: Path, *, artifact_id: str, wine_revision: str) -> None:
    """Write the component inventory of the components the runtime ships."""

    rows = [
        "component\trole\tsource",
        (
            "Wine\tWindows compatibility runtime\t"
            f"external catalog artifact {artifact_id} (wine-build-new {wine_revision})"
        ),
        "DXMT\tDirect3D-to-Metal payload\truntime.lock.json:sources.dxmt",
        f"FEX\tx86 emulation in the external Wine tree\texternal catalog artifact {artifact_id}",
    ]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def build_runtime(
    builder: Builder,
    *,
    release: bool,
    version: str,
    output: Path,
    source_commit: str,
) -> Path:
    """Build the native-arm64 runtime and return the path of its provenance fragment."""

    lock = require_external_lock(TARGET.name)
    root = BUILD_ROOT / TARGET.arch
    root.mkdir(parents=True, exist_ok=True)
    artifact = fetch_target(
        lock, root / "incoming", os.environ.get(RELEASE_ID_ENVIRONMENT, "").strip()
    )
    install = build_dxmt_arm64(builder, TARGET, lock, root)

    libraries = root / "Libraries"
    for stale in (libraries, root / "Licenses"):
        if stale.exists():
            shutil.rmtree(stale)
    (root / "NOTICE.md").unlink(missing_ok=True)
    assemble(root / "incoming" / "wine", install, libraries, root, lock["interface"])
    verify_interface(libraries, lock["interface"])

    # The fetch may re-pin the lock. The pin that the build records must match the catalog.
    pinned = require_external_lock(TARGET.name)["artifact"]
    if (pinned["release"], pinned["sha256"]) != (artifact["id"], artifact["sha256"]):
        raise BuildError("external artifact metadata does not match the lock pin")

    output.mkdir(parents=True, exist_ok=True)
    inventory = output / inventory_name(TARGET.arch)
    write_inventory(
        inventory,
        artifact_id=str(artifact["id"]),
        wine_revision=str(lock["sources"]["wine"]["commit"]),
    )
    validation_report = root / "validation.json"
    builder.run(
        sys.executable,
        VALIDATE_CLI,
        libraries,
        "--target",
        TARGET.name,
        "--report",
        validation_report,
    )
    return package_runtime(
        repository_root=ROOT,
        target=TARGET,
        version=version,
        release=release,
        output=output,
        content_root=root,
        members=("Libraries", "Licenses", "NOTICE.md"),
        source_entries=[(ROOT / name, name) for name in SOURCE_REPOSITORY_MEMBERS],
        source_root=ROOT,
        inventory=inventory,
        validation_report=validation_report,
        wine={
            "repository": lock["sources"]["wine"]["repository"],
            "commit": lock["sources"]["wine"]["commit"],
            "version": lock["sources"]["wine"]["version"],
            "externalBuild": {
                "repository": WINE_BUILD_NEW_REPOSITORY,
                "commit": lock["sources"]["wine"]["commit"],
            },
            "artifact": {
                "id": artifact["id"],
                "sha256": artifact["sha256"],
                "size": artifact.get("size"),
            },
        },
        dxmt={
            "repository": lock["sources"]["dxmt"]["repository"],
            "commit": lock["sources"]["dxmt"]["commit"],
            "version": lock["sources"]["dxmt"]["version"],
        },
        source_commit=source_commit,
    )
