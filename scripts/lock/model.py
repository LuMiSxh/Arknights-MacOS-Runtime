# SPDX-License-Identifier: MPL-2.0

"""Typed view of `runtime.lock.json` (schema 4).

The lock holds the pins of every lane, one patch registry, and the inputs of the
wine-build-new export. `scripts/lock/parse.py` builds these values from the JSON, so
callers get checked values and never read raw JSON.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = ROOT / "runtime.lock.json"
# The runtime archive format. The lock no longer pins it; the release provenance records it.
ARCHIVE_SCHEMA_VERSION = 3
DEFAULT_LANE = "rosetta-x86_64"
REQUIRED_SOURCES = ("wine", "dxmt")
# Where a lane's files sit in the staged `Libraries/` tree. The installed root drops both.
STAGED_WINE = "Wine"
DXMT_ARCHITECTURE = "x64"


class LockError(ValueError):
    """The runtime lock is unsafe or internally inconsistent."""


@dataclass(frozen=True, slots=True)
class Source:
    """One pinned upstream checkout."""

    repository: str
    commit: str
    version: str | None = None


@dataclass(frozen=True, slots=True)
class SourcePin:
    """One immutable upstream source identity monitored by this repository."""

    name: str
    repository: str
    commit: str


@dataclass(frozen=True, slots=True)
class Download:
    """One archive pinned by URL and SHA-256."""

    url: str
    sha256: str


@dataclass(frozen=True, slots=True)
class Artifact:
    """A release of an external catalog, pinned by id and SHA-256."""

    catalog: str
    release: str
    sha256: str


@dataclass(frozen=True, slots=True)
class Base:
    """The third-party base archive of a built lane and the pins that describe it."""

    download: Download
    recipe: Source
    provenance: Mapping[str, Source]


@dataclass(frozen=True, slots=True)
class Launcher:
    """The launcher link that the client starts, and the binary it points at."""

    path: str
    target: str


@dataclass(frozen=True, slots=True)
class DxmtPayload:
    """The DXMT PE libraries that the client copies into the prefix."""

    directory: str
    destinations: Mapping[str, str]
    libraries: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Interface:
    """What a lane ships, relative to the installed runtime root."""

    executables: tuple[str, ...]
    required_files: tuple[str, ...]
    mac_driver: str
    launcher: Launcher
    dxmt: DxmtPayload
    features: Mapping[str, bool]

    def staged_paths(self) -> tuple[str, ...]:
        """Return the files that the staged `Libraries/` tree must contain."""

        wine = (self.launcher.path, *self.executables, *self.required_files)
        dxmt = (
            f"{self.dxmt.directory}/{DXMT_ARCHITECTURE}/{name}"
            for name in self.dxmt.libraries
        )
        return (*(f"{STAGED_WINE}/{path}" for path in wine), *dxmt)


@dataclass(frozen=True, slots=True)
class Lane:
    """One runtime lane: its build mode, sources, base or artifact, and interface."""

    name: str
    arch: str
    build: str
    minimum_macos: str
    sources: Mapping[str, Source]
    interface: Interface
    base: Base | None
    artifact: Artifact | None


@dataclass(frozen=True, slots=True)
class PatchFile:
    """The file that one lane applies for a patch, and its SHA-256."""

    path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class Patch:
    """One entry of the patch registry. `files` maps each carrying lane to its file."""

    number: int
    id: str
    component: str
    gate: str | None
    default: bool
    files: Mapping[str, PatchFile]


@dataclass(frozen=True, slots=True)
class WineBuildNewExport:
    """The inputs of the wine-build-new export that the lock pins."""

    lane: str
    wine_base: str
    queue_before: int
    first_order: int
    optional_patches: frozenset[str]


@dataclass(frozen=True, slots=True)
class Lock:
    """A validated runtime lock."""

    llvm_mingw: Download | None
    nixpkgs: Source
    lanes: Mapping[str, Lane]
    patches: tuple[Patch, ...]
    export: WineBuildNewExport

    def lane(self, name: str | None = None) -> Lane:
        """Return one lane, or the default lane when `name` is None."""

        key = DEFAULT_LANE if name is None else name
        if key not in self.lanes:
            raise LockError(
                f"unknown lane {key!r}; expected one of {', '.join(sorted(self.lanes))}"
            )
        return self.lanes[key]


def monitored_sources(lock: Lock) -> tuple[SourcePin, ...]:
    """Return every source pin of the default lane, plus the shared nixpkgs pin."""

    lane = lock.lane()
    pins = [
        SourcePin(name, source.repository, source.commit)
        for name, source in lane.sources.items()
    ]
    if lane.base is not None:
        pins.append(
            SourcePin(
                "buildRecipe", lane.base.recipe.repository, lane.base.recipe.commit
            )
        )
        pins.extend(
            SourcePin(name, source.repository, source.commit)
            for name, source in lane.base.provenance.items()
        )
    pins.append(SourcePin("nixpkgs", lock.nixpkgs.repository, lock.nixpkgs.commit))
    return tuple(pins)
