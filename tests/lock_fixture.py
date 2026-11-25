# SPDX-License-Identifier: MPL-2.0

"""Valid schema 4 runtime locks for tests. Each test supplies its own patch registry."""

from typing import Any

DEFAULT_LANE = "rosetta-x86_64"
EXTERNAL_LANE = "native-arm64"


def _source(name: str, digit: str, version: str | None = None) -> dict[str, str]:
    source = {
        "repository": f"https://github.com/example/{name}.git",
        "commit": digit * 40,
    }
    if version is not None:
        source["version"] = version
    return source


def _interface() -> dict[str, Any]:
    return {
        "executables": ["bin/wine64", "bin/wineserver"],
        "requiredFiles": ["lib/wine/x86_64-unix/winemac.so"],
        "macDriver": "lib/wine/x86_64-unix/winemac.so",
        "launcher": {"path": "bin/Arknights", "target": "wine64"},
        "dxmt": {
            "payloadDirectory": "DXMT",
            "destinations": {"x64": "system32"},
            "libraries": ["d3d11.dll"],
        },
        "features": {
            "hardwareCursor": True,
            "metalFXSpatialUpscaling": True,
            "nativeFullscreenSpace": True,
        },
    }


def patch_entry(
    patch_id: str,
    component: str,
    number: int,
    path: str,
    sha256: str,
    *,
    lane: str = DEFAULT_LANE,
) -> dict[str, Any]:
    return {
        "id": patch_id,
        "component": component,
        "number": number,
        "gate": None,
        "default": True,
        "files": {lane: {"path": path, "sha256": sha256}},
    }


def synthetic_lock(patches: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a valid lock with fixed pins and the given patch registry."""

    return {
        "schemaVersion": 4,
        "shared": {
            "toolchain": {
                "llvmMingw": {
                    "url": "https://github.com/example/llvm-mingw/releases/download/v1/llvm-mingw.tar.xz",
                    "sha256": "6" * 64,
                }
            },
            "nixpkgs": _source("nixpkgs", "1"),
        },
        "lanes": {
            DEFAULT_LANE: {
                "arch": "x86_64",
                "build": "build",
                "minimumMacOS": "15.0",
                "sources": {
                    "wine": _source("wine", "a", "11.17"),
                    "dxmt": _source("dxmt", "b", "0.80"),
                },
                "base": {
                    "url": "https://github.com/example/runtime/releases/download/v1/Libraries.tar.gz",
                    "sha256": "c" * 64,
                    "recipe": _source("recipe", "d"),
                    "provenance": {
                        "moltenvk": _source("moltenvk", "e"),
                        "wineGecko": _source("wine-gecko", "f"),
                    },
                },
                "interface": _interface(),
            },
            EXTERNAL_LANE: {
                "arch": "arm64",
                "build": "external",
                "minimumMacOS": "27.0",
                "sources": {
                    "wine": _source("wine", "2", "11.18"),
                    "fex": _source("fex", "3", "2610"),
                    "dxmt": _source("dxmt", "4", "0.80"),
                },
                "artifact": {
                    "catalog": "wine",
                    "release": "wine-11-18-arm64-v5",
                    "sha256": "5" * 64,
                },
                "interface": _interface(),
            },
        },
        "patches": patches,
        "export": {
            "wine-build-new": {
                "lane": EXTERNAL_LANE,
                "wineBase": "9" * 40,
                "queueBefore": 68,
                "firstOrder": 73,
                "optionalPatches": [],
            }
        },
    }
