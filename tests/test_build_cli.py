# SPDX-License-Identifier: MPL-2.0

import subprocess
import unittest
from pathlib import Path


class BuildCLIContractTests(unittest.TestCase):
    def test_rejects_an_unknown_stage_before_doing_work(self) -> None:
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["bash", str(root / "scripts" / "build-canary.sh"), "unknown"],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "expected base, audio, hardware-cursor, performance, ace, cef, cn, or combined",
            result.stderr,
        )

    def test_hardware_cursor_stage_only_overlays_wine_ntdll(self) -> None:
        root = Path(__file__).resolve().parents[1]
        script = (root / "scripts" / "build-canary.sh").read_text(encoding="utf-8")

        self.assertIn("base|audio|hardware-cursor|performance", script)
        self.assertIn('if [[ "$stage" == hardware-cursor ]]; then', script)
        self.assertIn('prepare "$stage" --destination-root "$source_root"', script)
        self.assertIn(
            'if [[ "$stage" == hardware-cursor || "$stage" == audio || "$stage" == ace || "$stage" == cef || "$stage" == cn || "$stage" == combined ]]; then',
            script,
        )
        self.assertIn('make -j"$(sysctl -n hw.logicalcpu)" dlls/ntdll/ntdll.so', script)
        self.assertIn('cp "$wine_build/dlls/ntdll/ntdll.so"', script)
        self.assertIn("overlay_wine_file lib/wine/x86_64-unix/ntdll.so", script)
        self.assertIn(
            'if [[ "$stage" == performance || "$stage" == combined ]]; then',
            script,
        )

    def test_combined_overlay_replaces_bilibili_renderer_artifacts(self) -> None:
        root = Path(__file__).resolve().parents[1]
        script = (root / "scripts" / "build-canary.sh").read_text(encoding="utf-8")

        for artifact in (
            "lib/wine/x86_64-unix/winemac.so",
            "lib/wine/x86_64-windows/ntdll.dll",
            "lib/wine/x86_64-unix/win32u.so",
        ):
            self.assertIn(f"overlay_wine_file {artifact}", script)

        self.assertIn(
            '"$stage" == ace || "$stage" == cef || "$stage" == combined', script
        )
        self.assertIn("overlay_wine_file lib/wine/x86_64-windows/ntdll.dll", script)


if __name__ == "__main__":
    unittest.main()
