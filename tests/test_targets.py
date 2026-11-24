# SPDX-License-Identifier: MPL-2.0

from pathlib import Path

from scripts.lanes.x86_64 import wine_configure_command

WINE_SOURCE = Path("/src/wine")


def test_wine_configure_adds_the_pe_compiler_launcher_when_ccache_is_set():
    command = wine_configure_command(WINE_SOURCE, {"LMISXH_AKMOCL_CCACHE": "ccache"})

    assert "x86_64_CC=ccache x86_64-w64-mingw32-gcc" in command
