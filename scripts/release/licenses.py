#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Validate the license index and assemble the license files of the runtime archive.

`LICENSES/index.json` lists every component of the runtime archive. The `generate`
command checks the index against `runtime.lock.json`, the build script, and the
realised component inventory. It then writes `Licenses/` and `NOTICE.md`.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path, PurePosixPath
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if __package__:
    from ..lib.console import error, success, warning
else:
    if str(REPOSITORY_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))
    from lib.console import error, success, warning

LICENSES_DIRECTORY = "LICENSES"
INDEX_NAME = "index.json"
ARCHIVE_LICENSES_DIRECTORY = "Licenses"
ARCHIVE_NOTICE = "NOTICE.md"
SCHEMA_VERSION = 1
BUILD_SCRIPT = "scripts/build-canary.sh"
NIX_INVENTORY_ROLE = "Bundled Nix library"
BUILD_ONLY_NIX_PACKAGES = frozenset(("vulkan-headers",))
REQUIRED_COMPONENTS = frozenset(("Wine", "DXMT", "MoltenVK"))
STATUSES = frozenset(("verified", "unverified"))
BASES = frozenset(("upstream-declared",))
UNKNOWN_LICENSE = "NOASSERTION"

# Each SPDX identifier maps to the files (below LICENSES/) that hold its text.
LICENSE_TEXTS: dict[str, tuple[str, ...]] = {
    "Apache-2.0": ("runtime/Apache-2.0.txt",),
    "Bitstream-Vera": ("runtime/Bitstream-Vera.txt",),
    "BSD-2-Clause": ("runtime/BSD-2-Clause.txt",),
    "BSD-3-Clause": ("runtime/BSD-3-Clause.txt",),
    "bzip2-1.0.6": ("runtime/bzip2-1.0.6.txt",),
    "CC0-1.0": ("runtime/CC0-1.0.txt",),
    "FTL": ("runtime/FTL.txt",),
    "GPL-2.0-only": ("runtime/GPL-2.0.txt",),
    "GPL-2.0-or-later": ("runtime/GPL-2.0.txt",),
    "GPL-3.0-only": ("runtime/GPL-3.0.txt",),
    "GPL-3.0-or-later": ("runtime/GPL-3.0.txt",),
    "IJG": ("runtime/IJG.txt",),
    "LGPL-2.1-only": ("runtime/LGPL-2.1.txt", "Wine-LGPL-2.1.txt", "DXMT-LGPL-2.1.txt"),
    "LGPL-2.1-or-later": (
        "runtime/LGPL-2.1.txt",
        "Wine-LGPL-2.1.txt",
        "DXMT-LGPL-2.1.txt",
    ),
    "LGPL-3.0-only": ("runtime/LGPL-3.0.txt",),
    "LGPL-3.0-or-later": ("runtime/LGPL-3.0.txt",),
    "libpng-2.0": ("runtime/libpng-2.0.txt",),
    "libtiff": ("runtime/libtiff.txt",),
    "LLVM-exception": ("runtime/LLVM-exception.txt",),
    "MIT": ("runtime/MIT.txt", "runtime/MIT-DXMT.txt"),
    "NCSA": ("runtime/NCSA.txt",),
    "OLDAP-2.8": ("runtime/OLDAP-2.8.txt",),
    "SGI-B-2.0": ("runtime/SGI-B-2.0.txt",),
    "Spencer-94": ("runtime/Spencer-94.txt",),
    "TU-Berlin-2.0": ("runtime/TU-Berlin-2.0.txt",),
    "Unicode-DFS-2016": ("runtime/Unicode-DFS-2016.txt",),
    "Zlib": ("runtime/Zlib.txt",),
}
# The LGPL-3.0 text refers to the GPL-3.0 text.
COMPANION_LICENSES = {
    "LGPL-3.0-only": "GPL-3.0-only",
    "LGPL-3.0-or-later": "GPL-3.0-only",
}
SPDX_OPERATORS = frozenset(("AND", "OR", "WITH"))
SPDX_TOKEN = re.compile(r"[A-Za-z0-9.+-]+|[()]")
NIX_BUILD_PACKAGES = re.compile(r"for package in ([^;]+); do")
NIX_STORE_NAME = re.compile(
    r"^(?:[0-9a-z]{32}-)?(?P<pname>.+?)-(?P<version>\d.*?)"
    r"(?:-(?P<output>bin|dev|lib|man|doc|info|devdoc|static))?$"
)
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")


class LicenseError(ValueError):
    """The license index or the license files are incomplete or inconsistent."""


