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
ARCHIVE_SUFFIX = ".tar.xz"
LEGACY_ARCHIVE_SUFFIX = ".tar.gz"
RUNTIME_ROOT = "Runtime"


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


def runtime_archive_name(arch: str) -> str:
    return f"runtime-{arch}{ARCHIVE_SUFFIX}"


def manifest_name(arch: str) -> str:
    return f"runtime-{arch}.json"


def source_archive_name(arch: str) -> str:
    return f"source-{arch}{ARCHIVE_SUFFIX}"


def delta_archive_name(arch: str, source: str) -> str:
    """Return the name of the delta from the bare version `source` to this release."""

    return f"runtime-{arch}-from-{source}.delta{ARCHIVE_SUFFIX}"


def legacy_runtime_archive_stem(version: str, arch: str) -> str:
    """Return the stem of the asset names before archive schema 3, as in `...-v1.0.1-arm64`.

    Those releases published `<stem>.tar.gz` with a `.sha256` sidecar. Only the delta
    builder reads them, to fetch the previous release.
    """

    return f"Arknights-MacOS-Runtime-{release_tag(version)}-{arch}"


def provenance_name(arch: str) -> str:
    return f"provenance-{arch}.json"


def inventory_name(arch: str) -> str:
    return f"inventory-{arch}.tsv"


def notices_name(arch: str) -> str:
    return f"THIRD-PARTY-NOTICES-{arch}.txt"
