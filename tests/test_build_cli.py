# SPDX-License-Identifier: MPL-2.0

import json
import re
import unittest
from pathlib import Path

from scripts.build_x86 import WINE_OVERLAY_ARTIFACTS, patched_machos

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = REPOSITORY_ROOT / "runtime.lock.json"

# Patch module directory -> every Wine output built from it.
MODULE_ARTIFACTS = {
    "kernel32": ("lib/wine/x86_64-windows/kernel32.dll",),
    "kernelbase": ("lib/wine/x86_64-windows/kernelbase.dll",),
    "ntdll": (
        "lib/wine/x86_64-unix/ntdll.so",
        "lib/wine/x86_64-windows/ntdll.dll",
    ),
    "ntoskrnl.exe": ("lib/wine/x86_64-windows/ntoskrnl.exe",),
    "userenv": ("lib/wine/x86_64-windows/userenv.dll",),
    "win32u": ("lib/wine/x86_64-unix/win32u.so",),
    "winecoreaudio.drv": ("lib/wine/x86_64-unix/winecoreaudio.so",),
    "winemac.drv": ("lib/wine/x86_64-unix/winemac.so",),
    "ws2_32": ("lib/wine/x86_64-windows/ws2_32.dll",),
}


def _patched_modules() -> set[str]:
    """Return the dll and driver directories that the locked wine patches touch."""
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for patch in lock["patches"]:
        if patch["component"] != "wine":
            continue
        text = (REPOSITORY_ROOT / patch["path"]).read_text(encoding="utf-8")
        for path in re.findall(r"^\+\+\+ b/(\S+)$", text, re.MULTILINE):
            if path.startswith("include/"):
                # Headers are compiled into the consuming modules, which are listed.
                continue
            parts = path.split("/")
            if parts[0] != "dlls":
                raise AssertionError(f"unmapped patch path: {path}")
            if len(parts) > 2 and parts[2] == "tests":
                # Test sources are not built into the runtime (--disable-tests).
                continue
            modules.add(parts[1])
    return modules


class BuildOverlayContractTests(unittest.TestCase):
    def test_overlay_covers_every_wine_module_the_patches_change(self) -> None:
        modules = _patched_modules()

        self.assertEqual(set(MODULE_ARTIFACTS), modules)
        expected = {
            artifact
            for artifacts in MODULE_ARTIFACTS.values()
            for artifact in artifacts
        }
        self.assertEqual(set(WINE_OVERLAY_ARTIFACTS), expected)

    def test_only_unix_libraries_are_signed(self) -> None:
        self.assertEqual(
            sorted(patched_machos()),
            sorted(a for a in WINE_OVERLAY_ARTIFACTS if a.endswith(".so")),
        )


if __name__ == "__main__":
    unittest.main()
