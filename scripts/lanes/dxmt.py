# SPDX-License-Identifier: MPL-2.0

"""Build DXMT with Meson for one PE target.

The lanes share this skeleton. A lane supplies its cross file and compilers through its
`Target`, plus its own Wine build tree. The Wine build tree provides the import libraries
that DXMT links against.
"""

import re
from collections.abc import Sequence
from pathlib import Path

from scripts.build_common import (
    Builder,
    BuildError,
    write_compiler_launcher_cross_file,
    write_dxmt_native_file,
)
from scripts.lanes import Target

DXMT_BUILD_DIRECTORY = "dxmt-build"
DXMT_INSTALL_DIRECTORY = "dxmt-install"

AIR_TRIPLE = re.compile(r'target triple = "air64_v\d+-apple-macosx([\d.]+)"')


def meson_setup_command(
    build: Path,
    source: Path,
    cross_files: Sequence[Path],
    native_file: Path,
    llvm: Path,
    wine_build: Path,
    install: Path,
    *,
    reconfigure: bool = False,
) -> list[str]:
    """Return the Meson setup command. A later cross file overrides an earlier one."""

    command = ["meson", "setup"]
    if reconfigure:
        command.append("--reconfigure")
    command += [str(build), str(source)]
    for cross_file in cross_files:
        command += ["--cross-file", str(cross_file)]
    command += [
        "--native-file",
        str(native_file),
        f"-Dnative_llvm_path={llvm}",
        f"-Dwine_build_path={wine_build}",
        "--buildtype",
        "release",
        "--prefix",
        str(install),
        "--strip",
    ]
    return command


def version_tuple(version: str) -> tuple[int, int]:
    major, minor, *_ = (*(int(part) for part in version.split(".")), 0)
    return major, minor


def reject_metal_above(disassembly: str, deployment: str, name: str) -> None:
    """Reject a Metal library whose AIR targets a newer macOS than the lane supports.

    The Metal compiler defaults to the SDK. An SDK 27 default produces Metal 4.1 AIR,
    which macOS 26 and earlier cannot load.
    """

    triples = AIR_TRIPLE.findall(disassembly)
    if not triples:
        raise BuildError(f"{name} has no AIR target triple")
    limit = version_tuple(deployment)
    for triple in triples:
        if version_tuple(triple) > limit:
            raise BuildError(
                f"{name} targets macOS {triple}, above the deployment target {deployment}"
            )


def verify_metal_libraries(builder: Builder, build: Path, deployment: str) -> None:
    """Disassemble every Metal library of the build and check its target."""

    libraries = sorted(build.rglob("*.metallib"))
    if not libraries:
        raise BuildError(f"the DXMT build has no Metal library under {build}")
    for library in libraries:
        disassembly = builder.capture(
            "xcrun", "-sdk", "macosx", "metal-objdump", "--disassemble", library
        )
        reject_metal_above(disassembly, deployment, library.name)


def build_dxmt(
    builder: Builder,
    *,
    target: Target,
    source: Path,
    root: Path,
    wine_build: Path,
    llvm: Path,
    deployment: str,
) -> Path:
    """Build and install DXMT under `root`. Return the install tree."""

    cross_file = source / target.dxmt_cross_file
    if not cross_file.is_file():
        raise BuildError(f"the DXMT source has no {target.dxmt_cross_file}")
    build = root / DXMT_BUILD_DIRECTORY
    install = root / DXMT_INSTALL_DIRECTORY
    native_file = write_dxmt_native_file(root, deployment)
    cross_files = [cross_file]
    launcher_file = write_compiler_launcher_cross_file(
        root, target.dxmt_compilers(), builder.environment
    )
    if launcher_file is not None:
        cross_files.append(launcher_file)
    environment = builder.without_host_build_variables()
    # The Metal compiler reads this variable to pick its AIR target and language version.
    environment["MACOSX_DEPLOYMENT_TARGET"] = deployment
    command = meson_setup_command(
        build,
        source,
        cross_files,
        native_file,
        llvm,
        wine_build,
        install,
        reconfigure=(build / "build.ninja").is_file(),
    )
    builder.run(*command, environment=environment)
    builder.run("meson", "compile", "-C", build, environment=environment)
    builder.run("meson", "install", "-C", build, environment=environment)
    verify_metal_libraries(builder, build, deployment)
    return install
