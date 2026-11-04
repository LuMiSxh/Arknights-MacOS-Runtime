#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Build a runtime artifact from the pinned lock.

The recipe is docs/architecture.md for the x86_64 lanes and docs/arm/pipeline.md
for the ARM64 lane. This module never runs Wine, creates a prefix, or starts a game.
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
    from .runtime import (
        BUILD_ROOT,
        LockError,
        fetch_base,
        load_lock,
        prepare,
    )
else:
    from lib.console import error, info, success
    from runtime import BUILD_ROOT, LockError, fetch_base, load_lock, prepare

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_CLI = ROOT / "scripts" / "runtime.py"
VALIDATE_CLI = ROOT / "scripts" / "validate_runtime.py"
LICENSE_CLI = ROOT / "scripts" / "release" / "licenses.py"
TOOLCHAIN_CLI = ROOT / "scripts" / "release" / "toolchain.py"

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
# Packages the x86_64 lane links against, one Nix output each.
CANARY_NIX_PACKAGES = (
    "freetype",
    "gnutls",
    "libpng",
    "zlib",
    "brotli",
    "bzip2",
    "nettle",
    "libtasn1",
    "libidn2",
    "p11-kit",
    "libunistring",
    "gmp",
    "vulkan-headers",
)
ARM64_TARGET = "native-arm64"
ARM64_STAGE_ROOT = BUILD_ROOT / "stages" / "arm64"
ARM64_NIX_PACKAGES = ("freetype", "gnutls", "vulkan-headers")
ARCHIVE_BUNDLED_LIBRARIES = ("libfreetype.6.dylib", "libgnutls.30.dylib")
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
NIX_STORE = "/nix/store/"


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

    def capture(
        self,
        *command: object,
        cwd: Path | None = None,
        environment: dict[str, str] | None = None,
        allow_failure: bool = False,
    ) -> str:
        result = subprocess.run(
            [str(part) for part in command],
            cwd=cwd,
            env=environment if environment is not None else self.environment,
            capture_output=True,
            check=False,
            text=True,
        )
        if result.returncode != 0 and not allow_failure:
            raise BuildError(
                f"command failed: {' '.join(str(part) for part in command)}"
            )
        return result.stdout

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


def write_archive(directory: Path, tar_name: str, members: tuple[str, ...]) -> Path:
    """Create the tar.gz and its shasum-compatible checksum file."""

    path = directory / tar_name
    with tarfile.open(path, "w:gz") as tar:
        for member in members:
            tar.add(directory / member, arcname=member)
    (directory / f"{tar_name}.sha256").write_text(
        f"{sha256(path)}  {tar_name}\n", encoding="utf-8"
    )
    return path


def extract_archive(source: Path, destination: Path) -> None:
    with tarfile.open(source) as tar:
        tar.extractall(destination, filter="tar")


