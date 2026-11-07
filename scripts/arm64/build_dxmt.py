#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Build the pinned DXMT source for ARM64EC at the lock deployment target.

DXMT links `winemetal.dll` against Wine's PE import libraries and links
`winemetal.so` against `winemac.so`. The external v5 install tree has no import
libraries, so this script also builds a minimal Wine build tree from
`sources.wine`. That tree is a build dependency and is never shipped. The macOS
driver `winemac.so` comes from the external tree. The shipped Wine payload stays
the external v5 tree.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__:
    from ..build_common import (
        Builder,
        BuildError,
        is_macho,
        logical_cpu_count,
        write_dxmt_native_file,
    )
    from ..lib.console import error, success
    from ..runtime import LockError, load_lock
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.build_common import (
        Builder,
        BuildError,
        is_macho,
        logical_cpu_count,
        write_dxmt_native_file,
    )
    from scripts.lib.console import error, success
    from scripts.runtime import LockError, load_lock


ARM64_TARGET = "native-arm64"

WINE_SOURCE_DIRECTORY = "wine-build-source"
DXMT_SOURCE_DIRECTORY = "dxmt-source"
WINE_BUILD_DIRECTORY = "wine-build"
DXMT_BUILD_DIRECTORY = "dxmt-build"
DXMT_INSTALL_DIRECTORY = "dxmt"
EXTERNAL_WINE_DIRECTORY = Path("incoming") / "wine"

MINIMAL_WINE_TARGETS = (
    "tools/winebuild",
    "libs/winecrt0",
    "dlls/ntdll",
    "dlls/dbghelp",
)

REQUIRED_DXMT_FILES = (
    "aarch64-unix/winemetal.so",
    "aarch64-windows/d3d10core.dll",
    "aarch64-windows/d3d11.dll",
    "aarch64-windows/dxgi.dll",
    "aarch64-windows/winemetal.dll",
)

LC_BUILD_VERSION = 0x32
LC_VERSION_MIN_MACOSX = 0x24
MACHO_64 = 0xFEEDFACF
MACHO_64_REVERSED = 0xCFFAEDFE


def parse_version(value: str) -> tuple[int, int]:
    """Return the major and minor components of a deployment target string."""

    parts = value.split(".")
    try:
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except (IndexError, ValueError) as problem:
        raise BuildError(f"invalid deployment target: {value}") from problem


def deployment_target(lock: dict[str, Any], environment: dict[str, str]) -> str:
    """Return the lock deployment target and reject an inconsistent environment."""

    deployment = str(lock["deploymentTarget"])
    requested = environment.get("MACOSX_DEPLOYMENT_TARGET", deployment)
    if requested != deployment:
        raise BuildError(
            f"MACOSX_DEPLOYMENT_TARGET must be {deployment}, not {requested}"
        )
    return deployment


def macho_minimum_macos(path: Path) -> tuple[int, int] | None:
    """Read `LC_BUILD_VERSION` or `LC_VERSION_MIN_MACOSX` from a thin Mach-O."""

    data = path.read_bytes()
    if len(data) < 32:
        return None
    if struct.unpack_from("<I", data, 0)[0] == MACHO_64:
        endian = "<"
    elif struct.unpack_from("<I", data, 0)[0] == MACHO_64_REVERSED:
        endian = ">"
    else:
        return None

    command_count = struct.unpack_from(f"{endian}I", data, 16)[0]
    offset = 32
    for _ in range(command_count):
        if offset + 8 > len(data):
            raise BuildError(f"{path} has a truncated Mach-O load command")
        command, command_size = struct.unpack_from(f"{endian}II", data, offset)
        if command_size < 8 or offset + command_size > len(data):
            raise BuildError(f"{path} has a malformed Mach-O load command")
        if command == LC_BUILD_VERSION and command_size >= 24:
            minos = struct.unpack_from(f"{endian}I", data, offset + 12)[0]
            return minos >> 16, (minos >> 8) & 0xFF
        if command == LC_VERSION_MIN_MACOSX and command_size >= 16:
            version = struct.unpack_from(f"{endian}I", data, offset + 8)[0]
            return version >> 16, (version >> 8) & 0xFF
        offset += command_size
    return None


def reject_macho_above(root: Path, maximum: tuple[int, int]) -> None:
    """Reject a Mach-O in the DXMT install whose `minos` is above the floor."""

    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file() or not is_macho(path):
            continue
        minimum = macho_minimum_macos(path)
        if minimum is not None and minimum > maximum:
            raise BuildError(
                f"{path.relative_to(root)} records minos "
                f"{minimum[0]}.{minimum[1]}, above "
                f"{maximum[0]}.{maximum[1]}"
            )


