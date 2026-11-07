#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""The x86_64 lanes: one patch-family overlay, and the clean release artifact."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

if __package__:
    from .build_common import (
        CLEARED_DOS_STUB,
        LICENSE_CLI,
        NIX_PACKAGES,
        NIX_STORE,
        TOOLCHAIN_CLI,
        VALIDATE_CLI,
        Builder,
        BuildError,
        bundle_nix_libraries,
        clone_tree,
        extract_archive,
        library_flags,
        logical_cpu_count,
        nix_build,
        nix_package_outputs,
        references_in,
        write_archive,
        write_dxmt_native_file,
    )
    from .runtime import BUILD_ROOT, fetch_base, load_lock, prepare
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.build_common import (
        CLEARED_DOS_STUB,
        LICENSE_CLI,
        NIX_PACKAGES,
        NIX_STORE,
        TOOLCHAIN_CLI,
        VALIDATE_CLI,
        Builder,
        BuildError,
        bundle_nix_libraries,
        clone_tree,
        extract_archive,
        library_flags,
        logical_cpu_count,
        nix_build,
        nix_package_outputs,
        references_in,
        write_archive,
        write_dxmt_native_file,
    )
    from scripts.runtime import BUILD_ROOT, fetch_base, load_lock, prepare


STAGES = (
    "base",
    "audio",
    "hardware-cursor",
    "performance",
    "ace",
    "cef",
    "cn",
    "combined",
)


STAGE_HINT = (
    "expected base, audio, hardware-cursor, performance, ace, cef, cn, or combined"
)


class StageError(BuildError):
    """The stage name is not part of the patch recipe."""


def wine_overlay_artifacts(stage: str) -> tuple[str, ...]:
    """The Wine files a stage copies over the base archive."""

    if stage == "hardware-cursor":
        return ("lib/wine/x86_64-unix/ntdll.so",)
    artifacts: list[str] = []
    if stage in ("audio", "combined"):
        artifacts.append("lib/wine/x86_64-unix/winecoreaudio.so")
    if stage in ("ace", "cef", "combined"):
        artifacts.append("lib/wine/x86_64-windows/ntdll.dll")
    if stage in ("ace", "combined"):
        artifacts.extend(
            (
                "lib/wine/x86_64-unix/winemac.so",
                "lib/wine/x86_64-unix/ntdll.so",
                "lib/wine/x86_64-windows/kernel32.dll",
                "lib/wine/x86_64-windows/ntoskrnl.exe",
            )
        )
    if stage in ("cn", "combined"):
        artifacts.append("lib/wine/x86_64-unix/win32u.so")
        if stage == "cn":
            artifacts.append("lib/wine/x86_64-unix/winemac.so")
    return tuple(artifacts)


def patched_machos(stage: str) -> tuple[str, ...]:
    return tuple(
        artifact
        for artifact in wine_overlay_artifacts(stage)
        if artifact.endswith((".so", ".dylib"))
    )


def validate_stage(stage: str) -> None:
    if stage not in STAGES:
        raise StageError(STAGE_HINT)


def canary_environment(
    builder: Builder, lock: dict[str, object], stage: str
) -> tuple[str, list[Path]]:
    nixpkgs_revision = str(lock["build"]["nixpkgs"]["commit"])
    nixpkgs = f"github:NixOS/nixpkgs/{nixpkgs_revision}"
    builder.environment["MACOSX_DEPLOYMENT_TARGET"] = str(lock["deploymentTarget"])

    tool_paths: list[Path] = []
    for attribute in ("bison", "flex", "pkg-config"):
        output = nix_build(builder, f"{nixpkgs}#{attribute}")
        if output is None:
            raise BuildError(f"nix build failed for {attribute}")
        tool_paths.append(output)

    outputs: list[Path] = []
    if stage != "hardware-cursor":
        outputs = nix_package_outputs(builder, nixpkgs, "x86_64-darwin", NIX_PACKAGES)

    pkg_config, includes, libraries = library_flags(outputs)

    builder.environment.update(
        PATH=":".join(
            [str(path / "bin") for path in tool_paths]
            + [builder.environment.get("PATH", "")]
        ),
        SDKROOT=builder.capture("xcrun", "--show-sdk-path").strip(),
        CC="ccache /usr/bin/clang -arch x86_64",
        CXX="ccache /usr/bin/clang++ -arch x86_64",
        PKG_CONFIG_PATH=pkg_config,
        CFLAGS=(
            "-O2 -Wno-error=implicit-function-declaration "
            f"-Werror=unguarded-availability-new {includes}"
        ).strip(),
        CROSSCFLAGS="-O2",
        LDFLAGS=libraries,
        ac_cv_func_pipe2="no",
        ac_cv_lib_soname_freetype="libfreetype.6.dylib",
        ac_cv_lib_soname_gnutls="libgnutls.30.dylib",
        ac_cv_lib_soname_MoltenVK="libMoltenVK.dylib",
    )
    return nixpkgs, outputs