def clone_tree(source: Path, destination: Path) -> None:
    """Copy a tree with APFS clones when the host supports them."""

    result = subprocess.run(
        ["cp", "-cR", str(source), str(destination)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        shutil.copytree(source, destination, symlinks=True)


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


def references_in(builder: Builder, binary: Path, prefix: str) -> list[str]:
    references: list[str] = []
    for line in builder.capture("otool", "-L", binary).splitlines()[1:]:
        reference = line.strip().split(" (", 1)[0]
        if reference.startswith(prefix):
            references.append(reference)
    return references


def rewrite_references(builder: Builder, directory: Path, binary: Path) -> None:
    relative = os.path.relpath(directory, binary.parent)
    if ".dylib" in binary.name:
        builder.run(
            "install_name_tool",
            "-id",
            f"@loader_path/{binary.name}",
            binary,
        )
    for reference in references_in(builder, binary, "/opt/homebrew/"):
        builder.run(
            "install_name_tool",
            "-change",
            reference,
            f"@loader_path/{relative}/{Path(reference).name}",
            binary,
        )
    builder.run("codesign", "--force", "--sign", "-", binary)


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


# --- x86_64 lanes ----------------------------------------------------------------


def validate_stage(stage: str) -> None:
    if stage not in STAGES:
        raise BuildError(STAGE_HINT)


def nix_build(builder: Builder, attribute: str) -> Path | None:
    output = builder.capture(
        "nix", "build", "--no-link", "--print-out-paths", attribute, allow_failure=True
    ).strip()
    return Path(output) if output else None


def nix_package_outputs(
    builder: Builder, nixpkgs: str, packages: tuple[str, ...]
) -> list[Path]:
    outputs: list[Path] = []
    for package in packages:
        for output_name in ("dev", "out", "lib"):
            output = nix_build(
                builder,
                f"{nixpkgs}#legacyPackages.x86_64-darwin.{package}.{output_name}",
            )
            if output is not None:
                outputs.append(output)
    return outputs


def canary_environment(
    builder: Builder, lock: dict[str, object], root: Path, stage: str
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
        outputs = nix_package_outputs(builder, nixpkgs, CANARY_NIX_PACKAGES)

    pkg_config: list[str] = []
    includes: list[str] = []
    libraries: list[str] = []
    for output in outputs:
        if (output / "lib" / "pkgconfig").is_dir():
            pkg_config.append(str(output / "lib" / "pkgconfig"))
        if (output / "include").is_dir():
            includes.append(f"-I{output / 'include'}")
        if (output / "lib").is_dir():
            libraries.append(f"-L{output / 'lib'}")

    builder.environment.update(
        PATH=":".join(
            [str(path / "bin") for path in tool_paths]
            + [builder.environment.get("PATH", "")]
        ),
        SDKROOT=builder.capture("xcrun", "--show-sdk-path").strip(),
        CC="ccache /usr/bin/clang -arch x86_64",
        CXX="ccache /usr/bin/clang++ -arch x86_64",
        PKG_CONFIG_PATH=":".join(pkg_config),
        CFLAGS=(
            "-O2 -Wno-error=implicit-function-declaration "
            f"-Werror=unguarded-availability-new {' '.join(includes)}"
        ).strip(),
        CROSSCFLAGS="-O2",
        LDFLAGS=" ".join(libraries),
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
        if path.is_file() and artifact.endswith((".dll", ".exe")):
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


def bundle_release_libraries(
    builder: Builder, candidate: Path, root: Path, outputs: list[Path]
) -> list[str]:
    directory = candidate / "Wine" / "lib"
    inventory: list[str] = []
    queue: list[Path] = []
    for output in outputs:
        for name in ARCHIVE_BUNDLED_LIBRARIES:
            if (output / "lib" / name).is_file():
                queue.append(output / "lib" / name)
    for module in sorted((directory / "wine").glob("*-unix/*.so")):
        queue.extend(
            Path(reference) for reference in references_in(builder, module, NIX_STORE)
        )

    while queue:
        reference = queue.pop(0)
        name = reference.name
        if (directory / name).exists():
            continue
        shutil.copy2(reference, directory / name)
        destination = directory / name
        destination.chmod(0o644)
        if reference.as_posix().startswith(NIX_STORE):
            inventory.append(
                NIX_STORE + reference.as_posix().split(NIX_STORE, 1)[1].split("/", 1)[0]
            )
        queue.extend(
            Path(next_reference)
            for next_reference in references_in(builder, destination, NIX_STORE)
        )

    for binary in sorted(directory.glob("*.dylib*")) + sorted(
        (directory / "wine").glob("*-unix/*.so")
    ):
        fix_release_macho(builder, directory, binary)
    link = directory / "libfreetype.dylib"
    link.unlink(missing_ok=True)
    link.symlink_to("libfreetype.6.dylib")
    for binary in sorted((directory / "wine").glob("*-unix/*.so")):
        result = subprocess.run(
            ["otool", "-l", str(binary)], capture_output=True, text=True, check=False
        )
        if "@loader_path/../../" not in result.stdout:
            builder.run(
                "install_name_tool", "-add_rpath", "@loader_path/../../", binary
            )
        builder.run("codesign", "--force", "--sign", "-", binary)
    return sorted(set(inventory))


def fix_release_macho(builder: Builder, directory: Path, binary: Path) -> None:
    relative = os.path.relpath(directory, binary.parent)
    binary.chmod(binary.stat().st_mode | 0o200)
    if ".dylib" in binary.name:
        builder.run("install_name_tool", "-id", f"@loader_path/{binary.name}", binary)
    for reference in references_in(builder, binary, NIX_STORE):
        name = Path(reference).name
        if name.startswith("libiconv") and "_iconv" in builder.capture(
            "nm", "-u", binary, allow_failure=True
        ):
            builder.run(
                "install_name_tool",
                "-change",
                reference,
                "/usr/lib/libiconv.2.dylib",
                binary,
            )
        else:
            builder.run(
                "install_name_tool",
                "-change",
                reference,
                f"@loader_path/{relative}/{name}",
                binary,
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
    builder.run(
        "meson",
        "setup",
        "--cross-file",
        source / "build-win64.txt",
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
    capability_manifest = str(lock["interface"]["runtimeCapabilities"])
    if clean_release:
        candidate.mkdir(parents=True)
        shutil.copy2(ROOT / capability_manifest, candidate / capability_manifest)
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
        return write_archive(root, f"Arknights-MacOS-Runtime-{stage}.tar.gz", members)

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
        inventory = bundle_release_libraries(builder, candidate, outputs)

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
            "--require-capabilities",
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
    return write_archive(root, f"Arknights-MacOS-Runtime-{stage}.tar.gz", members)


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


def build_fex_arm64(
    builder: Builder, source: Path, root: Path, unix_directory: Path
) -> Path:
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


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    canary = commands.add_parser("canary", help="build one patch family overlay")
    canary.add_argument("stage", nargs="?", default="combined")
    canary.add_argument("--clean-release", action="store_true")
    commands.add_parser("release", help="build the clean release artifact")
    arm64 = commands.add_parser("arm64", help="build the native-arm64 canary")
    arm64.add_argument("--resume", action="store_true")
    arm64.add_argument(
        "--no-patches", action="store_true", help="build the unpatched base sources"
    )
    parsed = parser.parse_args(arguments)
    builder = Builder()
    try:
        if parsed.command == "canary":
            artifact = build_canary(
                builder, parsed.stage, clean_release=parsed.clean_release
            )
        elif parsed.command == "release":
            artifact = build_canary(builder, "combined", clean_release=True)
        else:
            artifact = build_arm64(
                builder, resume=parsed.resume, patched=not parsed.no_patches
            )
    except BuildError as failure:
        print(f"error: {failure}", file=sys.stderr)
        return 2 if str(failure) == STAGE_HINT else 1
    except (LockError, OSError, subprocess.CalledProcessError) as failure:
        error(str(failure))
        return 1
    success(f"artifact: {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
