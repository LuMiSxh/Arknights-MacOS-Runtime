# SPDX-License-Identifier: MPL-2.0

import json
import re
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WINSOCK_PATCH = (
    REPOSITORY_ROOT / "patches" / "wine" / "0005-ws2_32-address-list-sort.patch"
)


def _winsock_patch_text() -> str:
    return WINSOCK_PATCH.read_text(encoding="utf-8")


def test_winsock_patch_validates_the_count_before_arithmetic() -> None:
    text = _winsock_patch_text()

    assert "Address[in->iAddressCount]" not in text
    assert "header_size = FIELD_OFFSET(SOCKET_ADDRESS_LIST, Address[0])" in text
    assert "(in_size - header_size) / sizeof(in->Address[0])" in text


def test_winsock_patch_validates_every_address_in_the_in_place_path() -> None:
    text = _winsock_patch_text()

    assert "const SOCKET_ADDRESS *address = &in->Address[i];" in text
    assert "address->iSockaddrLength <= 0" in text
    assert "out == in" in text


def test_winsock_patch_completes_overlapped_calls() -> None:
    text = _winsock_patch_text()

    assert "struct afd_complete_async_params" in text
    assert "IOCTL_AFD_WINE_COMPLETE_ASYNC" in text
    assert "server_ioctl_sock( s, IOCTL_AFD_WINE_COMPLETE_ASYNC, &complete" in text
    assert "file_complete_async" in text


def test_winsock_patch_is_gated_by_its_own_flag() -> None:
    text = _winsock_patch_text()

    assert "lmisxh_akmocl_winsock_enabled" in text
    assert "LMISXH_AKMOCL_WINSOCK" in text


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


def _lock() -> dict:
    lock_path = REPOSITORY_ROOT / "runtime.lock.json"
    return json.loads(lock_path.read_text(encoding="utf-8"))


def _wine_patches() -> list[dict]:
    return [patch for patch in _lock()["patches"] if patch["component"] == "wine"]


def _patch_text(patch: dict) -> str:
    return (REPOSITORY_ROOT / patch["path"]).read_text(encoding="utf-8")


@pytest.mark.parametrize("patch", _wine_patches(), ids=lambda patch: patch["id"])
def test_every_wine_patch_checks_its_lock_gate(patch: dict) -> None:
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
