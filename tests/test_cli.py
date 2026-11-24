# SPDX-License-Identifier: MPL-2.0

import importlib

import pytest

from scripts.__main__ import COMMANDS, main, resolve


def _targets() -> list[str]:
    return [
        target
        for entry in COMMANDS.values()
        for target in (entry.values() if isinstance(entry, dict) else [entry])
    ]


@pytest.mark.parametrize("target", _targets())
def test_every_registered_command_resolves_to_a_callable(target):
    module, function = target.split(":")
    if module == "scripts.release.deltas":
        pytest.importorskip("bsdiff4")
    assert callable(getattr(importlib.import_module(module), function))


def test_resolve_splits_the_group_from_the_command_arguments():
    assert resolve(["release", "combine", "--version", "1"]) == (
        "scripts.release.combine:main",
        ["--version", "1"],
    )
    assert resolve(["pins", "update", "--dry-run"]) == (
        "scripts.pins.cli:main",
        ["update", "--dry-run"],
    )
    assert resolve(["release"]) is None
    assert resolve(["nope"]) is None


def test_unknown_command_exits_with_a_usage_error(capsys):
    assert main(["nope"]) == 2
    assert "usage:" in capsys.readouterr().err


def test_pins_update_requires_the_arm64_lane_for_a_named_release():
    with pytest.raises(SystemExit) as failure:
        main(["pins", "update", "--release", "wine-11-18-arm64-v4"])

    assert failure.value.code == 2