def meson_setup_command(
    build: Path,
    source: Path,
    native_file: Path,
    llvm: Path,
    wine_build: Path,
    install: Path,
    *,
    reconfigure: bool = False,
) -> list[str]:
    """Return the Meson setup command for the ARM64EC DXMT build."""

    command = ["meson", "setup"]
    if reconfigure:
        command.append("--reconfigure")
    command += [
        str(build),
        str(source),
        "--cross-file",
        str(source / "build-arm64ec.txt"),
        "--native-file",
        str(native_file),
        f"-Dnative_llvm_path={llvm}",
        # The external install tree lacks import libraries, so DXMT must link
        # against the minimal Wine build tree instead.
        f"-Dwine_build_path={wine_build}",
        "--buildtype",
        "release",
        "--prefix",
        str(install),
        "--strip",
    ]
    return command


def verify_dxmt_install(install: Path) -> None:
    """Require every DXMT payload that the assembled runtime consumes."""

    for relative in REQUIRED_DXMT_FILES:
        if not (install / relative).is_file():
            raise BuildError(f"the DXMT install is missing {relative}")


def _brew_prefix(builder: Builder, formula: str) -> str:
    try:
        return builder.capture("brew", "--prefix", formula, allow_failure=True).strip()
    except OSError:
        return ""


def _prepend_homebrew_bin(builder: Builder, formula: str) -> None:
    prefix = _brew_prefix(builder, formula)
    if prefix:
        path = builder.environment.get("PATH", "")
        builder.environment["PATH"] = f"{Path(prefix) / 'bin'}:{path}"


def _resolve_llvm(builder: Builder, candidate: Path | None) -> Path:
    value = candidate or os.environ.get("LLVM_ROOT")
    llvm = Path(value) if value else Path(_brew_prefix(builder, "llvm@15"))
    if not (llvm / "bin" / "llvm-config").is_file():
        raise BuildError("set --llvm or LLVM_ROOT to an LLVM 15 install")
    return llvm.resolve()


def _resolve_llvm_mingw(builder: Builder, candidate: Path | None) -> None:
    value = candidate or os.environ.get("LLVM_MINGW_ROOT")
    if value:
        root = Path(value).resolve()
        if not root.is_dir():
            raise BuildError(f"the llvm-mingw root is not a directory: {root}")
        path = builder.environment.get("PATH", "")
        builder.environment["PATH"] = f"{root / 'bin'}:{path}"
        builder.environment["LLVM_MINGW_ROOT"] = str(root)
    for triple in ("arm64ec-w64-mingw32", "aarch64-w64-mingw32"):
        if (
            shutil.which(f"{triple}-clang", path=builder.environment.get("PATH"))
            is None
        ):
            raise BuildError(
                f"{triple}-clang is missing; set --llvm-mingw or LLVM_MINGW_ROOT"
            )


def _require_bison_3(builder: Builder) -> None:
    version = builder.capture("bison", "--version")
    match = re.search(r"(\d+)\.(\d+)", version)
    if match is None or int(match.group(1)) < 3:
        raise BuildError("Wine needs bison 3 or later; use the Homebrew bison")


def _prepare_toolchain(builder: Builder) -> None:
    _prepend_homebrew_bin(builder, "bison")
    builder.require(
        "git",
        "make",
        "meson",
        "ninja",
        "bison",
        "flex",
        "pkg-config",
        "xcrun",
        "codesign",
    )
    _require_bison_3(builder)


def _clone_pinned(
    builder: Builder, repository: str, commit: str, destination: Path
) -> None:
    if destination.exists():
        head = builder.capture("git", "-C", destination, "rev-parse", "HEAD").strip()
        if head != commit:
            raise BuildError(
                f"{destination} is at {head or 'an unknown commit'}, expected {commit}"
            )
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    builder.run(
        "git",
        "clone",
        "--filter=blob:none",
        "--no-checkout",
        repository,
        destination,
    )
    builder.run("git", "checkout", "--detach", commit, cwd=destination)


def _configure_wine(
    builder: Builder, source: Path, build: Path, deployment: str
) -> None:
    build.mkdir(parents=True, exist_ok=True)
    if (build / "Makefile").is_file():
        return
    environment = dict(builder.environment)
    sdk = builder.capture("xcrun", "--show-sdk-path").strip()
    if not sdk:
        raise BuildError("xcrun did not report a macOS SDK path")
    environment["SDKROOT"] = sdk
    environment["MACOSX_DEPLOYMENT_TARGET"] = deployment
    builder.run(
        source / "configure",
        "--host=aarch64-apple-darwin",
        "--enable-archs=arm64ec,aarch64",
        "--disable-tests",
        "--without-x",
        "--without-wayland",
        "--without-oss",
        "--without-alsa",
        "--without-pulse",
        "--without-sane",
        "--without-usb",
        "--without-v4l2",
        "--without-pcap",
        "--without-capi",
        "--without-opencl",
        "--without-cups",
        "--without-ffmpeg",
        "--without-gstreamer",
        "--prefix=/opt/whiskywine",
        cwd=build,
        environment=environment,
    )


