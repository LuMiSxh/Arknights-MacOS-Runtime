# SPDX-License-Identifier: MPL-2.0

"""Runtime lanes and the facts that tell them apart.

Each lane module defines one `TARGET` and one `build_runtime` function. Shared steps take a
`Target` and never branch on its name. The deployment target comes from `runtime.lock.json`.
"""

from dataclasses import dataclass

from scripts.build_common import NATIVE_ARM64_TARGET

ROSETTA_X86_64_TARGET = "rosetta-x86_64"
REQUIRED_TARGETS = (ROSETTA_X86_64_TARGET, NATIVE_ARM64_TARGET)
WINE_SOURCES = frozenset(("built", "external"))


@dataclass(frozen=True)
class Target:
    """One runtime lane.

    `name` is the lock target. `arch` names the release files. `wine_source` is `built`
    when the lane builds Wine and `external` when it downloads Wine. `dxmt_cross_file` is
    the Meson cross file in the DXMT source tree. `pe_compiler` is the mingw triple whose
    gcc and g++ build DXMT.
    """

    name: str
    arch: str
    wine_source: str
    dxmt_cross_file: str
    pe_compiler: str

    def __post_init__(self) -> None:
        if self.wine_source not in WINE_SOURCES:
            raise ValueError(f"unknown Wine source: {self.wine_source}")

    def dxmt_compilers(self) -> dict[str, str]:
        """Return the Meson compiler names of the DXMT cross build."""

        return {"c": f"{self.pe_compiler}-gcc", "cpp": f"{self.pe_compiler}-g++"}


def release_tag(version: str) -> str:
    """Return the git tag of a bare release version, such as `v0.9.0`."""

    return f"v{version}"


def runtime_archive_name(version: str, arch: str) -> str:
    return f"Arknights-MacOS-Runtime-{release_tag(version)}-{arch}.tar.gz"


def source_archive_name(version: str, arch: str) -> str:
    return f"Arknights-MacOS-Runtime-{release_tag(version)}-{arch}-source.tar.gz"


def provenance_name(arch: str) -> str:
    return f"provenance-{arch}.json"


def inventory_name(arch: str) -> str:
    return f"runtime-component-inventory-{arch}.tsv"


def notices_name(arch: str) -> str:
    return f"THIRD-PARTY-NOTICES-{arch}.txt"
