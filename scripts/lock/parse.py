# SPDX-License-Identifier: MPL-2.0

"""Parse and validate `runtime.lock.json` into the typed model in `model.py`.

`load_lock` checks the raw shape, every pin, and every patch file hash, so callers never read
raw JSON.
"""

import json
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from scripts.lib.artifact import sha256
from scripts.lock.model import (
    DEFAULT_LANE,
    LOCK_PATH,
    ROOT,
    Artifact,
    Base,
    Download,
    DxmtPayload,
    Interface,
    Lane,
    Launcher,
    Lock,
    LockError,
    Patch,
    PatchFile,
    Source,
    WineBuildNewExport,
)

SCHEMA_VERSION = 4
# Each build mode fixes its minimum macOS. The lock states it and validation rejects drift.
BUILD_MINIMUM_MACOS = {"build": "15.0", "external": "27.0"}
SOURCE_COMPONENTS = ("wine", "dxmt", "fex")
BASE_PROVENANCE = ("moltenvk", "wineGecko")
ALLOWED_REPOSITORY_HOSTS = frozenset({"github.com", "gitlab.winehq.org"})
LANE_KEYS = frozenset(
    {"arch", "build", "minimumMacOS", "sources", "interface", "base", "artifact"}
)
INTERFACE_KEYS = frozenset(
    {
        "executables",
        "requiredFiles",
        "macDriver",
        "launcher",
        "dxmt",
        "features",
    }
)
FEATURE_KEYS = frozenset(
    {"hardwareCursor", "metalFXSpatialUpscaling", "nativeFullscreenSpace"}
)
DXMT_DESTINATIONS = {"x64": "system32"}
LANE_NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")


def _mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LockError(f"{context} must be an object")
    return value


def _required(mapping: dict[str, Any], key: str, context: str) -> Any:
    if key not in mapping:
        raise LockError(f"{context} is missing {key}")
    return mapping[key]


def _exact_keys(mapping: dict[str, Any], allowed: frozenset[str], context: str) -> None:
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise LockError(f"{context} has unknown keys: {', '.join(unknown)}")


def _string(mapping: dict[str, Any], key: str, context: str) -> str:
    value = _required(mapping, key, context)
    if not isinstance(value, str) or not value:
        raise LockError(f"{context}.{key} must be a non-empty string")
    return value


def _hash(mapping: dict[str, Any], key: str, context: str) -> str:
    value = _string(mapping, key, context)
    if HASH_PATTERN.fullmatch(value) is None:
        raise LockError(f"{context}.{key} must be a lowercase SHA-256 hash")
    return value


def _commit(mapping: dict[str, Any], key: str, context: str) -> str:
    value = _string(mapping, key, context)
    if COMMIT_PATTERN.fullmatch(value) is None:
        raise LockError(f"{context}.{key} must be a full commit hash")
    return value


def _integer(mapping: dict[str, Any], key: str, context: str) -> int:
    value = _required(mapping, key, context)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise LockError(f"{context}.{key} must be a non-negative integer")
    return value


