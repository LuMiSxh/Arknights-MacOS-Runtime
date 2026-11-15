# SPDX-License-Identifier: MPL-2.0

"""Build DXMT with Meson for one PE target.

The lanes share this skeleton. A lane supplies its cross file and compilers through its
`Target`, plus its own Wine build tree. The Wine build tree provides the import libraries
that DXMT links against.
"""

from collections.abc import Sequence
from pathlib import Path

from scripts.build_common import (
    Builder,
    BuildError,
    write_compiler_launcher_cross_file,
    write_dxmt_native_file,
)
from scripts.targets import Target

DXMT_BUILD_DIRECTORY = "dxmt-build"
DXMT_INSTALL_DIRECTORY = "dxmt-install"


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
    return install
