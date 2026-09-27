# SPDX-License-Identifier: MPL-2.0

from dataclasses import dataclass, replace
from pathlib import Path

WS_CHILD = 0x40000000
WS_POPUP = 0x80000000


@dataclass(frozen=True)
class Window:
    class_name: str
    style: int
    pid: int
    parent: str | None = None
    owner: str | None = None


def payment_candidate(
    windows: dict[str, Window], hwnd: str, *, current_pid: int, cn_enabled: bool = True
) -> bool:
    """Offline reference classifier for the observed Bilibili HWND parent tree."""
    child = windows[hwnd]
    if (
        not cn_enabled
        or child.class_name != "Chrome_WidgetWin_0"
        or not child.style & WS_CHILD
        or child.style & WS_POPUP
        or not child.parent
    ):
        return False

    parent = windows[child.parent]
    if parent.class_name != "CefBrowserWindow":
        return False

    root_id = child.parent
    while windows[root_id].style & WS_CHILD:
        root_id = windows[root_id].parent or ""
        if not root_id or root_id not in windows:
            return False
    root = windows[root_id]
    return (
        not root.style & WS_CHILD
        and root.class_name.startswith("CPayDlg_P_")
        and bool(root.class_name.removeprefix("CPayDlg_P_"))
        and child.pid == parent.pid == root.pid == current_pid
    )


def driver_accepts_payment_candidate(
    windows: dict[str, Window],
    hwnd: str,
    *,
    current_pid: int,
    translucent_property: bool,
) -> bool:
    return translucent_property and payment_candidate(
        windows, hwnd, current_pid=current_pid
    )


def observed_payment_tree() -> dict[str, Window]:
    return {
        "root": Window("CPayDlg_P_7f32", WS_POPUP, 41),
        "browser": Window("CefBrowserWindow", WS_CHILD, 41, parent="root"),
        "renderer": Window(
            "Chrome_WidgetWin_0", WS_CHILD, 41, parent="browser", owner="root"
        ),
    }


def test_payment_classifier_accepts_observed_parent_tree() -> None:
    tree = observed_payment_tree()

    assert payment_candidate(tree, "renderer", current_pid=41)
    assert driver_accepts_payment_candidate(
        tree, "renderer", current_pid=41, translucent_property=True
    )


def test_payment_classifier_rejects_wrong_parent_root_style_and_process() -> None:
    tree = observed_payment_tree()
    cases = {
        "wrong immediate parent": {
            **tree,
            "browser": replace(tree["browser"], class_name="OtherBrowserWindow"),
        },
        "wrong root": {**tree, "root": replace(tree["root"], class_name="CPayDlg_")},
        "empty root suffix": {
            **tree,
            "root": replace(tree["root"], class_name="CPayDlg_P_"),
        },
        "child root": {
            **tree,
            "root": replace(tree["root"], style=WS_CHILD),
        },
        "wrong renderer class": {
            **tree,
            "renderer": replace(tree["renderer"], class_name="Chrome_WidgetWin_1"),
        },
        "child popup": {
            **tree,
            "renderer": replace(tree["renderer"], style=WS_CHILD | WS_POPUP),
        },
        "non-child renderer": {
            **tree,
            "renderer": replace(tree["renderer"], style=0),
        },
        "renderer PID mismatch": {
            **tree,
            "renderer": replace(tree["renderer"], pid=42),
        },
        "parent PID mismatch": {
            **tree,
            "browser": replace(tree["browser"], pid=42),
        },
        "root PID mismatch": {**tree, "root": replace(tree["root"], pid=42)},
        "wrong current process": tree,
    }
    current_pids = {"wrong current process": 42}

    for name, candidate_tree in cases.items():
        assert not payment_candidate(
            candidate_tree, "renderer", current_pid=current_pids.get(name, 41)
        ), name


def test_payment_classifier_does_not_follow_owner_links() -> None:
    tree = observed_payment_tree()
    tree["renderer"] = replace(tree["renderer"], parent=None, owner="root")

    assert not payment_candidate(tree, "renderer", current_pid=41)


def test_driver_keeps_translucent_property_requirement() -> None:
    tree = observed_payment_tree()

    assert not driver_accepts_payment_candidate(
        tree, "renderer", current_pid=41, translucent_property=False
    )


def test_wine_patch_keeps_login_route_and_bounds_payment_route() -> None:
    root = Path(__file__).resolve().parents[1]
    patch = (
        root
        / "patches"
        / "wine"
        / "cn"
        / "windowing"
        / "0001-win32u-winemac-bilibili-layered-child.patch"
    ).read_text(encoding="utf-8")

    for contract in (
        "is_bilibili_payment_proxy_candidate",
        "static const WCHAR browserW[] = {'C','e','f','B','r','o','w','s','e','r','W','i','n','d','o','w',0};",
        "style & WS_CHILD",
        "style & WS_POPUP",
        "GA_ROOT",
        "static const WCHAR payment_rootW[] = {'C','P','a','y','D','l','g','_','P','_',0};",
        "root_length <= ARRAY_SIZE(payment_rootW) - 1",
        "NtUserGetWindowLongW( root, GWL_STYLE ) & WS_CHILD",
        "NtUserGetWindowThread",
        "parent_pid == current_pid && root_pid == parent_pid",
        "hwnd_pid == parent_pid && hwnd_pid == root_pid",
        "is_bilibili_layered_proxy_candidate( class_name, parent, cs.style )",
        "return has_bilibili_webview_ancestor( parent ) || is_bilibili_payment_proxy_candidate( parent, style );",
        "has_bilibili_webview_ancestor( parent ) || is_bilibili_payment_proxy_window( hwnd, parent )",
        "NtUserGetProp(hwnd, translucentW)",
        "NtUserSetProp( hwnd, translucentW, ULongToHandle( 1 ) )",
        "if (pts_dst && is_bilibili_layered_proxy_window( hwnd )) pts_dst = NULL;",
    ):
        assert contract in patch, contract

    assert "GA_ROOTOWNER" not in patch
    assert "GW_OWNER" not in patch