def spdx_identifiers(expression: str) -> set[str]:
    """Return the license and exception identifiers of an SPDX expression."""

    tokens = SPDX_TOKEN.findall(expression)
    if not tokens or "".join(tokens) != re.sub(r"\s+", "", expression):
        raise LicenseError(f"invalid SPDX expression: {expression!r}")
    return {token for token in tokens if token not in SPDX_OPERATORS | {"(", ")"}}


def _known(identifier: str) -> bool:
    return identifier in LICENSE_TEXTS or identifier == UNKNOWN_LICENSE


def _safe_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and "." not in path.parts


def load_index(licenses_root: Path) -> dict[str, Any]:
    path = licenses_root / INDEX_NAME
    try:
        index = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as problem:
        raise LicenseError(f"cannot read license index: {path}") from problem
    if not isinstance(index, dict):
        raise LicenseError("license index must be a JSON object")
    return index


def _regular(licenses_root: Path, relative: str) -> bool:
    path = licenses_root / relative
    return path.is_file() and not path.is_symlink() and path.stat().st_size > 0


def _lock_entry(lock: dict[str, Any], dotted: str) -> Any:
    node: Any = lock
    for part in dotted.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    return node


def _component_problems(
    component: Any, licenses_root: Path, lock: dict[str, Any]
) -> list[str]:
    if not isinstance(component, dict):
        return ["a component entry is not an object"]
    name = component.get("name")
    label = name if isinstance(name, str) and name else "<unnamed component>"
    problems: list[str] = []

    def problem(message: str) -> None:
        problems.append(f"{label}: {message}")

    for key in ("name", "version", "spdx", "source", "status"):
        if not isinstance(component.get(key), str) or not component[key].strip():
            problem(f"missing {key}")
    if not str(component.get("source", "")).startswith("https://") and not str(
        component.get("source", "")
    ).startswith("http://"):
        problem("source must be an URL")
    status = component.get("status")
    if "note" in component and not (
        isinstance(component["note"], str) and component["note"].strip()
    ):
        problem("note must be a non-empty string")
    if isinstance(status, str) and status not in STATUSES:
        problem(f"unknown status {status!r}")
    basis = component.get("basis")
    if basis is not None and basis not in BASES:
        problem(f"unknown basis {basis!r}")

    files = component.get("files")
    if not isinstance(files, list) or not files:
        problem("files must be a non-empty list")
        files = []
    for relative in files:
        if not _safe_relative(relative):
            problem(f"unsafe file path {relative!r}")
        elif not _regular(licenses_root, relative):
            problem(f"missing or empty license file {relative}")
    notice = component.get("notice")
    if notice is not None:
        if not _safe_relative(notice):
            problem(f"unsafe notice path {notice!r}")
        elif not _regular(licenses_root, notice):
            problem(f"missing or empty notice file {notice}")

    identifiers: set[str] = set()
    expression = component.get("spdx")
    if isinstance(expression, str) and expression.strip():
        try:
            identifiers = spdx_identifiers(expression)
        except LicenseError as invalid:
            problem(str(invalid))
        if expression == UNKNOWN_LICENSE:
            if status != "unverified":
                problem(f"{UNKNOWN_LICENSE} requires the status unverified")
            if notice is None:
                problem(f"{UNKNOWN_LICENSE} requires a notice that explains the gap")
            candidates = component.get("candidates", [])
            if not isinstance(candidates, list):
                problem("candidates must be a list")
                candidates = []
            identifiers = {item for item in candidates if isinstance(item, str)}
        elif "candidates" in component:
            problem("candidates are only allowed with NOASSERTION")
    for identifier in sorted(identifiers):
        if not _known(identifier):
            problem(f"unknown SPDX identifier {identifier}")
            continue
        for needed in (identifier, COMPANION_LICENSES.get(identifier)):
            if needed and not set(LICENSE_TEXTS[needed]) & set(files):
                problem(f"no license text for {needed} in files")

    nix_packages = component.get("nixPackages")
    if nix_packages is not None and (
        not isinstance(nix_packages, list)
        or not nix_packages
        or not all(isinstance(item, str) and item for item in nix_packages)
    ):
        problem("nixPackages must be a non-empty list of names")

    lock_key = component.get("lock")
    if isinstance(lock_key, str):
        pin = _lock_entry(lock, lock_key)
        if not isinstance(pin, dict):
            problem(f"lock entry {lock_key} does not exist")
        else:
            if str(pin.get("commit")) not in str(component.get("source", "")):
                problem(f"source does not name the locked commit of {lock_key}")
            if "version" in pin and pin["version"] != component.get("version"):
                problem(f"version does not match {lock_key}.version")
    return problems


