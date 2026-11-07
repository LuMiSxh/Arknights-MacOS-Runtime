# SPDX-License-Identifier: MPL-2.0

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WINSOCK_PATCH = (
    REPOSITORY_ROOT
    / "patches"
    / "wine"
    / "winsock"
    / "0001-ws2_32-implement-address-list-sort.patch"
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


def test_winsock_patch_stays_ungated() -> None:
    text = _winsock_patch_text()

    assert "lmisxh_akmocl_winsock_enabled" not in text