def stage_winemac_so(build: Path, wine_install: Path) -> None:
    """Place the external `winemac.so` where DXMT's Meson build expects it.

    DXMT's native `winemetal.so` links `winemac.so` and `ntdll.so`. The minimal
    build produces `ntdll.so`; the macOS driver comes from the external tree.
    """

    destination = build / "dlls" / "winemac.drv" / "winemac.so"
    if destination.is_file():
        return
    source = wine_install / "lib" / "wine" / "aarch64-unix" / "winemac.so"
    if not source.is_file():
        raise BuildError(
            "the external Wine tree has no winemac.so; run fetch_external.py first"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.symlink_to(source)


def _build_minimal_wine(
    builder: Builder, lock: dict[str, Any], root: Path, deployment: str
) -> Path:
    source = root / WINE_SOURCE_DIRECTORY
    wine = lock["sources"]["wine"]
    _clone_pinned(builder, wine["repository"], wine["commit"], source)
    build = root / WINE_BUILD_DIRECTORY
    _configure_wine(builder, source, build, deployment)
    environment = dict(builder.environment)
    environment["SDKROOT"] = builder.capture("xcrun", "--show-sdk-path").strip()
    environment["MACOSX_DEPLOYMENT_TARGET"] = deployment
    builder.run(
        "make",
        f"-j{logical_cpu_count()}",
        *MINIMAL_WINE_TARGETS,
        cwd=build,
        environment=environment,
    )
    stage_winemac_so(build, root / EXTERNAL_WINE_DIRECTORY)
    return build


def _build_dxmt(
    builder: Builder,
    lock: dict[str, Any],
    root: Path,
    llvm: Path,
    wine_build: Path,
    deployment: str,
) -> Path:
    source = root / DXMT_SOURCE_DIRECTORY
    dxmt = lock["sources"]["dxmt"]
    _clone_pinned(builder, dxmt["repository"], dxmt["commit"], source)
    builder.run("git", "submodule", "update", "--init", "--recursive", cwd=source)
    if not (source / "build-arm64ec.txt").is_file():
        raise BuildError("the DXMT source has no build-arm64ec.txt")

    build = root / DXMT_BUILD_DIRECTORY
    install = root / DXMT_INSTALL_DIRECTORY
    native_file = write_dxmt_native_file(root, deployment)
    environment = builder.without_host_build_variables()
    command = meson_setup_command(
        build,
        source,
        native_file,
        llvm,
        wine_build,
        install,
        reconfigure=(build / "build.ninja").is_file(),
    )
    builder.run(*command, environment=environment)
    builder.run("meson", "compile", "-C", build, environment=environment)
    builder.run("meson", "install", "-C", build, environment=environment)
    return install


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=ARM64_TARGET)
    parser.add_argument("--root", type=Path, default=Path(".build/arm64"))
    parser.add_argument("--llvm", type=Path)
    parser.add_argument("--llvm-mingw", type=Path)
    arguments = parser.parse_args()
    try:
        lock = load_lock(target=arguments.target)
        if lock["buildMode"] != "external":
            error(f"the {lock['target']} target is not an external target")
            return 1
        root = arguments.root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        builder = Builder()
        _prepare_toolchain(builder)
        deployment = deployment_target(lock, builder.environment)
        llvm = _resolve_llvm(builder, arguments.llvm)
        _resolve_llvm_mingw(builder, arguments.llvm_mingw)
        wine_build = _build_minimal_wine(builder, lock, root, deployment)
        install = _build_dxmt(builder, lock, root, llvm, wine_build, deployment)
        verify_dxmt_install(install)
        # DXMT is unsigned at install time. Ad-hoc sign only the Mach-O payload;
        # the PE files must keep their Wine builtin marker handling to assembly.
        builder.run(
            "codesign",
            "--force",
            "--sign",
            "-",
            install / "aarch64-unix" / "winemetal.so",
        )
        reject_macho_above(install, parse_version(deployment))
    except (BuildError, LockError, OSError, subprocess.CalledProcessError) as caught:
        error(str(caught))
        return 1
    success(f"built DXMT at {install}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
