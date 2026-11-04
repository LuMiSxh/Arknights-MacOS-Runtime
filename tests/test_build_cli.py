# SPDX-License-Identifier: MPL-2.0

import subprocess
import sys
import unittest
from pathlib import Path

from scripts.x86.build import (
    STAGE_HINT,
    patched_machos,
    wine_overlay_artifacts,
)


class BuildCLIContractTests(unittest.TestCase):
    def test_rejects_an_unknown_stage_before_doing_work(self) -> None:
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(root / "scripts" / "build.py"), "canary", "unknown"],
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn(STAGE_HINT, result.stderr)

    def test_hardware_cursor_stage_only_overlays_wine_ntdll(self) -> None:
        self.assertEqual(
            wine_overlay_artifacts("hardware-cursor"),
            ("lib/wine/x86_64-unix/ntdll.so",),
        )
        self.assertEqual(
            patched_machos("hardware-cursor"), ("lib/wine/x86_64-unix/ntdll.so",)
        )

    def test_combined_overlay_replaces_bilibili_renderer_artifacts(self) -> None:
        artifacts = wine_overlay_artifacts("combined")

        for artifact in (
            "lib/wine/x86_64-unix/winemac.so",
            "lib/wine/x86_64-windows/ntdll.dll",
            "lib/wine/x86_64-unix/win32u.so",
        ):
            self.assertIn(artifact, artifacts)

    def test_a_stage_overlays_only_its_own_families(self) -> None:
        self.assertEqual(
            wine_overlay_artifacts("audio"),
            ("lib/wine/x86_64-unix/winecoreaudio.so",),
        )
        self.assertEqual(
            wine_overlay_artifacts("cef"),
            ("lib/wine/x86_64-windows/ntdll.dll",),
        )
        self.assertEqual(patched_machos("cef"), ())
        self.assertIn("lib/wine/x86_64-unix/win32u.so", wine_overlay_artifacts("cn"))

    def test_only_macho_overlays_are_signed(self) -> None:
        for stage in ("audio", "ace", "cn", "combined"):
            with self.subTest(stage=stage):
                for artifact in patched_machos(stage):
                    self.assertTrue(artifact.endswith(".so"))
                self.assertEqual(
                    set(patched_machos(stage)) - set(wine_overlay_artifacts(stage)),
                    set(),
                )


if __name__ == "__main__":
    unittest.main()