def llvm_native_tree(builder: Builder, nixpkgs: str, root: Path) -> Path:
    attribute = f"{nixpkgs}#legacyPackages.x86_64-darwin.llvmPackages_15.llvm"
    development = nix_build(builder, f"{attribute}.dev")
    library = nix_build(builder, f"{attribute}.lib")
    if development is None or library is None:
        raise BuildError("nix build failed for LLVM 15")
    for directory in (development / "include", library / "lib"):
        if not directory.is_dir():
            raise BuildError(f"LLVM output has no expected directory: {directory}")
    tree = root / "llvm-native"
    tree.mkdir(parents=True, exist_ok=True)
    for name, source in (
        ("include", development / "include"),
        ("lib", library / "lib"),
    ):
        link = tree / name
        link.unlink(missing_ok=True)
        link.symlink_to(source)
    return tree


def configure_wine(
    builder: Builder,
    wine_source: Path,
    wine_build: Path,
    configure_flags: tuple[str, ...],
    *,
    only_ntdll: bool,
) -> None:
    wine_build.mkdir(parents=True, exist_ok=True)
    builder.run(
        wine_source / "configure",
        "--host=x86_64-apple-darwin24",
        "--enable-archs=x86_64",
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
        *configure_flags,
        cwd=wine_build,
    )
    targets = ("dlls/ntdll/ntdll.so",) if only_ntdll else ()
    builder.run("make", f"-j{logical_cpu_count()}", *targets, cwd=wine_build)


def overlay_wine_files(
    builder: Builder, candidate: Path, wine_install: Path, stage: str
) -> None:
    for artifact in wine_overlay_artifacts(stage):
        source = wine_install / artifact
        if not source.is_file():
            raise BuildError(f"patched Wine output is missing: {artifact}")
        shutil.copy2(source, candidate / "Wine" / artifact)
    for artifact in (
        "lib/wine/x86_64-windows/ntdll.dll",
        "lib/wine/x86_64-windows/kernel32.dll",
        "lib/wine/x86_64-windows/ntoskrnl.exe",
    ):
        path = candidate / "Wine" / artifact
        if path.is_file():
            builder.run("x86_64-w64-mingw32-strip", "--strip-debug", path)


def fix_patched_machos(builder: Builder, candidate: Path, stage: str) -> None:
    for artifact in patched_machos(stage):
        binary = candidate / "Wine" / artifact
        for reference in references_in(builder, binary, NIX_STORE):
            dependency = candidate / "Wine" / "lib" / Path(reference).name
            if not dependency.is_file():
                raise BuildError(
                    f"patched Wine binary needs an unbundled dependency: {reference}"
                )
            builder.run(
                "install_name_tool",
                "-change",
                reference,
                f"@rpath/{Path(reference).name}",
                binary,
            )
        rpaths = builder.capture("otool", "-l", binary)
        if "@loader_path/../../" not in rpaths:
            builder.run(
                "install_name_tool", "-add_rpath", "@loader_path/../../", binary
            )
        builder.run("codesign", "--force", "--sign", "-", binary)


