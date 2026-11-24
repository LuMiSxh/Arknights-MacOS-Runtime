# SPDX-License-Identifier: MPL-2.0

import struct

import pytest

from scripts.build_common import BuildError
from scripts.lanes.arm64_dxmt import (
    LC_BUILD_VERSION,
    MINIMAL_WINE_TARGETS,
    reject_macho_above,
    stage_winemac_so,
    verify_dxmt_install,
    verify_minimal_wine_outputs,
)
from scripts.lanes.dxmt import reject_metal_above


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


def test_verify_minimal_wine_outputs_requires_every_target(tmp_path):
    for relative in MINIMAL_WINE_TARGETS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"payload")

    verify_minimal_wine_outputs(tmp_path)

    (tmp_path / MINIMAL_WINE_TARGETS[-1]).unlink()
    with pytest.raises(BuildError, match="ntdll.so"):
        verify_minimal_wine_outputs(tmp_path)


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


def test_reject_metal_above_rejects_an_sdk_default_target():
    ok = 'target triple = "air64_v27-apple-macosx15.0.0"\n'
    reject_metal_above(ok, "15.0", "x.metallib")
    with pytest.raises(BuildError, match="27.2.0"):
        reject_metal_above(
            ok + 'target triple = "air64_v29-apple-macosx27.2.0"\n',
            "15.0",
            "x.metallib",
        )