def direct_nix_packages(build_script: Path) -> set[str]:
    """Return the Nix packages that the build script builds and links against."""

    try:
        script = build_script.read_text(encoding="utf-8")
    except OSError as problem:
        raise LicenseError(f"cannot read build script: {build_script}") from problem
    match = NIX_BUILD_PACKAGES.search(script)
    if match is None:
        raise LicenseError("build script has no Nix package list")
    return set(match.group(1).split())


def validate_index(
    index: dict[str, Any],
    *,
    licenses_root: Path,
    lock: dict[str, Any],
    nix_packages: set[str],
) -> None:
    """Raise `LicenseError` with every problem found in the index."""

    problems: list[str] = []
    if index.get("schemaVersion") != SCHEMA_VERSION:
        problems.append(f"schemaVersion must be {SCHEMA_VERSION}")
    nixpkgs_commit = (index.get("nixpkgs") or {}).get("commit")
    locked_commit = _lock_entry(lock, "build.nixpkgs.commit")
    if nixpkgs_commit != locked_commit:
        problems.append("nixpkgs commit does not match runtime.lock.json")
    components = index.get("components")
    if not isinstance(components, list) or not components:
        raise LicenseError(
            "; ".join([*problems, "components must be a non-empty list"])
        )

    seen: set[str] = set()
    covered: set[str] = set()
    referenced: set[str] = set()
    for component in components:
        problems.extend(_component_problems(component, licenses_root, lock))
        if not isinstance(component, dict):
            continue
        name = component.get("name")
        if name in seen:
            problems.append(f"duplicate component {name}")
        seen.add(str(name))
        covered.update(component.get("nixPackages") or [])
        for key in ("files", "notice"):
            value = component.get(key)
            referenced.update(value if isinstance(value, list) else [value])
    excluded = {
        item.get("name", "").lower()
        for item in index.get("excluded", [])
        if isinstance(item, dict)
    }
    for required in sorted(REQUIRED_COMPONENTS - seen):
        problems.append(f"shipped component has no entry: {required}")
    for package in sorted(nix_packages - covered):
        if package not in BUILD_ONLY_NIX_PACKAGES:
            problems.append(f"shipped Nix package has no entry: {package}")
        elif package not in excluded:
            problems.append(
                f"build-only Nix package is not listed as excluded: {package}"
            )

    for path in sorted(licenses_root.rglob("*")):
        relative = path.relative_to(licenses_root).as_posix()
        if path.is_file() and relative != INDEX_NAME and relative not in referenced:
            problems.append(f"license file is not listed in the index: {relative}")
    for relative in index.get("textOrigins", {}):
        if relative not in referenced:
            problems.append(f"textOrigins names an unlisted file: {relative}")
    if problems:
        raise LicenseError("\n".join(problems))


def parse_inventory(text: str) -> list[dict[str, str]]:
    """Return the Nix library rows of the runtime component inventory."""

    rows = [line.split("\t") for line in text.splitlines()]
    if not rows or rows[0] != ["component", "role", "source"]:
        raise LicenseError("runtime component inventory has invalid syntax")
    libraries = []
    for row in rows[1:]:
        if len(row) == 3 and row[1] == NIX_INVENTORY_ROLE:
            match = NIX_STORE_NAME.match(row[0])
            if match is None:
                raise LicenseError(f"cannot read Nix store name: {row[0]}")
            libraries.append(
                {"store": row[0], "pname": match["pname"], "version": match["version"]}
            )
    return libraries


def resolve_shipped(
    index: dict[str, Any], libraries: list[dict[str, str]]
) -> dict[str, Any]:
    """Return the index of the shipped components with the realised Nix versions."""

    by_package = {
        package: component
        for component in index["components"]
        for package in component.get("nixPackages", [])
    }
    realised: dict[str, list[dict[str, str]]] = {}
    unknown = []
    for library in libraries:
        component = by_package.get(library["pname"])
        if component is None:
            unknown.append(library["store"])
        else:
            realised.setdefault(component["name"], []).append(library)
    if unknown:
        raise LicenseError(
            "shipped Nix library has no license entry: " + ", ".join(sorted(unknown))
        )
    shipped = []
    for component in index["components"]:
        if "nixPackages" not in component:
            shipped.append(component)
        elif component["name"] in realised:
            found = realised[component["name"]]
            shipped.append(
                {
                    **component,
                    "version": ", ".join(sorted({item["version"] for item in found})),
                    "realised": sorted({item["store"] for item in found}),
                }
            )
    return {**index, "components": shipped}


