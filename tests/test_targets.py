# SPDX-License-Identifier: MPL-2.0

from pathlib import Path

import pytest

from scripts import build
from scripts.targets import arm64, x86_64
from scripts.targets.x86_64 import wine_configure_command

WINE_SOURCE = Path("/src/wine")


def test_wine_configure_adds_the_pe_compiler_launcher_when_ccache_is_set():
    command = wine_configure_command(WINE_SOURCE, {"LMISXH_AKMOCL_CCACHE": "ccache"})

    assert "x86_64_CC=ccache x86_64-w64-mingw32-gcc" in command


def test_wine_configure_uses_the_plain_compiler_without_a_launcher():
    command = wine_configure_command(WINE_SOURCE, {})

    assert not any(argument.startswith("x86_64_CC=") for argument in command)
    assert command[0] == str(WINE_SOURCE / "configure")


@pytest.mark.parametrize("module", [x86_64, arm64])
def test_each_lane_declares_its_target_name(module):
    assert module.TARGET.name in build.LANES


def test_candidate_dispatches_to_the_selected_lane(monkeypatch, tmp_path):
    calls = []

    def fake_build_runtime(builder, **keyword_arguments):
        calls.append(keyword_arguments)
        return tmp_path / "provenance.json"

    monkeypatch.setitem(build.LANES, x86_64.TARGET.name, x86_64)
    monkeypatch.setattr(x86_64, "build_runtime", fake_build_runtime)

    status = build.main(
        [
            "candidate",
            "--target",
            x86_64.TARGET.name,
            "--version",
            "0.9.0",
            "--output",
            str(tmp_path / "out"),
        ]
    )

    assert status == 0
    assert calls[0]["release"] is False
    assert calls[0]["version"] == "0.9.0"
    assert calls[0]["output"] == (tmp_path / "out").resolve()


def test_build_rejects_a_version_with_a_leading_v(tmp_path):
    status = build.main(
        [
            "release",
            "--target",
            x86_64.TARGET.name,
            "--version",
            "v0.9.0",
            "--output",
            str(tmp_path / "out"),
        ]
    )

    assert status == 1
