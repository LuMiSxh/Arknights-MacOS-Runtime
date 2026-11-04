#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""The native-arm64 lane: WineCX, FEX, and DXMT for an unentitled process."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

if __package__:
    from ..shared.build import (
        ARCHIVE_BUNDLED_LIBRARIES,
        CLEARED_DOS_STUB,
        LOADER_SDK_VERSION,
        ROOT,
        RUNTIME_CLI,
        VALIDATE_CLI,
        Builder,
        BuildError,
        logical_cpu_count,
        references_in,
        rewrite_references,
        sign_directory,
        write_archive,
    )
    from ..shared.lib.console import info
    from ..shared.runtime import BUILD_ROOT, load_lock, prepare
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.shared.build import (
        ARCHIVE_BUNDLED_LIBRARIES,
        CLEARED_DOS_STUB,
        LOADER_SDK_VERSION,
        ROOT,
        RUNTIME_CLI,
        VALIDATE_CLI,
        Builder,
        BuildError,
        logical_cpu_count,
        references_in,
        rewrite_references,
        sign_directory,
        write_archive,
    )
    from scripts.shared.lib.console import info
    from scripts.shared.runtime import BUILD_ROOT, load_lock, prepare


ARM64_TARGET = "native-arm64"


ARM64_STAGE_ROOT = BUILD_ROOT / "stages" / "arm64"


ARM64_NIX_PACKAGES = ("freetype", "gnutls", "vulkan-headers")


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


def brew_prefixes(builder: Builder) -> tuple[str, str, str]:
    pkg_config: list[str] = []
    includes: list[str] = []
    libraries: list[str] = []
    for package in ARM64_NIX_PACKAGES:
        prefix = Path(builder.capture("brew", "--prefix", package).strip())
        if (prefix / "lib" / "pkgconfig").is_dir():
            pkg_config.append(str(prefix / "lib" / "pkgconfig"))
        if (prefix / "include").is_dir():
            includes.append(f"-I{prefix / 'include'}")
        if (prefix / "lib").is_dir():
            libraries.append(f"-L{prefix / 'lib'}")
    return ":".join(pkg_config), " ".join(includes), " ".join(libraries)


def patch_vulkan_soname(wine_source: Path) -> None:
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


def patch_fex_arm64ec_flags(source: Path) -> None:
    """Give the arm64ec frontend the flags llvm-mingw needs for hybrid code.

    A global CMAKE_CXX_FLAGS would also hit FEX's host tools, so the guard keeps
    the flags on the mingw side. ARM64EC is an x64-compatible ABI, so the header
    guard that hides RtlIsEcCode in winnt.h needs __x86_64__.
    """

    path = source / "CMakeLists.txt"
    text = path.read_text(encoding="utf-8")
    marker = "# ARKNIGHTS_RUNTIME_ARM64EC_FLAGS"
    if marker in text:
        start = text.index(marker)
        end = text.index("endif()\n", start) + len("endif()\n")
        text = text[:start] + text[end:]
    shim = (
        f"{marker}\n"
        'if (MINGW AND MINGW_TRIPLE MATCHES "^arm64ec")\n'
        "  add_compile_options(-marm64x)\n"
        "  add_compile_options(-include${CMAKE_BINARY_DIR}/arknights-arm64ec-compat.h)\n"
        "  add_link_options(-marm64x)\n"
        "endif()\n"
    )
    anchor = "project(FEX C CXX ASM)\n"
    path.write_text(text.replace(anchor, anchor + shim, 1), encoding="utf-8")


def write_arm64ec_compat_header(build: Path) -> None:
    """Declare RtlIsEcCode, which winnt.h hides behind __x86_64__.

    Defining __x86_64__ instead would pull the whole x86 intrinsic surface into
    an ARM64EC compile, which does not build.
    """

    build.mkdir(parents=True, exist_ok=True)
    header = """#pragma once
#ifdef __cplusplus
extern "C" {
#endif
__declspec(dllimport) unsigned char __stdcall RtlIsEcCode(unsigned long long);
#ifdef __cplusplus
}
#endif
"""
    (build / "arknights-arm64ec-compat.h").write_text(header, encoding="utf-8")


def build_fex_arm64(
    builder: Builder, source: Path, root: Path, unix_directory: Path
) -> Path:
    builder.run("git", "submodule", "update", "--init", "--recursive", cwd=source)
    patch_fex_arm64ec_flags(source)
    install = root / "fex-install"
    install.mkdir(parents=True, exist_ok=True)
    environment = builder.without_host_build_variables()
    for triple in ("arm64ec-w64-mingw32", "aarch64-w64-mingw32"):
        build = root / f"fex-{triple}"
        if triple.startswith("arm64ec"):
            write_arm64ec_compat_header(build)
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
            "-DFMT_MODULE=OFF",
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


def build_wine_arm64(
    builder: Builder, source: Path, build: Path, staging: Path
) -> Path:
    patch_vulkan_soname(source)
    pkg_config, includes, libraries = brew_prefixes(builder)
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


def build_dxmt_arm64(
    builder: Builder, source: Path, root: Path, wine_build: Path
) -> Path:
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


def assemble_arm64(
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
    for module in ("libarm64ecfex.dll", "libwow64fex.dll"):
        shutil.copy2(fex_install / "lib" / module, windows / module)
    shutil.copy2(
        dxmt_install / "aarch64-windows/winemetal.dll", windows / "winemetal.dll"
    )
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


def bundle_arm64_libraries(builder: Builder, candidate: Path) -> None:
    """Copy the library closure of the Wine unix modules and rewrite its paths."""

    directory = candidate / "Wine" / "lib"
    queue: list[Path] = []
    for package in ARM64_NIX_PACKAGES:
        prefix = Path(builder.capture("brew", "--prefix", package).strip())
        for name in ARCHIVE_BUNDLED_LIBRARIES:
            if (prefix / "lib" / name).is_file():
                queue.append(prefix / "lib" / name)
    queue.extend(
        Path(reference)
        for reference in references_in(
            builder, directory / "wine/aarch64-unix/wine", "/opt/homebrew/"
        )
    )
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
        queue.extend(
            Path(reference)
            for reference in references_in(builder, destination, "/opt/homebrew/")
        )
    for binary in sorted(directory.glob("*.dylib*")) + sorted(
        (directory / "wine" / "aarch64-unix").glob("*.so")
    ):
        rewrite_references(builder, directory, binary)


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

    builder.run(sys.executable, RUNTIME_CLI, "validate-lock", "--target", ARM64_TARGET)
    wine_build = root / "wine-build"
    wine_install = build_wine_arm64(
        builder, wine_source, wine_build, root / "wine-staging"
    )
    fex_install = build_fex_arm64(
        builder, fex_source, root, wine_install / "lib" / "wine" / "aarch64-unix"
    )
    dxmt_install = build_dxmt_arm64(builder, dxmt_source, root, wine_build)
    assemble_arm64(builder, candidate, wine_install, fex_install, dxmt_install)
    bundle_arm64_libraries(builder, candidate)
    sign_directory(builder, candidate)
    builder.run(
        sys.executable,
        VALIDATE_CLI,
        candidate,
        "--target",
        ARM64_TARGET,
        "--require-capabilities",
        "--require-64-bit-only",
    )
    return write_archive(
        root, "Arknights-MacOS-Runtime-arm64-canary.tar.gz", ("Libraries",)
    )
