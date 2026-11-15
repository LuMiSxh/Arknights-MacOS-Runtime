# SPDX-License-Identifier: MPL-2.0

"""The x86_64 lane: WineCX built from source, DXMT, and Nix libraries for Rosetta 2."""

import os
import shutil
import sys
from pathlib import Path

from scripts.build_common import (
    MACHO_SUFFIXES,
    NIX_PACKAGES,
    NIX_STORE,
    ROOT,
    VALIDATE_CLI,
    WINE_CONFIGURE_FLAGS,
    WINE_PREFIX,
    Builder,
    BuildError,
    adhoc_sign,
    bundle_nix_libraries,
    clear_dos_stub,
    clone_tree,
    compiler_launcher,
    ensure_loader_rpath,
    extract_archive,
    library_flags,
    logical_cpu_count,
    nix_build,
    nix_package_outputs,
    references_in,
)
from scripts.release.licenses import generate
from scripts.runtime import BUILD_ROOT, fetch_base, load_lock, prepare
from scripts.targets import ROSETTA_X86_64_TARGET, Target, inventory_name
from scripts.targets.dxmt import build_dxmt
from scripts.targets.package import package_runtime

TARGET = Target(
    name=ROSETTA_X86_64_TARGET,
    arch="x86_64",
    wine_source="built",
    dxmt_cross_file="build-win64.txt",
    pe_compiler="x86_64-w64-mingw32",
)

# Every Wine file that a patch in runtime.lock.json changes.
WINE_OVERLAY_ARTIFACTS = (
    "lib/wine/x86_64-unix/winecoreaudio.so",
    "lib/wine/x86_64-windows/ntdll.dll",
    "lib/wine/x86_64-unix/winemac.so",
    "lib/wine/x86_64-unix/ntdll.so",
    "lib/wine/x86_64-windows/kernel32.dll",
    "lib/wine/x86_64-windows/kernelbase.dll",
    "lib/wine/x86_64-windows/ntoskrnl.exe",
    "lib/wine/x86_64-windows/ws2_32.dll",
    "lib/wine/x86_64-windows/userenv.dll",
    "lib/wine/x86_64-unix/win32u.so",
)

# Repository paths that the corresponding-source archive carries besides the sources.
SOURCE_REPOSITORY_MEMBERS = (
    "patches",
    "runtime.lock.json",
    "docs/patch-registry.md",
    "docs/legal",
    "LICENSE",
    "LICENSES",
    "scripts",
    "Justfile",
    "pyproject.toml",
    "uv.lock",
)


def patched_machos() -> tuple[str, ...]:
    return tuple(
        artifact
        for artifact in WINE_OVERLAY_ARTIFACTS
        if artifact.endswith(MACHO_SUFFIXES)
    )


def build_environment(
    builder: Builder, lock: dict[str, object]
) -> tuple[str, list[Path]]:
    nixpkgs_revision = str(lock["build"]["nixpkgs"]["commit"])
    nixpkgs = f"github:NixOS/nixpkgs/{nixpkgs_revision}"
    builder.environment["MACOSX_DEPLOYMENT_TARGET"] = str(lock["deploymentTarget"])

    tool_paths: list[Path] = []
    for attribute in ("bison", "flex", "pkg-config"):
        tool_paths.append(nix_build(builder, f"{nixpkgs}#{attribute}"))

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


def wine_configure_command(wine_source: Path, environment: dict[str, str]) -> list[str]:
    """Return the Wine configure command.

    With a compiler launcher set, the PE compiles of Wine go through it too. Wine reads
    the `x86_64_CC` variable for its PE cross compiler.
    """

    command = [
        str(wine_source / "configure"),
        "--host=x86_64-apple-darwin24",
        "--enable-archs=x86_64",
        "--disable-tests",
        *WINE_CONFIGURE_FLAGS,
        f"--prefix={WINE_PREFIX}",
    ]
    launcher = compiler_launcher(environment)
    if launcher:
        compiler = f"{TARGET.pe_compiler}-gcc"
        command.append("x86_64_CC=" + " ".join((*launcher, compiler)))
    return command


def configure_wine(builder: Builder, wine_source: Path, wine_build: Path) -> None:
    wine_build.mkdir(parents=True, exist_ok=True)
    builder.run(
        *wine_configure_command(wine_source, builder.environment), cwd=wine_build
    )
    builder.run("make", f"-j{logical_cpu_count()}", cwd=wine_build)