def build_dxmt_x86_64(
    builder: Builder,
    source: Path,
    root: Path,
    wine_build: Path,
    llvm: Path,
    candidate: Path,
) -> None:
    builder.run("git", "submodule", "update", "--init", "--recursive", cwd=source)
    install = root / "dxmt-install"
    build = root / "dxmt-build64"
    environment = builder.without_host_build_variables()
    native_file = write_dxmt_native_file(
        root, builder.environment["MACOSX_DEPLOYMENT_TARGET"]
    )
    builder.run(
        "meson",
        "setup",
        "--cross-file",
        source / "build-win64.txt",
        "--native-file",
        native_file,
        f"-Dnative_llvm_path={llvm}",
        f"-Dwine_build_path={wine_build}",
        "--buildtype",
        "release",
        "--prefix",
        install,
        "--strip",
        build,
        source,
        environment=environment,
    )
    builder.run("meson", "compile", "-C", build, environment=environment)
    builder.run("meson", "install", "-C", build, environment=environment)
    for library in ("d3d10core.dll", "d3d11.dll", "dxgi.dll", "winemetal.dll"):
        shutil.copy2(
            install / "x86_64-windows" / library, candidate / "DXMT/x64" / library
        )
    shutil.copy2(
        install / "x86_64-windows/winemetal.dll",
        candidate / "Wine/lib/wine/x86_64-windows/winemetal.dll",
    )
    shutil.copy2(
        install / "x86_64-unix/winemetal.so",
        candidate / "Wine/lib/wine/x86_64-unix/winemetal.so",
    )
    builder.run(
        "codesign",
        "--force",
        "--sign",
        "-",
        candidate / "Wine/lib/wine/x86_64-unix/winemetal.so",
    )
    for library in ("d3d10core.dll", "d3d11.dll", "dxgi.dll"):
        destination = candidate / "DXMT/x64" / library
        with destination.open("r+b") as file:
            file.seek(64)
            file.write(CLEARED_DOS_STUB)


def write_release_metadata(
    builder: Builder,
    root: Path,
    candidate: Path,
    inventory: list[str],
    nixpkgs_revision: str,
) -> None:
    inventory_path = root / "runtime-component-inventory.tsv"
    rows = [
        "component\trole\tsource",
        "WineCX/Wine\tWindows compatibility runtime\truntime.lock.json:sources.wine",
        "DXMT\tDirect3D-to-Metal payload\truntime.lock.json:sources.dxmt",
        (
            "MoltenVK\tVulkan-to-Metal library\truntime.lock.json:baseArtifact "
            "(SHA-256-pinned third-party base archive; not built from source)"
        ),
    ]
    for output in inventory:
        rows.append(
            f"{Path(output).name}\tBundled Nix library\t{output} (nixpkgs {nixpkgs_revision})"
        )
    inventory_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    builder.run(sys.executable, TOOLCHAIN_CLI, root / "build-toolchain.json")
    builder.run(
        sys.executable,
        LICENSE_CLI,
        "generate",
        "--inventory",
        inventory_path,
        "--output",
        root / "candidate",
    )


