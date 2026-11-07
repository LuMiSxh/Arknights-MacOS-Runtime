#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Repack the external native-arm64 tree into the client runtime contract.

The external builder ships a signed `wine/` tree. DXMT is built locally for
ARM64EC by `build_dxmt.py`. This wrapper moves both into the `Libraries/` layout,
adds the launcher aliases, and clears the Wine DOS-stub marker from the native DXMT
D3D payloads. It never rewrites bytes inside the signed `wine.app`.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

if __package__:
    from ..build_common import CLEARED_DOS_STUB, ROOT
    from ..lib.console import error, success
    from ..release.licenses import EXTERNAL_NOTICE_FILES
    from ..runtime import LockError, load_lock
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.build_common import CLEARED_DOS_STUB, ROOT
    from scripts.lib.console import error, success
    from scripts.release.licenses import EXTERNAL_NOTICE_FILES
    from scripts.runtime import LockError, load_lock


ARM64_TARGET = "native-arm64"

DXMT_D3D_DLLS = ("d3d10core.dll", "d3d11.dll", "dxgi.dll")

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")

# The top-level notices the runtime archive carries in addition to the upstream
# `Licenses/external/` directory copied from `wine/share/licenses`.
# `EXTERNAL_NOTICE_FILES` is the same set the release verifier checks, so the
# assembled archive and the verifier agree on the shipped notices.


class AssemblyError(RuntimeError):
    """The external tree cannot be assembled into the client contract."""


def _require_directory(path: Path, label: str) -> Path:
    if not path.is_dir():
        raise AssemblyError(f"{label} is not a directory: {path}")
    return path


def _require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise AssemblyError(f"{label} is not a file: {path}")
    return path


def _reject_escaping_link(path: Path, root: Path, resolved_root: Path) -> None:
    relative = path.relative_to(root)
    target = os.readlink(path)
    if target.startswith("/") or "\\" in target or _WINDOWS_DRIVE.match(target):
        raise AssemblyError(f"symlink escapes the runtime root: {relative}")
    try:
        path.resolve(strict=False).relative_to(resolved_root)
    except ValueError as problem:
        raise AssemblyError(
            f"symlink escapes the runtime root: {relative}"
        ) from problem


def _validate_tree(root: Path) -> None:
    """Reject macOS metadata entries and any symlink that escapes the source root."""

    resolved_root = root.resolve()
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        for name in (*directory_names, *file_names):
            path = Path(directory) / name
            relative = path.relative_to(root)
            if any(
                part == "__MACOSX" or part.startswith("._") for part in relative.parts
            ):
                raise AssemblyError(f"metadata entry is not allowed: {relative}")
            if path.is_symlink():
                _reject_escaping_link(path, root, resolved_root)


def _copy_file(source: Path, destination: Path) -> None:
    _require_file(source, "required source file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _clear_dos_stub(path: Path) -> None:
    with path.open("r+b") as file:
        file.seek(64)
        file.write(CLEARED_DOS_STUB)


def _add_launcher_links(wine: Path) -> None:
    bin_directory = wine / "bin"
    wine64 = bin_directory / "wine64"
    if wine64.exists() or wine64.is_symlink():
        raise AssemblyError("Wine/bin/wine64 already exists")
    wine64.symlink_to("wine")
    launcher = bin_directory / "Arknights"
    if launcher.exists() or launcher.is_symlink():
        raise AssemblyError("Wine/bin/Arknights already exists")
    launcher.symlink_to("wine64")


def _render_notice() -> str:
    return """# Third-party notices

This archive repackages the external native-arm64 Wine runtime from
[wine-build-new](https://github.com/riverfog7/wine-build-new).

The `Licenses/external/` directory preserves the upstream `wine/share/licenses`
tree, which records the Wine, FEX, and Mesa notices shipped by the external build.

The runtime adds these notices:

- `Licenses/Wine-LGPL-2.1.txt` — Wine, LGPL-2.1-or-later.
- `Licenses/DXMT-LGPL-2.1.txt` — DXMT, LGPL-2.1-or-later.
- `Licenses/runtime/MIT.txt` — FEX, MIT.
- `Licenses/runtime/Apache-2.0.txt` — MoltenVK, Apache-2.0.

The corresponding-source archive of the same release contains the modified source
and the build scripts.
"""


def _write_notices(archive_root: Path, wine_root: Path) -> None:
    licenses = archive_root / "Licenses"
    if licenses.exists() or (archive_root / "NOTICE.md").exists():
        raise AssemblyError(f"notice output already exists below {archive_root}")

    external = licenses / "external"
    source_licenses = wine_root / "share" / "licenses"
    if source_licenses.is_dir():
        shutil.copytree(source_licenses, external, symlinks=True)
    else:
        external.mkdir(parents=True)

    for filename in EXTERNAL_NOTICE_FILES:
        source = ROOT / "LICENSES" / filename
        _copy_file(source, licenses / filename)

    (archive_root / "NOTICE.md").write_text(_render_notice(), encoding="utf-8")


def assemble(
    wine_root: Path,
    dxmt_root: Path,
    output: Path,
) -> Path:
    """Build the `Libraries/` tree. Returns that directory."""

    wine_root = _require_directory(wine_root, "wine root")
    dxmt_root = _require_directory(dxmt_root, "dxmt root")
    if output.exists():
        raise AssemblyError(f"output already exists: {output}")

    _validate_tree(wine_root)
    _validate_tree(dxmt_root)

    output.mkdir(parents=True)
    archive_root = output.parent

    wine = output / "Wine"
    shutil.copytree(wine_root, wine, symlinks=True)
    _add_launcher_links(wine)

    unix = _require_directory(
        wine / "lib" / "wine" / "aarch64-unix", "Wine aarch64-unix"
    )
    windows = _require_directory(
        wine / "lib" / "wine" / "aarch64-windows", "Wine aarch64-windows"
    )
    _copy_file(dxmt_root / "aarch64-unix" / "winemetal.so", unix / "winemetal.so")
    _copy_file(
        dxmt_root / "aarch64-windows" / "winemetal.dll", windows / "winemetal.dll"
    )

    payload = output / "DXMT" / "x64"
    payload.mkdir(parents=True)
    for name in DXMT_D3D_DLLS:
        destination = payload / name
        _copy_file(dxmt_root / "aarch64-windows" / name, destination)
        _clear_dos_stub(destination)

    _write_notices(archive_root, wine_root)
    return output


def _verify_interface(libraries: Path, interface: dict[str, Any]) -> None:
    for relative in (*interface["executables"], *interface["requiredFiles"]):
        path = libraries / relative
        if not path.exists():
            raise AssemblyError(f"assembled tree is missing: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wine", type=Path, required=True)
    parser.add_argument("--dxmt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        lock = load_lock(target=ARM64_TARGET)
        libraries = assemble(arguments.wine, arguments.dxmt, arguments.output)
        _verify_interface(libraries, lock["interface"])
    except (AssemblyError, LockError, OSError) as caught_error:
        error(str(caught_error))
        return 1
    success(f"assembled {libraries}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
