#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Build a runtime artifact from the pinned lock.

The recipe for each target is docs/arm/pipeline.md and docs/architecture.md.
This module never runs Wine, creates a prefix, or starts a game.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

if __package__:
    from .lib.console import error, info, success
    from .runtime import BUILD_ROOT, LockError, load_lock, prepare
else:
    from lib.console import error, info, success
    from runtime import BUILD_ROOT, LockError, load_lock, prepare

ROOT = Path(__file__).resolve().parents[1]
ARM64_TARGET = "native-arm64"
ARM64_STAGE_ROOT = BUILD_ROOT / "stages" / "arm64"
WINE_NIX_PACKAGES = ("freetype", "gnutls", "vulkan-headers")
BUNDLED_LIBRARIES = ("libfreetype.6.dylib", "libgnutls.30.dylib")
MACHO_MAGIC = (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe")
# Wine's DOS stub marker at offset 64 makes the loader prefer the builtin DLL.
CLEARED_DOS_STUB = bytes.fromhex("0e1fba0e00b409cd21b8014ccd219090")
# The kernel keeps x18 only when the main executable's SDK version is 12.0 or older.
LOADER_SDK_VERSION = "12.0"
HOST_BUILD_VARIABLES = (
    "CFLAGS",
    "CXXFLAGS",
    "CPPFLAGS",
    "LDFLAGS",
    "OBJCFLAGS",
    "CC",
    "CXX",
    "OBJC",
    "SDKROOT",
    "MACOSX_DEPLOYMENT_TARGET",
)


class BuildError(RuntimeError):
    """The build cannot continue."""


@dataclass
class Builder:
    """Run build commands with one explicit environment."""

    environment: dict[str, str] = field(default_factory=lambda: dict(os.environ))

    def run(
        self,
        *command: object,
        cwd: Path | None = None,
        environment: dict[str, str] | None = None,
    ) -> None:
        info("$ " + " ".join(str(part) for part in command))
        subprocess.run(
            [str(part) for part in command],
            cwd=cwd,
            env=environment if environment is not None else self.environment,
            check=True,
        )

    def capture(self, *command: object) -> str:
        return subprocess.run(
            [str(part) for part in command],
            env=self.environment,
            capture_output=True,
            check=True,
            text=True,
        ).stdout

    def require(self, *names: str) -> None:
        for name in names:
            if shutil.which(name, path=self.environment.get("PATH")) is None:
                raise BuildError(f"required command not found: {name}")

    def without_host_build_variables(self) -> dict[str, str]:
        """A PE cross build must not see the host compiler or SDK settings."""

        environment = dict(self.environment)
        for name in HOST_BUILD_VARIABLES:
            environment.pop(name, None)
        return environment


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_archive(directory: Path, member: str, tar_name: str) -> Path:
    """Create the tar.gz and its shasum-compatible checksum file."""

    path = directory / tar_name
    with tarfile.open(path, "w:gz") as tar:
        tar.add(directory / member, arcname=member)
    (directory / f"{tar_name}.sha256").write_text(
        f"{sha256(path)}  {tar_name}\n", encoding="utf-8"
    )
    return path


def logical_cpu_count() -> str:
    return subprocess.run(
        ["sysctl", "-n", "hw.logicalcpu"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()


def is_macho(path: Path) -> bool:
    try:
        with path.open("rb") as file:
            return file.read(4) in MACHO_MAGIC
    except OSError:
        return False


def sign_directory(builder: Builder, directory: Path) -> None:
    for path in sorted(directory.rglob("*")):
        if path.is_symlink() or not path.is_file() or not is_macho(path):
            continue
        builder.run("codesign", "--force", "--sign", "-", path)


def referenced_libraries(builder: Builder, binary: Path) -> list[Path]:
    references: list[Path] = []
    for line in builder.capture("otool", "-L", binary).splitlines()[1:]:
        reference = line.strip().split(" (", 1)[0]
        if reference.startswith("/opt/homebrew/"):
            references.append(Path(reference))
    return references


# --- ARM64 lane ------------------------------------------------------------------


def arm64_environment(builder: Builder, lock: dict[str, object]) -> None:
    """Prepare the toolchain and SDK variables for the ARM64 host build."""

    llvm_mingw_root = Path(
        builder.environment.get(
            "LLVM_MINGW_ROOT", str(BUILD_ROOT / "toolchains" / "llvm-mingw")
        )
    )
    llvm15_root = (
        builder.environment.get("LLVM_ROOT")
        or builder.capture("brew", "--prefix", "llvm@15").strip()
    )
    if not llvm15_root:
        raise BuildError("set LLVM_ROOT to an LLVM 15 install")
    for compiler in ("arm64ec-w64-mingw32-clang", "aarch64-w64-mingw32-clang"):
        if not (llvm_mingw_root / "bin" / compiler).is_file():
            raise BuildError(
                f"{compiler} is missing; set LLVM_MINGW_ROOT to an llvm-mingw release"
            )
    bison_prefix = builder.capture("brew", "--prefix", "bison").strip()
    builder.environment.update(
        PATH=(
            f"{llvm_mingw_root / 'bin'}:{bison_prefix}/bin:"
            f"{builder.environment.get('PATH', '')}"
        ),
        SDKROOT=builder.capture("xcrun", "--show-sdk-path").strip(),
        MACOSX_DEPLOYMENT_TARGET=str(lock["deploymentTarget"]),
        LLVM_MINGW_ROOT=str(llvm_mingw_root),
        LLVM_ROOT=llvm15_root,
        # pipe2 arrives in macOS 27; the deployment target stays at the lock value.
        ac_cv_func_pipe2="no",
        ac_cv_lib_soname_freetype="libfreetype.6.dylib",
        ac_cv_lib_soname_gnutls="libgnutls.30.dylib",
    )


def nix_prefixes(builder: Builder) -> tuple[str, str, str]:
    pkg_config: list[str] = []
    includes: list[str] = []
    libraries: list[str] = []
    for package in WINE_NIX_PACKAGES:
        prefix = Path(builder.capture("brew", "--prefix", package).strip())
        if (prefix / "lib" / "pkgconfig").is_dir():
            pkg_config.append(str(prefix / "lib" / "pkgconfig"))
        if (prefix / "include").is_dir():
            includes.append(f"-I{prefix / 'include'}")
        if (prefix / "lib").is_dir():
            libraries.append(f"-L{prefix / 'lib'}")
    return ":".join(pkg_config), " ".join(includes), " ".join(libraries)


def patch_vulkan_soname(builder: Builder, wine_source: Path) -> None:
    """The arm64 branch reads SONAME_LIBVULKAN in a PE module without a guard.

    This build configures no Vulkan driver, and DXMT talks to Metal directly.
    """

    source = wine_source / "dlls" / "win32u" / "vulkan.c"
    text = source.read_text(encoding="utf-8")
    if "#ifndef SONAME_LIBVULKAN" in text:
        return
    anchor = "static void vulkan_init_once(void)"
    fallback = '#ifndef SONAME_LIBVULKAN\n#define SONAME_LIBVULKAN "libvulkan.1.dylib"\n#endif\n\n'
    source.write_text(text.replace(anchor, fallback + anchor, 1), encoding="utf-8")


def build_wine(builder: Builder, source: Path, build: Path, staging: Path) -> Path:
    patch_vulkan_soname(builder, source)
    pkg_config, includes, libraries = nix_prefixes(builder)
    builder.environment.update(
        PKG_CONFIG_PATH=pkg_config,
        CFLAGS=(
            "-O2 -Wno-error=implicit-function-declaration "
            f"-Werror=unguarded-availability-new {includes}".strip()
        ),
        LDFLAGS=libraries,
        CC="ccache /usr/bin/clang -arch arm64",
        CXX="ccache /usr/bin/clang++ -arch arm64",
    )
    build.mkdir(parents=True, exist_ok=True)
    if not (build / "Makefile").exists():
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
        )
    builder.run("make", f"-j{logical_cpu_count()}", cwd=build)
    builder.run("make", "install", f"DESTDIR={staging}", cwd=build)
    return staging / "opt" / "whiskywine"


def build_fex(builder: Builder, source: Path, root: Path, unix_directory: Path) -> Path:
    builder.run("git", "submodule", "update", "--init", "--recursive", cwd=source)
    install = root / "fex-install"
    install.mkdir(parents=True, exist_ok=True)
    environment = builder.without_host_build_variables()
    for triple in ("arm64ec-w64-mingw32", "aarch64-w64-mingw32"):
        build = root / f"fex-{triple}"
        builder.run(
            "cmake",
            "-S",
            source,
            "-B",
            build,
            "-G",
            "Ninja",
            f"-DCMAKE_TOOLCHAIN_FILE={source / 'Data/CMake/toolchain_mingw.cmake'}",
            f"-DMINGW_TRIPLE={triple}",
            "-DCMAKE_BUILD_TYPE=Release",
            "-DENABLE_LTO=FALSE",
            "-DENABLE_CCACHE=FALSE",
            "-DBUILD_TESTING=FALSE",
            "-DBUILD_FEXCONFIG=FALSE",
            "-DENABLE_JEMALLOC_GLIBC_ALLOC=FALSE",
            "-DENABLE_OFFLINE_TELEMETRY=FALSE",
            "-DTUNE_ARCH=generic",
            "-DTUNE_CPU=none",
            "-DRANGES_NATIVE=OFF",
            f"-DCMAKE_INSTALL_PREFIX={install}",
            environment=environment,
        )
        builder.run("cmake", "--build", build, environment=environment)
        builder.run("cmake", "--install", build, environment=environment)
    for module in ("arm64ecfex", "wow64fex"):
        builder.run(
            "/usr/bin/clang++",
            "-std=c++20",
            "-O2",
            "-shared",
            "-fPIC",
            "-arch",
            "arm64",
            f"-mmacosx-version-min={builder.environment['MACOSX_DEPLOYMENT_TARGET']}",
            f"-I{source / 'Source/Windows/UnixLib'}",
            source / "Source/Windows/UnixLib/FEXUnixLib.cpp",
            "-o",
            unix_directory / f"lib{module}.so",
        )
    return install


def build_dxmt(builder: Builder, source: Path, root: Path, wine_build: Path) -> Path:
    builder.run("git", "submodule", "update", "--init", "--recursive", cwd=source)
    install = root / "dxmt-install"
    build = root / "dxmt-build"
    environment = builder.without_host_build_variables()
    if not (build / "build.ninja").exists():
        builder.run(
            "meson",
            "setup",
            build,
            source,
            "--cross-file",
            source / "build-arm64ec.txt",
            f"-Dnative_llvm_path={builder.environment['LLVM_ROOT']}",
            f"-Dwine_build_path={wine_build}",
            "--buildtype",
            "release",
            "--prefix",
            install,
            "--strip",
            environment=environment,
        )
    builder.run("meson", "compile", "-C", build, environment=environment)
    builder.run("meson", "install", "-C", build, environment=environment)
    return install


def assemble(
    builder: Builder,
    candidate: Path,
    wine_install: Path,
    fex_install: Path,
    dxmt_install: Path,
) -> None:
    wine = candidate / "Wine"
    wine.mkdir(parents=True, exist_ok=True)
    for name in ("bin", "lib", "share"):
        target = wine / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(wine_install / name, target, symlinks=True)
    loader = wine / "lib/wine/aarch64-unix/wine"
    if not loader.is_file():
        raise BuildError(f"the Wine install has no ARM64 loader: {loader}")
    for name in ("wine", "wine64", "wineloader"):
        link = wine / "bin" / name
        link.unlink(missing_ok=True)
        link.symlink_to("../lib/wine/aarch64-unix/wine")
    launcher = wine / "bin" / "Arknights"
    launcher.unlink(missing_ok=True)
    launcher.symlink_to("wine64")
    versioned = loader.with_suffix(".versioned")
    builder.run(
        "vtool",
        "-set-build-version",
        "macos",
        builder.environment["MACOSX_DEPLOYMENT_TARGET"],
        LOADER_SDK_VERSION,
        "-replace",
        "-o",
        versioned,
        loader,
    )
    versioned.replace(loader)
    loader.chmod(0o755)

    windows = wine / "lib/wine/aarch64-windows"
    unix = wine / "lib/wine/aarch64-unix"
    for module in ("libarm64ecfex.dll", "libwow64fex.dll", "winemetal.dll"):
        shutil.copy2(fex_install / "lib" / module, windows / module)
    shutil.copy2(dxmt_install / "aarch64-unix/winemetal.so", unix / "winemetal.so")
    payload = candidate / "DXMT" / "x64"
    payload.mkdir(parents=True, exist_ok=True)
    for library in ("d3d10core.dll", "d3d11.dll", "dxgi.dll"):
        destination = payload / library
        shutil.copy2(dxmt_install / "aarch64-windows" / library, destination)
        with destination.open("r+b") as file:
            file.seek(64)
            file.write(CLEARED_DOS_STUB)
    shutil.copy2(
        ROOT / "runtime-capabilities.json", candidate / "runtime-capabilities.json"
    )


def bundle_libraries(builder: Builder, candidate: Path) -> None:
    """Copy the library closure of the Wine unix modules and rewrite its paths."""

    directory = candidate / "Wine" / "lib"
    queue: list[Path] = []
    for package in WINE_NIX_PACKAGES:
        prefix = Path(builder.capture("brew", "--prefix", package).strip())
        for name in BUNDLED_LIBRARIES:
            if (prefix / "lib" / name).is_file():
                queue.append(prefix / "lib" / name)
    queue.extend(referenced_libraries(builder, directory / "wine/aarch64-unix/wine"))
    copied: set[str] = set()
    while queue:
        library = queue.pop(0)
        if library.name in copied:
            continue
        copied.add(library.name)
        destination = directory / library.name
        if library.parent != directory:
            shutil.copy2(library, destination)
            destination.chmod(0o644)
        queue.extend(referenced_libraries(builder, destination))
    for binary in sorted(directory.glob("*.dylib*")) + sorted(
        (directory / "wine" / "aarch64-unix").glob("*.so")
    ):
        rewrite_references(builder, directory, binary)


def rewrite_references(builder: Builder, directory: Path, binary: Path) -> None:
    relative = os.path.relpath(directory, binary.parent)
    builder.run("chmod", "u+w", binary)
    if ".dylib" in binary.name:
        builder.run("install_name_tool", "-id", f"@loader_path/{binary.name}", binary)
    for reference in referenced_libraries(builder, binary):
        builder.run(
            "install_name_tool",
            "-change",
            reference,
            f"@loader_path/{relative}/{reference.name}",
            binary,
        )
    builder.run("codesign", "--force", "--sign", "-", binary)


def build_arm64(builder: Builder, *, resume: bool, patched: bool) -> Path:
    """Build the native-arm64 canary from the pinned sources."""

    lock = load_lock(target=ARM64_TARGET)
    builder.require(
        "git", "cmake", "meson", "ninja", "clang", "brew", "codesign", "vtool"
    )
    arm64_environment(builder, lock)

    root = ARM64_STAGE_ROOT
    candidate = root / "candidate" / "Libraries"
    sources = root / "sources"
    if root.exists() and not resume:
        raise BuildError(f"build output already exists: {root} (pass --resume)")
    root.mkdir(parents=True, exist_ok=True)
    candidate.mkdir(parents=True, exist_ok=True)
    sources.mkdir(parents=True, exist_ok=True)

    stage = "combined" if patched else "base"
    wine_source = sources / f"wine-{ARM64_TARGET}-{stage}"
    dxmt_source = sources / f"dxmt-{ARM64_TARGET}-{stage}"
    fex_source = sources / f"fex-{ARM64_TARGET}-{stage}"
    if wine_source.is_dir() and dxmt_source.is_dir() and fex_source.is_dir():
        info("Using the sources from the previous run")
    else:
        # The fullscreen patch needs a rebase onto arm64-1117; report the skip.
        skips = ("wine-fullscreen-native-space",) if patched else ()
        prepare(
            stage, sources, target=ARM64_TARGET, all_sources=True, skip_patches=skips
        )

    builder.run(
        sys.executable,
        ROOT / "scripts" / "runtime.py",
        "validate-lock",
        "--target",
        ARM64_TARGET,
    )
    wine_build = root / "wine-build"
    wine_install = build_wine(builder, wine_source, wine_build, root / "wine-staging")
    fex_install = build_fex(
        builder, fex_source, root, wine_install / "lib" / "wine" / "aarch64-unix"
    )
    dxmt_install = build_dxmt(builder, dxmt_source, root, wine_build)
    assemble(builder, candidate, wine_install, fex_install, dxmt_install)
    bundle_libraries(builder, candidate)
    sign_directory(builder, candidate)
    builder.run(
        sys.executable,
        ROOT / "scripts" / "validate_runtime.py",
        candidate,
        "--target",
        ARM64_TARGET,
        "--require-capabilities",
        "--require-64-bit-only",
    )
    return write_archive(
        root, "Libraries", "Arknights-MacOS-Runtime-arm64-canary.tar.gz"
    )


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    arm64 = commands.add_parser("arm64", help="build the native-arm64 canary")
    arm64.add_argument("--resume", action="store_true")
    arm64.add_argument(
        "--no-patches", action="store_true", help="build the unpatched base sources"
    )
    parsed = parser.parse_args(arguments)
    builder = Builder()
    try:
        artifact = build_arm64(
            builder, resume=parsed.resume, patched=not parsed.no_patches
        )
    except (BuildError, LockError, OSError, subprocess.CalledProcessError) as failure:
        error(str(failure))
        return 1
    success(f"artifact: {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