def _runtime_path(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise LockError(f"{context} must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise LockError(f"{context} must be a runtime-relative path")
    return value


def _runtime_paths(value: Any, context: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise LockError(f"{context} must be a non-empty array")
    return tuple(
        _runtime_path(entry, f"{context}[{index}]") for index, entry in enumerate(value)
    )


def _file_names(value: Any, context: str) -> tuple[str, ...]:
    names = _runtime_paths(value, context)
    for index, name in enumerate(names):
        if "/" in name:
            raise LockError(f"{context}[{index}] must be a file name")
    return names


def _repository(value: str, context: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_REPOSITORY_HOSTS
        or not parsed.path.endswith(".git")
        or parsed.query
        or parsed.fragment
    ):
        raise LockError(f"{context} must be an allowlisted HTTPS Git repository URL")
    return value


def _source(value: Any, context: str) -> Source:
    mapping = _mapping(value, context)
    _exact_keys(mapping, frozenset({"repository", "commit", "version"}), context)
    repository = _repository(
        _string(mapping, "repository", context), f"{context}.repository"
    )
    commit = _commit(mapping, "commit", context)
    version = mapping.get("version")
    if version is not None and (not isinstance(version, str) or not version):
        raise LockError(f"{context}.version must be a non-empty string")
    return Source(repository, commit, version)


def _download(mapping: dict[str, Any], prefix: str, context: str) -> Download:
    url = _string(mapping, "url", context)
    if not url.startswith(prefix):
        raise LockError(f"{context}.url must start with {prefix}")
    return Download(url, _hash(mapping, "sha256", context))


def _base(value: Any, context: str) -> Base:
    mapping = _mapping(value, context)
    _exact_keys(mapping, frozenset({"url", "sha256", "recipe", "provenance"}), context)
    download = _download(mapping, "https://github.com/", context)
    recipe = _source(_required(mapping, "recipe", context), f"{context}.recipe")
    provenance_map = _mapping(
        _required(mapping, "provenance", context), f"{context}.provenance"
    )
    _exact_keys(provenance_map, frozenset(BASE_PROVENANCE), f"{context}.provenance")
    provenance = {
        name: _source(
            _required(provenance_map, name, f"{context}.provenance"),
            f"{context}.provenance.{name}",
        )
        for name in BASE_PROVENANCE
    }
    return Base(download, recipe, provenance)


def _artifact(value: Any, context: str) -> Artifact:
    mapping = _mapping(value, context)
    _exact_keys(mapping, frozenset({"catalog", "release", "sha256"}), context)
    return Artifact(
        _string(mapping, "catalog", context),
        _string(mapping, "release", context),
        _hash(mapping, "sha256", context),
    )


def _features(value: Any, context: str) -> Mapping[str, bool]:
    features = _mapping(value, context)
    if set(features) != FEATURE_KEYS:
        raise LockError(f"{context} must contain exactly the runtime features")
    for key in sorted(FEATURE_KEYS):
        if type(features[key]) is not bool:
            raise LockError(f"{context}.{key} must be a boolean")
    return features


def _interface(value: Any, context: str) -> Interface:
    mapping = _mapping(value, context)
    _exact_keys(mapping, INTERFACE_KEYS, context)
    launcher = _mapping(_required(mapping, "launcher", context), f"{context}.launcher")
    _exact_keys(launcher, frozenset({"path", "target"}), f"{context}.launcher")
    dxmt = _mapping(_required(mapping, "dxmt", context), f"{context}.dxmt")
    _exact_keys(
        dxmt,
        frozenset({"payloadDirectory", "destinations", "libraries"}),
        f"{context}.dxmt",
    )
    destinations = _mapping(
        _required(dxmt, "destinations", f"{context}.dxmt"),
        f"{context}.dxmt.destinations",
    )
    if destinations != DXMT_DESTINATIONS:
        raise LockError(f"{context}.dxmt.destinations must be {DXMT_DESTINATIONS}")
    return Interface(
        executables=_runtime_paths(
            _required(mapping, "executables", context), f"{context}.executables"
        ),
        required_files=_runtime_paths(
            _required(mapping, "requiredFiles", context), f"{context}.requiredFiles"
        ),
        mac_driver=_runtime_path(
            _required(mapping, "macDriver", context), f"{context}.macDriver"
        ),
        launcher=Launcher(
            _runtime_path(
                _required(launcher, "path", f"{context}.launcher"),
                f"{context}.launcher.path",
            ),
            _string(launcher, "target", f"{context}.launcher"),
        ),
        dxmt=DxmtPayload(
            _runtime_path(
                _required(dxmt, "payloadDirectory", f"{context}.dxmt"),
                f"{context}.dxmt.payloadDirectory",
            ),
            DXMT_DESTINATIONS,
            _file_names(
                _required(dxmt, "libraries", f"{context}.dxmt"),
                f"{context}.dxmt.libraries",
            ),
        ),
        features=_features(
            _required(mapping, "features", context), f"{context}.features"
        ),
    )


def _lane(name: Any, value: Any) -> Lane:
    if not isinstance(name, str) or LANE_NAME.fullmatch(name) is None:
        raise LockError(f"lane name {name!r} must be lowercase")
    context = f"lanes.{name}"
    mapping = _mapping(value, context)
    _exact_keys(mapping, LANE_KEYS, context)
    build = _required(mapping, "build", context)
    if build not in BUILD_MINIMUM_MACOS:
        raise LockError(f"{context}.build must be build or external")
    minimum = _string(mapping, "minimumMacOS", context)
    if minimum != BUILD_MINIMUM_MACOS[build]:
        raise LockError(f"{context}.minimumMacOS must be {BUILD_MINIMUM_MACOS[build]}")
    sources_map = _mapping(_required(mapping, "sources", context), f"{context}.sources")
    missing = [name for name in ("wine", "dxmt") if name not in sources_map]
    if missing:
        raise LockError(f"{context}.sources must pin {', '.join(missing)}")
    unknown = sorted(set(sources_map) - set(SOURCE_COMPONENTS))
    if unknown:
        raise LockError(
            f"{context}.sources has unknown components: {', '.join(unknown)}"
        )
    sources = {
        component: _source(pin, f"{context}.sources.{component}")
        for component, pin in sources_map.items()
    }
    base: Base | None = None
    artifact: Artifact | None = None
    if build == "build":
        if "artifact" in mapping:
            raise LockError(f"{context} must not pin an artifact for a build lane")
        base = _base(_required(mapping, "base", context), f"{context}.base")
    else:
        if "base" in mapping:
            raise LockError(f"{context} must not pin a base for an external lane")
        artifact = _artifact(
            _required(mapping, "artifact", context), f"{context}.artifact"
        )
    return Lane(
        name=name,
        arch=_string(mapping, "arch", context),
        build=build,
        minimum_macos=minimum,
        sources=sources,
        interface=_interface(
            _required(mapping, "interface", context), f"{context}.interface"
        ),
        base=base,
        artifact=artifact,
    )


def _contained_file(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise LockError(f"patch path {relative!r} must be repository-relative")
    path = root / candidate
    if path.is_symlink():
        raise LockError(f"patch path {relative!r} must not be a symlink")
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise LockError(
            f"patch path {relative!r} must be repository-relative"
        ) from error
    if not path.is_file():
        raise LockError(f"patch file does not exist: {relative}")
    return path


def _patch_file(
    value: Any, patch_id: str, lane: str, repository_root: Path
) -> PatchFile:
    context = f"patch {patch_id} for {lane}"
    mapping = _mapping(value, context)
    _exact_keys(mapping, frozenset({"path", "sha256"}), context)
    relative = _string(mapping, "path", context)
    expected = _hash(mapping, "sha256", context)
    actual = sha256(_contained_file(repository_root, relative))
    if actual != expected:
        raise LockError(f"patch {patch_id} hash mismatch: {actual} != {expected}")
    return PatchFile(relative, expected)


def _patches(
    value: Any, lanes: Mapping[str, Lane], repository_root: Path
) -> tuple[Patch, ...]:
    if not isinstance(value, list):
        raise LockError("patches must be an array")
    ids: set[str] = set()
    numbers: set[tuple[str, int]] = set()
    patches: list[Patch] = []
    for index, item in enumerate(value):
        context = f"patches[{index}]"
        mapping = _mapping(item, context)
        _exact_keys(
            mapping,
            frozenset({"id", "component", "number", "gate", "default", "files"}),
            context,
        )
        patch_id = _string(mapping, "id", context)
        if patch_id in ids:
            raise LockError(f"duplicate patch id: {patch_id}")
        ids.add(patch_id)
        component = _string(mapping, "component", context)
        number = _required(mapping, "number", context)
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            raise LockError(f"{context}.number must be a positive integer")
        if (component, number) in numbers:
            raise LockError(f"duplicate {component} patch number: {number}")
        numbers.add((component, number))
        gate = _required(mapping, "gate", context)
        if gate is not None and not isinstance(gate, str):
            raise LockError(f"{context}.gate must be a string or null")
        default = _required(mapping, "default", context)
        if not isinstance(default, bool):
            raise LockError(f"{context}.default must be a boolean")
        files_map = _mapping(_required(mapping, "files", context), f"{context}.files")
        if not files_map:
            raise LockError(f"{context}.files must name at least one lane")
        files: dict[str, PatchFile] = {}
        for lane, file_value in files_map.items():
            if lane not in lanes:
                raise LockError(f"patch {patch_id} names an undeclared lane: {lane}")
            if component not in lanes[lane].sources:
                raise LockError(
                    f"patch {patch_id} uses {component}, "
                    f"which the {lane} lane does not build"
                )
            files[lane] = _patch_file(file_value, patch_id, lane, repository_root)
        patches.append(Patch(number, patch_id, component, gate, default, files))
    return tuple(patches)


def _export(
    value: Any, lanes: Mapping[str, Lane], patches: tuple[Patch, ...]
) -> WineBuildNewExport:
    exports = _mapping(value, "export")
    _exact_keys(exports, frozenset({"wine-build-new"}), "export")
    context = "export.wine-build-new"
    entry = _mapping(_required(exports, "wine-build-new", "export"), context)
    _exact_keys(
        entry,
        frozenset({"lane", "wineBase", "queueBefore", "firstOrder", "optionalPatches"}),
        context,
    )
    lane = _string(entry, "lane", context)
    if (
        lane not in lanes
        or lanes[lane].build != "external"
        or "fex" not in lanes[lane].sources
    ):
        raise LockError(f"{context}.lane must name an external lane with a fex source")
    optional = _required(entry, "optionalPatches", context)
    if not isinstance(optional, list) or not all(
        isinstance(name, str) for name in optional
    ):
        raise LockError(f"{context}.optionalPatches must be an array of patch ids")
    known = {patch.id for patch in patches}
    for name in optional:
        if name not in known:
            raise LockError(f"{context}.optionalPatches names an unknown patch: {name}")
    return WineBuildNewExport(
        lane=lane,
        wine_base=_commit(entry, "wineBase", context),
        queue_before=_integer(entry, "queueBefore", context),
        first_order=_integer(entry, "firstOrder", context),
        optional_patches=frozenset(optional),
    )


def load_lock(path: Path = LOCK_PATH, *, repository_root: Path = ROOT) -> Lock:
    """Read and validate the lock. Patch files are read from `repository_root`."""

    try:
        document = _mapping(json.loads(path.read_text(encoding="utf-8")), "lock")
    except (OSError, json.JSONDecodeError) as error:
        raise LockError(f"cannot read {path}: {error}") from error
    if document.get("schemaVersion") != SCHEMA_VERSION:
        raise LockError(f"schemaVersion must be {SCHEMA_VERSION}")
    _exact_keys(
        document,
        frozenset({"schemaVersion", "shared", "lanes", "patches", "export"}),
        "lock",
    )

    shared = _mapping(_required(document, "shared", "lock"), "shared")
    _exact_keys(shared, frozenset({"toolchain", "nixpkgs"}), "shared")
    toolchain = _mapping(_required(shared, "toolchain", "shared"), "shared.toolchain")
    _exact_keys(toolchain, frozenset({"llvmMingw"}), "shared.toolchain")
    llvm = toolchain.get("llvmMingw")
    llvm_mingw = (
        None
        if llvm is None
        else _download(
            _mapping(llvm, "shared.toolchain.llvmMingw"),
            "https://",
            "shared.toolchain.llvmMingw",
        )
    )
    nixpkgs = _source(_required(shared, "nixpkgs", "shared"), "shared.nixpkgs")

    lanes_map = _mapping(_required(document, "lanes", "lock"), "lanes")
    if DEFAULT_LANE not in lanes_map:
        raise LockError(f"lanes must include the default lane {DEFAULT_LANE}")
    lanes = {name: _lane(name, value) for name, value in lanes_map.items()}
    patches = _patches(_required(document, "patches", "lock"), lanes, repository_root)
    export = _export(_required(document, "export", "lock"), lanes, patches)
    return Lock(llvm_mingw, nixpkgs, lanes, patches, export)
