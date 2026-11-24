# SPDX-License-Identifier: MPL-2.0

"""The native-arm64 lane: Wine from the external catalog and DXMT built for ARM64EC.

The catalog URL comes from `ARM64_RUNTIME_CATALOG_URL` and is never printed. The optional
The build fetches exactly the catalog release that `runtime.lock.json` pins.
"""

import shutil
from pathlib import Path

from scripts.build_common import (
    NATIVE_ARM64_TARGET,
    ROOT,
    VALIDATE_COMMAND,
    WINE_BUILD_NEW_REPOSITORY,
    Builder,
)
from scripts.lanes import Target, inventory_name
from scripts.lanes.arm64_assemble import assemble, verify_interface
from scripts.lanes.arm64_dxmt import build_dxmt_arm64
from scripts.lanes.arm64_external import fetch_target, require_external_lock
from scripts.lanes.inventory import write_inventory
from scripts.lanes.package import package_runtime
from scripts.lock.sources import BUILD_ROOT

TARGET = Target(
    name=NATIVE_ARM64_TARGET,
    arch="arm64",
    wine_source="external",
    dxmt_cross_file="build-arm64ec.txt",
    pe_compiler="arm64ec-w64-mingw32",
)


# Repository paths that the corresponding-source archive carries.
SOURCE_REPOSITORY_MEMBERS = (
    "wine-build-new",
    "runtime.lock.json",
    "docs/arm/README.md",
)


def build_runtime(
    builder: Builder,
    *,
    release: bool,
    version: str,
    output: Path,
    source_commit: str,
) -> Path:
    """Build the native-arm64 runtime and return the path of its provenance fragment."""

    lane = require_external_lock(TARGET.name)
    root = BUILD_ROOT / TARGET.arch
    root.mkdir(parents=True, exist_ok=True)
    artifact = fetch_target(lane, root / "incoming")
    install = build_dxmt_arm64(builder, TARGET, lane, root)

    libraries = root / "Libraries"
    for stale in (libraries, root / "Licenses"):
        if stale.exists():
            shutil.rmtree(stale)
    (root / "NOTICE.md").unlink(missing_ok=True)
    assemble(root / "incoming" / "wine", install, libraries, root, lane.interface)
    verify_interface(libraries, lane.interface)

    output.mkdir(parents=True, exist_ok=True)
    inventory = output / inventory_name(TARGET.arch)
    write_inventory(inventory, lane)
    validation_report = root / "validation.json"
    builder.run(
        *VALIDATE_COMMAND,
        libraries,
        "--target",
        TARGET.name,
        "--report",
        validation_report,
        cwd=ROOT,
    )
    return package_runtime(
        repository_root=ROOT,
        target=TARGET,
        version=version,
        release=release,
        output=output,
        content_root=root,
        source_entries=[(ROOT / name, name) for name in SOURCE_REPOSITORY_MEMBERS],
        source_root=ROOT,
        inventory=inventory,
        validation_report=validation_report,
        wine={
            "repository": lane.sources["wine"].repository,
            "commit": lane.sources["wine"].commit,
            "version": lane.sources["wine"].version,
            "externalBuild": {
                "repository": WINE_BUILD_NEW_REPOSITORY,
                "commit": lane.sources["wine"].commit,
            },
            "artifact": {
                "id": artifact["id"],
                "sha256": artifact["sha256"],
                "size": artifact.get("size"),
            },
        },
        dxmt={
            "repository": lane.sources["dxmt"].repository,
            "commit": lane.sources["dxmt"].commit,
            "version": lane.sources["dxmt"].version,
        },
        source_commit=source_commit,
    )