def overlay_wine_files(builder: Builder, candidate: Path, wine_install: Path) -> None:
    for artifact in WINE_OVERLAY_ARTIFACTS:
        source = wine_install / artifact
        if not source.is_file():
            raise BuildError(f"patched Wine output is missing: {artifact}")
        shutil.copy2(source, candidate / "Wine" / artifact)
    for artifact in WINE_OVERLAY_ARTIFACTS:
        if not artifact.endswith((".dll", ".exe")):
            continue
        path = candidate / "Wine" / artifact
        if path.is_file():
            builder.run("x86_64-w64-mingw32-strip", "--strip-debug", path)


def fix_patched_machos(builder: Builder, candidate: Path) -> None:
    for artifact in patched_machos():
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
        ensure_loader_rpath(builder, binary)
        adhoc_sign(builder, binary)


def build_dxmt_x86_64(
    builder: Builder,
    deployment: str,
    source: Path,
    root: Path,
    wine_build: Path,
    llvm: Path,
    candidate: Path,
) -> None:
    builder.run("git", "submodule", "update", "--init", "--recursive", cwd=source)
    install = build_dxmt(
        builder,
        target=TARGET,
        source=source,
        root=root,
        wine_build=wine_build,
        llvm=llvm,
        deployment=deployment,
    )
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
    adhoc_sign(builder, candidate / "Wine/lib/wine/x86_64-unix/winemetal.so")
    for library in ("d3d10core.dll", "d3d11.dll", "dxgi.dll"):
        clear_dos_stub(candidate / "DXMT/x64" / library)


def write_inventory(path: Path, libraries: list[str], nixpkgs_revision: str) -> None:
    """Write the component inventory: the shipped components and the Nix libraries."""

    rows = [
        "component\trole\tsource",
        "WineCX/Wine\tWindows compatibility runtime\truntime.lock.json:sources.wine",
        "DXMT\tDirect3D-to-Metal payload\truntime.lock.json:sources.dxmt",
        (
            "MoltenVK\tVulkan-to-Metal library\truntime.lock.json:baseArtifact "
            "(SHA-256-pinned third-party base archive; not built from source)"
        ),
    ]
    rows.extend(
        f"{Path(output).name}\tBundled Nix library\t{output} (nixpkgs {nixpkgs_revision})"
        for output in libraries
    )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def prepare_base(root: Path, *, clean_release: bool) -> Path:
    """Fetch the pinned base and lay out the candidate tree."""

    base_archive = fetch_base()
    (root / "base").mkdir(parents=True)
    (root / "candidate").mkdir(parents=True)
    extract_archive(base_archive, root / "base")
    candidate = root / "candidate" / "Libraries"
    if clean_release:
        candidate.mkdir(parents=True)
    else:
        clone_tree(root / "base" / "Libraries", candidate)
        launcher = candidate / "Wine" / "bin" / "Arknights"
        if not launcher.exists() and not launcher.is_symlink():
            launcher.symlink_to("wine64")
    return candidate


def configure_runtime(
    builder: Builder,
    lock: dict[str, object],
    root: Path,
    source_root: Path,
) -> tuple[str, list[Path], Path]:
    """Prepare the patched sources and build Wine."""

    nixpkgs, outputs = build_environment(builder, lock)
    prepare(source_root)
    wine_build = root / "wine-build"
    configure_wine(builder, source_root / "wine", wine_build)
    return nixpkgs, outputs, wine_build


def install_clean_wine(root: Path, candidate: Path, wine_install: Path) -> None:
    """Copy the clean Wine install and point every launcher at the loader."""

    (candidate / "Wine").mkdir(parents=True, exist_ok=True)
    for name in ("bin", "lib", "share"):
        shutil.copytree(wine_install / name, candidate / "Wine" / name, symlinks=True)
    loader = candidate / "Wine/lib/wine/x86_64-unix/wine"
    if not os.access(loader, os.X_OK):
        raise BuildError(f"clean Wine install has no loader: {loader}")
    for name in ("wine", "wine64", "wineloader"):
        link = candidate / "Wine/bin" / name
        link.unlink(missing_ok=True)
        link.symlink_to("../lib/wine/x86_64-unix/wine")
    launcher = candidate / "Wine/bin" / "Arknights"
    launcher.unlink(missing_ok=True)
    launcher.symlink_to("wine64")
    base_library = root / "base/Libraries/Wine/lib/libMoltenVK.dylib"
    if not base_library.is_file():
        raise BuildError(
            "pinned base is missing required payload: Wine/lib/libMoltenVK.dylib"
        )
    shutil.copy2(base_library, candidate / "Wine/lib/libMoltenVK.dylib")


