# SPDX-License-Identifier: MPL-2.0

import json
import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# Unset (or a missing value) enables the feature.
_UNSET_MEANS_ON = re.compile(
    r"STATUS_VARIABLE_NOT_FOUND\)\s*return TRUE"
    r"|!\w+\s*\|\|"
)
# Only the exact value "1" enables the feature.
_EXACTLY_ONE = re.compile(
    r"\w+\s*&&\s*\w+\[\d\]\s*==\s*'1'"
    r'|strcmp\s*\(\s*\w+\s*,\s*"1"\s*\)'
)

# Patch id -> id of the patch that owns its gate check.
GATE_RIDERS = {
    # 0008 has no gate code of its own; it relies on 0007's LMISXH_AKMOCL_CN check.
    "wine-cn-bilibili-join-all-spaces": "wine-cn-bilibili-layered-child",
}


def _wine_patches() -> list[dict]:
    lock = json.loads((REPOSITORY_ROOT / "runtime.lock.json").read_text("utf-8"))
    return [patch for patch in lock["patches"] if patch["component"] == "wine"]


def _patch_text(patch: dict) -> str:
    return (REPOSITORY_ROOT / patch["path"]).read_text(encoding="utf-8")


def test_every_wine_patch_checks_its_lock_gate() -> None:
    for patch in _wine_patches():
        text = _patch_text(patch)
        gate = patch["gate"]

        if gate not in text:
            owner_id = GATE_RIDERS.get(patch["id"])
            assert owner_id is not None, f"{patch['path']} does not check {gate}"
            owner = next(entry for entry in _wine_patches() if entry["id"] == owner_id)
            text = _patch_text(owner)

        if patch["default"]:
            assert _UNSET_MEANS_ON.search(text), (
                f"{patch['path']} does not treat an unset {gate} as enabled"
            )
        else:
            assert _EXACTLY_ONE.search(text), (
                f'{patch["path"]} does not require {gate} to be exactly "1"'
            )
