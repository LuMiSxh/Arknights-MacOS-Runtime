# SPDX-License-Identifier: MPL-2.0

"""Patch registry helpers and the wine-build-new export.

The registry holds one entry per patch, and each entry names the lanes that carry it.
`export_wine_build_new` derives `wine-build-new/lock.json` from the registry. The external
workspace parses that file, so its bytes are a contract: change the text here only with
that workspace.
"""

import json
from typing import Any

from scripts.lock.model import Lock, Patch, PatchFile, WineBuildNewExport

PORTFILE = "overlay/emulators/wine-arm64ec/Portfile"
FEX_APPLICATION = (
    "Apply after the wine-build-new FEX patch queue and deploy with Wine patch 0001."
)
OPT_OUT_SEMANTICS = "Unset or `1` keeps the patch on; any other value turns it off."
MODIFIERS = {
    "LMISXH_AKMOCL_CN": "Enable the Bilibili window behavior.",
    "LMISXH_AKMOCL_CURSOR": "Hide the two game software-cursor assets.",
}
OPT_OUTS = {
    "LMISXH_AKMOCL_EFLAGS": "Carry PF, AF and DF across ARM64EC context switches with the paired FEX patch.",
    "LMISXH_AKMOCL_HYBRID_THREAD": "Start a hybrid-module thread on its x64 export.",
    "LMISXH_AKMOCL_ACE_IMPORTS": "Export the three ACE kernel imports.",
    "LMISXH_AKMOCL_APPCONTAINER": "Implement the AppContainer names Chromium resolves.",
    "LMISXH_AKMOCL_WINSOCK": "Implement SIO_ADDRESS_LIST_SORT.",
    "LMISXH_AKMOCL_CEF": "Apply the Bilibili CEF 80.1.15 descriptor.",
    "LMISXH_AKMOCL_MENU": "Make Command+Q quit from the app menu.",
    "LMISXH_AKMOCL_LOADER_LINK": "Name the loader link and the application menu after the program (0016 and 0017).",
    "LMISXH_AKMOCL_SQUIRCLE_ICON": "Draw the Dock icon as a rounded square on the macOS icon grid.",
}
EXCLUDED = [
    {
        "patch": "fex/lookup-cache-commit",
        "reason": "patches/fex/local/0009 already commits the L1 lookup window and rewrites the same constructor; the standalone patch does not apply.",
    },
    {
        "patch": "mono/skip",
        "reason": "The workspace ships no Wine Mono, the cross-architecture entitlement removes the low-4GB constraint, and WINEDLLOVERRIDES=mscoree=d covers a fresh prefix.",
    },
]


def lane_patches(lock: Lock, lane: str) -> tuple[Patch, ...]:
    """Return the patches that name a file for `lane`, in registry order."""

    return tuple(patch for patch in lock.patches if lane in patch.files)


def _file_entry(file: PatchFile) -> dict[str, str]:
    return {"path": file.path, "sha256": file.sha256}


def _wine_entry(export: WineBuildNewExport, patch: Patch, order: int) -> dict[str, Any]:
    """Return one Wine entry. The key order is part of the export format."""

    entry: dict[str, Any] = {"order": order, **_file_entry(patch.files[export.lane])}
    if patch.gate is not None and not patch.default:
        entry["modifier"] = patch.gate
    entry["default"] = "on" if patch.default else "off"
    if patch.id in export.optional_patches:
        entry["optional"] = True
    if patch.gate is not None and patch.default:
        entry["opt_out"] = patch.gate
    return entry


def export_wine_build_new(lock: Lock) -> str:
    """Return the text of `wine-build-new/lock.json`."""

    export = lock.export
    lane = lock.lanes[export.lane]
    carried = lane_patches(lock, export.lane)
    wine = sorted(
        (patch for patch in carried if patch.component == "wine"),
        key=lambda patch: patch.number,
    )
    fex = [patch for patch in carried if patch.component == "fex"]
    document: dict[str, Any] = {
        "schema": 1,
        "kind": "arknights-patch-set",
        "generated_for": "wine-build-new",
        "submodule_path": "third-party/arknights-macos-runtime",
        "source": {
            "repository": "https://github.com/LuMiSxh/Arknights-MacOS-Runtime",
            "export_branch": "main",
        },
        "base": {"wine": export.wine_base, "queue_before": export.queue_before},
        "application": "build-time",
        "gates": "runtime",
        "master_env": "LMISXH_AKMOCL",
        "modifiers": MODIFIERS,
        "wine": {
            "portfile": PORTFILE,
            "patches": [
                _wine_entry(export, patch, export.first_order + position)
                for position, patch in enumerate(wine)
            ],
        },
        "excluded": EXCLUDED,
        "opt_outs": OPT_OUTS,
        "opt_out_semantics": OPT_OUT_SEMANTICS,
        "patch_alias": "patches/wine/arknights-macos-runtime",
        "patch_alias_target": "third-party/arknights-macos-runtime/wine-build-new/patches",
        "patch_alias_mode": "per-file",
        "portfile_prefix": "arknights-macos-runtime/",
        "fex": {
            "base": lane.sources["fex"].commit,
            "application": FEX_APPLICATION,
            "patches": [_file_entry(patch.files[export.lane]) for patch in fex],
        },
    }
    return json.dumps(document, indent=2) + "\n"