def build_canary(builder: Builder, stage: str, *, clean_release: bool = False) -> Path:
    """Build one canary stage, or the clean release artifact."""

    validate_stage(stage)
    if clean_release and stage != "combined":
        raise BuildError("a clean release build must use the combined stage")
    lock = load_lock()
    root = BUILD_ROOT / "stages" / stage
    if root.exists():
        raise BuildError(f"stage output already exists: {root}")
    builder.require("git", "tar", "uv")

    base_archive = fetch_base()
    (root / "base").mkdir(parents=True)
    (root / "candidate").mkdir(parents=True)
    extract_archive(base_archive, root / "base")
    candidate = root / "candidate" / "Libraries"
    if clean_release:
        candidate.mkdir(parents=True)
    else:
        clone_tree(root / "base" / "Libraries", candidate)
    members = ("Libraries",)

    launcher = candidate / "Wine" / "bin" / "Arknights"
    if not clean_release and not launcher.exists() and not launcher.is_symlink():
        launcher.symlink_to("wine64")

    if stage == "base":
        builder.run(
            sys.executable,
            VALIDATE_CLI,
            candidate,
            "--baseline",
            root / "base" / "Libraries",
        )
        return write_archive(
            root,
            f"Arknights-MacOS-Runtime-{stage}.tar.gz",
            members,
            content_root=candidate.parent,
        )

    builder.require("nix", "clang", "make", "x86_64-w64-mingw32-gcc")
    nixpkgs, outputs = canary_environment(builder, lock, stage)
    nixpkgs_revision = str(lock["build"]["nixpkgs"]["commit"])

    source_root = root / "sources"
    prepare(stage, source_root)
    source_stage = "base" if stage == "performance" else stage
    if stage == "performance":
        prepare("base", source_root)
    wine_source = source_root / f"wine-{source_stage}"
    wine_build = root / "wine-build"

    configure_flags = (
        "--without-ffmpeg",
        "--without-gstreamer",
        "--prefix=/opt/whiskywine",
    )
    configure_wine(
        builder,
        wine_source,
        wine_build,
        configure_flags,
        only_ntdll=stage == "hardware-cursor",
    )

    if stage == "hardware-cursor":
        directory = candidate / "Wine/lib/wine/x86_64-unix"
        directory.mkdir(parents=True, exist_ok=True)
        shutil.copy2(wine_build / "dlls/ntdll/ntdll.so", directory / "ntdll.so")
    else:
        staging = root / "wine-staging"
        builder.run(
            "make",
            "-C",
            wine_build,
            f"-j{logical_cpu_count()}",
            "install-lib",
            f"DESTDIR={staging}",
        )
        wine_install = staging / "opt" / "whiskywine"
        if clean_release:
            (candidate / "Wine").mkdir(parents=True, exist_ok=True)
            for name in ("bin", "lib", "share"):
                shutil.copytree(
                    wine_install / name, candidate / "Wine" / name, symlinks=True
                )
            loader = candidate / "Wine/lib/wine/x86_64-unix/wine"
            if not os.access(loader, os.X_OK):
                raise BuildError(f"clean Wine install has no loader: {loader}")
            for name in ("wine", "wine64", "wineloader"):
                link = candidate / "Wine/bin" / name
                link.unlink(missing_ok=True)
                link.symlink_to("../lib/wine/x86_64-unix/wine")
            launcher.unlink(missing_ok=True)
            launcher.symlink_to("wine64")
            base_library = root / "base/Libraries/Wine/lib/libMoltenVK.dylib"
            if not base_library.is_file():
                raise BuildError(
                    "pinned base is missing required payload: Wine/lib/libMoltenVK.dylib"
                )
            shutil.copy2(base_library, candidate / "Wine/lib/libMoltenVK.dylib")
        overlay_wine_files(builder, candidate, wine_install, stage)
        fix_patched_machos(builder, candidate, stage)

    inventory: list[str] = []
    if clean_release:
        inventory = bundle_nix_libraries(builder, candidate, outputs)

    if stage in ("performance", "combined"):
        llvm = llvm_native_tree(builder, nixpkgs, root)
        (candidate / "DXMT/x64").mkdir(parents=True, exist_ok=True)
        build_dxmt_x86_64(
            builder,
            source_root / f"dxmt-{stage}",
            root,
            wine_build,
            llvm,
            candidate,
        )

    if clean_release:
        builder.run(
            sys.executable,
            VALIDATE_CLI,
            candidate,
            "--require-64-bit-only",
        )
        write_release_metadata(builder, root, candidate, inventory, nixpkgs_revision)
        members = ("Libraries", "Licenses", "NOTICE.md")
    else:
        builder.run(
            sys.executable,
            VALIDATE_CLI,
            candidate,
            "--baseline",
            root / "base" / "Libraries",
        )
    return write_archive(
        root,
        f"Arknights-MacOS-Runtime-{stage}.tar.gz",
        members,
        content_root=candidate.parent,
    )