def render_notice(index: dict[str, Any], licenses_root: Path) -> str:
    components = index["components"]
    lines = [
        "# Third-party notices",
        "",
        "This runtime archive contains the components in the table below.",
        f"The `{ARCHIVE_LICENSES_DIRECTORY}/` directory holds their license texts.",
        f"The file `{ARCHIVE_LICENSES_DIRECTORY}/{INDEX_NAME}` lists the same data for tools.",
        "",
        "| Component | Version | License (SPDX) | Status | License files |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in components:
        files = ", ".join(
            f"[{Path(name).name}]({ARCHIVE_LICENSES_DIRECTORY}/{name})"
            for name in item["files"]
        )
        lines.append(
            f"| {item['name']} | {item['version']} | {item['spdx']} | {item['status']} | {files} |"
        )
    lines += [
        "",
        "Status `verified` means that the license text is the canonical text of the stated license.",
        "Basis `upstream-declared` means that the license comes from the published terms of the upstream project.",
        "This project has not compared the license file of the exact shipped version.",
        "Status `unverified` means that the license is unknown or in conflict. The notice of the component explains the gap.",
    ]
    notices = sorted({item["notice"] for item in components if "notice" in item})
    if notices:
        lines += ["", "## Notices"]
    for relative in notices:
        owners = ", ".join(i["name"] for i in components if i.get("notice") == relative)
        text = (licenses_root / relative).read_text(encoding="utf-8").rstrip()
        lines += [
            "",
            f"### {owners}",
            "",
            *(f"    {line}".rstrip() for line in text.splitlines()),
        ]
    lines += [
        "",
        "## Source code",
        "",
        "- Wine and DXMT: The corresponding-source archive of the same release contains the modified source and the build scripts.",
        "- MoltenVK: This project does not build MoltenVK. The upstream commit in the table identifies the source.",
        f"- Nix libraries: The release does not contain their source. The nixpkgs revision `{index['nixpkgs']['commit']}` identifies the exact packages.",
        "  An offer of the corresponding source for these libraries is not yet in place.",
        "",
    ]
    return "\n".join(lines)


def generate(
    repository_root: Path,
    output: Path | None,
    *,
    inventory: Path | None = None,
) -> dict[str, Any]:
    """Validate the index. If `output` is set, write `Licenses/` and `NOTICE.md` there."""

    licenses_root = repository_root / LICENSES_DIRECTORY
    try:
        lock = json.loads((repository_root / "runtime.lock.json").read_text("utf-8"))
    except (OSError, ValueError) as problem:
        raise LicenseError("cannot read runtime.lock.json") from problem
    index = load_index(licenses_root)
    validate_index(
        index,
        licenses_root=licenses_root,
        lock=lock,
        nix_packages=direct_nix_packages(repository_root / BUILD_SCRIPT),
    )
    shipped = index
    if inventory is not None:
        try:
            text = inventory.read_text(encoding="utf-8")
        except OSError as problem:
            raise LicenseError(f"cannot read inventory: {inventory}") from problem
        shipped = resolve_shipped(index, parse_inventory(text))
    if output is None:
        return shipped

    destination = output / ARCHIVE_LICENSES_DIRECTORY
    if destination.exists() or (output / ARCHIVE_NOTICE).exists():
        raise LicenseError(f"output already exists below {output}")
    needed = {
        relative
        for item in shipped["components"]
        for relative in (
            *item["files"],
            *([item["notice"]] if "notice" in item else []),
        )
    }
    for relative in sorted(needed):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(licenses_root / relative, target)
    shipped = {
        **shipped,
        "textOrigins": {
            key: value for key, value in shipped["textOrigins"].items() if key in needed
        },
    }
    (destination / INDEX_NAME).write_text(
        json.dumps(shipped, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / ARCHIVE_NOTICE).write_text(
        render_notice(shipped, licenses_root), encoding="utf-8"
    )
    return shipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("generate", help="validate and assemble the files")
    command.add_argument(
        "--check", action="store_true", help="validate only; write nothing"
    )
    command.add_argument(
        "--inventory", type=Path, help="runtime-component-inventory.tsv"
    )
    command.add_argument(
        "--output", type=Path, help="directory for Licenses/ and NOTICE.md"
    )
    command.add_argument(
        "--strict",
        action="store_true",
        help="fail on components with status unverified",
    )
    arguments = parser.parse_args()
    if not arguments.check and arguments.output is None:
        parser.error("generate needs --output unless --check is set")
    try:
        shipped = generate(
            REPOSITORY_ROOT,
            None if arguments.check else arguments.output,
            inventory=arguments.inventory,
        )
    except (LicenseError, OSError) as problem:
        for line in str(problem).splitlines():
            error(line)
        return 1
    unverified = [
        c["name"] for c in shipped["components"] if c["status"] == "unverified"
    ]
    if unverified:
        warning("unverified licenses: " + ", ".join(unverified))
        if arguments.strict:
            error("--strict: unverified licenses remain")
            return 1
    success(f"{len(shipped['components'])} components checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
