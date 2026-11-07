# SPDX-License-Identifier: MPL-2.0

import struct

import pytest

from scripts.arm64.build_dxmt import (
    LC_BUILD_VERSION,
    LC_VERSION_MIN_MACOSX,
    deployment_target,
    macho_minimum_macos,
    meson_setup_command,
    parse_version,
    reject_macho_above,
    stage_winemac_so,
    verify_dxmt_install,
)
from scripts.build_common import BuildError


def _macho(command: int, version: tuple[int, int]) -> bytes:
    packed = (version[0] << 16) | (version[1] << 8)
    if command == LC_BUILD_VERSION:
        body = struct.pack("<IIIIII", command, 24, 1, packed, 0, 0)
    else:
        body = struct.pack("<IIII", command, 16, packed, 0)
    header = struct.pack("<IiiIIIII", 0xFEEDFACF, 0x0100000C, 0, 2, 1, len(body), 0, 0)
    return header + body


def _install_with_macho(root, version: tuple[int, int]):
    install = root / "dxmt"
    unix = install / "aarch64-unix"
    unix.mkdir(parents=True)
    (unix / "winemetal.so").write_bytes(_macho(LC_BUILD_VERSION, version))
    return install


def test_macho_minimum_macos_reads_the_build_version(tmp_path):
    path = tmp_path / "winemetal.so"
    path.write_bytes(_macho(LC_BUILD_VERSION, (26, 0)))

    assert macho_minimum_macos(path) == (26, 0)


def test_macho_minimum_macos_reads_the_legacy_version_command(tmp_path):
    path = tmp_path / "winemetal.so"
    path.write_bytes(_macho(LC_VERSION_MIN_MACOSX, (26, 1)))

    assert macho_minimum_macos(path) == (26, 1)


def test_reject_macho_above_accepts_the_floor(tmp_path):
    install = _install_with_macho(tmp_path, (26, 0))

    reject_macho_above(install, (26, 0))


def test_reject_macho_above_rejects_macos_27(tmp_path):
    install = _install_with_macho(tmp_path, (27, 2))

    with pytest.raises(BuildError, match="27.2"):
        reject_macho_above(install, (26, 0))


def test_verify_dxmt_install_requires_every_payload(tmp_path):
    install = tmp_path / "dxmt"
    names = (
        "aarch64-unix/winemetal.so",
        "aarch64-windows/d3d10core.dll",
        "aarch64-windows/d3d11.dll",
        "aarch64-windows/dxgi.dll",
        "aarch64-windows/winemetal.dll",
    )
    for name in names:
        path = install / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"payload")

    verify_dxmt_install(install)

    (install / names[-1]).unlink()
    with pytest.raises(BuildError, match="winemetal.dll"):
        verify_dxmt_install(install)


def test_stage_winemac_so_links_the_external_unixlib(tmp_path):
    wine_install = tmp_path / "incoming" / "wine"
    unix = wine_install / "lib" / "wine" / "aarch64-unix"
    unix.mkdir(parents=True)
    (unix / "winemac.so").write_bytes(b"winemac payload")
    build = tmp_path / "wine-build"

    stage_winemac_so(build, wine_install)

    destination = build / "dlls" / "winemac.drv" / "winemac.so"
    assert destination.is_symlink()
    assert destination.resolve() == (unix / "winemac.so").resolve()


def test_stage_winemac_so_requires_the_external_tree(tmp_path):
    with pytest.raises(BuildError, match="winemac.so"):
        stage_winemac_so(tmp_path / "wine-build", tmp_path / "incoming" / "wine")


def test_meson_setup_uses_the_wine_build_tree_not_an_install_tree(tmp_path):
    command = meson_setup_command(
        tmp_path / "dxmt-build",
        tmp_path / "dxmt-source",
        tmp_path / "dxmt-native.ini",
        tmp_path / "llvm",
        tmp_path / "wine-build",
        tmp_path / "dxmt",
    )

    assert "--cross-file" in command
    assert f"-Dwine_build_path={tmp_path / 'wine-build'}" in command
    assert not any(argument.startswith("-Dwine_install_path") for argument in command)
    assert "--strip" in command
    assert command[command.index("--buildtype") + 1] == "release"


def test_meson_setup_reconfigures_an_existing_build(tmp_path):
    command = meson_setup_command(
        tmp_path / "dxmt-build",
        tmp_path / "dxmt-source",
        tmp_path / "dxmt-native.ini",
        tmp_path / "llvm",
        tmp_path / "wine-build",
        tmp_path / "dxmt",
        reconfigure=True,
    )

    assert command[1:3] == ["setup", "--reconfigure"]


def test_deployment_target_requires_the_lock_value():
    lock = {"deploymentTarget": "26.0"}

    assert deployment_target(lock, {}) == "26.0"
    assert deployment_target(lock, {"MACOSX_DEPLOYMENT_TARGET": "26.0"}) == "26.0"
    with pytest.raises(BuildError, match="26.0"):
        deployment_target(lock, {"MACOSX_DEPLOYMENT_TARGET": "15.0"})


def test_parse_version_reads_the_major_and_minor():
    assert parse_version("26.0") == (26, 0)
    assert parse_version("26") == (26, 0)