def install_runtime(
    builder: Builder,
    root: Path,
    candidate: Path,
    wine_build: Path,
    *,
    clean_release: bool,
) -> None:
    """Install the built Wine tree and apply the patched files."""

    staging = root / "wine-staging"
    builder.run(
        "make",
        "-C",
        wine_build,
        f"-j{logical_cpu_count()}",
        "install-lib",
        f"DESTDIR={staging}",
    )
    wine_install = staging / WINE_PREFIX.lstrip("/")
    if clean_release:
        install_clean_wine(root, candidate, wine_install)
    overlay_wine_files(builder, candidate, wine_install)
    fix_patched_machos(builder, candidate)


def source_entries(source_root: Path, inventory: Path) -> list[tuple[Path, str]]:
    """Return the corresponding-source members of the x86_64 lane."""

    return [
        (source_root / "wine", "wine"),
        (source_root / "dxmt", "dxmt"),
        (inventory, "runtime-component-inventory.tsv"),
        *((ROOT / name, name) for name in SOURCE_REPOSITORY_MEMBERS),
    ]


def build_runtime(
    builder: Builder,
    *,
    release: bool,
    version: str,
    output: Path,
    source_commit: str,
) -> Path:
    """Build the x86_64 runtime and return the path of its provenance fragment.

    A release build is clean and gated. A candidate overlays the patched Wine files on the
    pinned base.
    """

    lock = load_lock(target=TARGET.name)
    root = BUILD_ROOT / TARGET.arch
    if root.exists():
        raise BuildError(f"build output already exists: {root}")
    builder.require("git", "tar", "uv")

    candidate = prepare_base(root, clean_release=release)

    builder.require(
        "nix", "clang", "make", "meson", "ninja", f"{TARGET.pe_compiler}-gcc"
    )
    source_root = root / "sources"
    nixpkgs, outputs, wine_build = configure_runtime(builder, lock, root, source_root)
    install_runtime(builder, root, candidate, wine_build, clean_release=release)
    libraries = bundle_nix_libraries(builder, candidate, outputs) if release else []
    llvm = llvm_native_tree(builder, nixpkgs, root)
    (candidate / "DXMT/x64").mkdir(parents=True, exist_ok=True)
    build_dxmt_x86_64(
        builder,
        str(lock["deploymentTarget"]),
        source_root / "dxmt",
        root,
        wine_build,
        llvm,
        candidate,
    )
    if (
        release
        and builder.capture("git", "-C", str(ROOT), "status", "--porcelain").strip()
    ):
        raise BuildError("build modified tracked repository files")

    output.mkdir(parents=True, exist_ok=True)
    inventory = output / inventory_name(TARGET.arch)
    write_inventory(inventory, libraries, str(lock["build"]["nixpkgs"]["commit"]))
    validation_report = root / "validation.json"
    if release:
        builder.run(
            sys.executable,
            VALIDATE_CLI,
            candidate,
            "--target",
            TARGET.name,
            "--require-64-bit-only",
            "--report",
            validation_report,
        )
        generate(ROOT, candidate.parent, inventory=inventory, target=TARGET.name)
        members = ("Libraries", "Licenses", "NOTICE.md")
    else:
        builder.run(
            sys.executable,
            VALIDATE_CLI,
            candidate,
            "--target",
            TARGET.name,
            "--baseline",
            root / "base" / "Libraries",
            "--report",
            validation_report,
        )
        members = ("Libraries",)
    return package_runtime(
        repository_root=ROOT,
        target=TARGET,
        version=version,
        release=release,
        output=output,
        content_root=candidate.parent,
        members=members,
        source_entries=source_entries(source_root, inventory),
        source_root=source_root,
        inventory=inventory,
        validation_report=validation_report,
        wine={
            "repository": lock["sources"]["wine"]["repository"],
            "commit": lock["sources"]["wine"]["commit"],
            "version": lock["sources"]["wine"]["version"],
        },
        dxmt={
            "repository": lock["sources"]["dxmt"]["repository"],
            "commit": lock["sources"]["dxmt"]["commit"],
            "version": lock["sources"]["dxmt"]["version"],
        },
        source_commit=source_commit,
    )
