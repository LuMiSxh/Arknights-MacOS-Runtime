# SPDX-License-Identifier: MPL-2.0

"""The component inventory that every lane writes beside its runtime archive."""

from collections.abc import Sequence
from pathlib import Path

from scripts.lock.model import Lane

HEADER = "component\trole\tsource"
ROLES = {
    "wine": "Windows compatibility runtime",
    "dxmt": "Direct3D-to-Metal payload",
    "fex": "x86 emulation in the external Wine tree",
}
MOLTENVK_SOURCE = (
    "runtime.lock.json:baseArtifact "
    "(SHA-256-pinned third-party base archive; not built from source)"
)


def write_inventory(
    path: Path,
    lane: Lane,
    *,
    nix_libraries: Sequence[str] = (),
    nixpkgs_commit: str = "",
) -> None:
    """Write one row per component that the lane ships.

    The rows follow the lane's sources. A built lane also lists its MoltenVK base and the
    bundled Nix libraries. An external lane names the catalog artifact for Wine and FEX.
    """

    artifact = lane.artifact
    rows = [HEADER]
    for name, role in ROLES.items():
        if name not in lane.sources:
            continue
        if artifact is not None and name == "wine":
            source = (
                f"external catalog artifact {artifact.release} "
                f"(wine-build-new {lane.sources[name].commit})"
            )
            label = "Wine"
        elif artifact is not None and name == "fex":
            source = f"external catalog artifact {artifact.release}"
            label = "FEX"
        else:
            source = f"runtime.lock.json:sources.{name}"
            label = "WineCX/Wine" if name == "wine" else name.upper()
        rows.append(f"{label}\t{role}\t{source}")
    if lane.base is not None:
        rows.append(f"MoltenVK\tVulkan-to-Metal library\t{MOLTENVK_SOURCE}")
    rows.extend(
        f"{Path(library).name}\tBundled Nix library\t{library} (nixpkgs {nixpkgs_commit})"
        for library in nix_libraries
    )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
