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
            "expected base, audio, cursor, performance, cn, or combined", result.stderr
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

    def test_bilibili_runtime_contract_has_no_separate_toggle(self) -> None:
        root = Path(__file__).resolve().parents[1]
        texts = [
            (root / "runtime.lock.json").read_text(encoding="utf-8"),
            (root / "scripts" / "build-canary.sh").read_text(encoding="utf-8"),
            (
                root
                / "patches"
                / "wine"
                / "cn"
                / "cef"
                / "0001-ntdll-bilibili-cef-80-stackbase.patch"
            ).read_text(encoding="utf-8"),
            (
                root
                / "patches"
                / "wine"
                / "cn"
                / "windowing"
                / "0001-win32u-winemac-bilibili-layered-child.patch"
            ).read_text(encoding="utf-8"),
        ]

        for text in texts[2:]:
            self.assertIn("ARKNIGHTS_RUNTIME_CN_COMPAT", text)
            self.assertNotIn("MESSAGE(", text)
        for text in texts:
            self.assertNotIn("ARKNIGHTS_RUNTIME_BILIBILI_", text)
        for required in (
            "Chrome.WindowTranslucent",
            "chrome_widgetW",
            "NtUserIsWindowVisible",
            "NtUserGetProp(hwnd, translucentW)",
            "WineContentView* view = (WineContentView*)v;",
            "WineWindow* window = (WineWindow*)w;",
            "macdrv_retain_view(data->layered_view)",
            "macdrv_release_view(layered_view)",
        ):
            self.assertIn(required, texts[3])


if __name__ == "__main__":
    unittest.main()
