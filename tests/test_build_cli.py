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
            "expected base, audio, cursor, performance, ace, cef, cn, or combined",
            result.stderr,
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

    def test_cef_and_cn_runtime_contracts_use_separate_toggles(self) -> None:
        root = Path(__file__).resolve().parents[1]
        texts = [
            (root / "runtime.lock.json").read_text(encoding="utf-8"),
            (root / "scripts" / "build-canary.sh").read_text(encoding="utf-8"),
            (
                root / "patches" / "wine" / "cef" / "0001-ntdll-cef-compatibility.patch"
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

        cef_patch, windowing_patch = texts[2:]
        self.assertIn("ARKNIGHTS_RUNTIME_CEF_COMPAT", cef_patch)
        self.assertIn("ARKNIGHTS_RUNTIME_CN_COMPAT", cef_patch)
        self.assertIn("struct arknights_cef_descriptor", cef_patch)
        self.assertIn("ARKNIGHTS_CEF_COMPAT_LEGACY_CN", cef_patch)
        self.assertIn("ARKNIGHTS_CEF_REGION_CN", cef_patch)
        self.assertIn("arknights_apply_cef_descriptor", cef_patch)
        self.assertNotIn("ARKNIGHTS_RUNTIME_ACE_COMPACT", cef_patch)
        self.assertNotIn("MESSAGE(", cef_patch)
        self.assertIn("ARKNIGHTS_RUNTIME_CN_COMPAT", windowing_patch)
        self.assertNotIn("ARKNIGHTS_RUNTIME_CEF_COMPAT", windowing_patch)
        self.assertNotIn("ARKNIGHTS_RUNTIME_ACE_COMPACT", windowing_patch)
        self.assertNotIn("MESSAGE(", windowing_patch)
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

    def test_ace_runtime_contract_uses_the_ace_toggle(self) -> None:
        root = Path(__file__).resolve().parents[1]
        texts = [
            path.read_text(encoding="utf-8")
            for path in sorted((root / "patches" / "wine" / "ace").rglob("*.patch"))
        ]

        self.assertEqual(len(texts), 4)
        for text in texts:
            self.assertIn("ARKNIGHTS_RUNTIME_ACE_COMPACT", text)
            self.assertNotIn("ARKNIGHTS_RUNTIME_CN_COMPAT", text)

    def test_ace_ntoskrnl_exports_capture_persistent_thread_state(self) -> None:
        root = Path(__file__).resolve().parents[1]
        patch = (
            root
            / "patches"
            / "wine"
            / "ace"
            / "ntoskrnl"
            / "0001-ntoskrnl-compatibility-surface.patch"
        ).read_text(encoding="utf-8")

        self.assertIn("KeCapturePersistentThreadState", patch)
        self.assertIn("@ stdcall KeCapturePersistentThreadState", patch)
        self.assertIn("if (!arknights_runtime_ace_compact_enabled())", patch)

    def test_ace_ntoskrnl_exports_callable_audit_parameter_routine(self) -> None:
        root = Path(__file__).resolve().parents[1]
        patch = (
            root
            / "patches"
            / "wine"
            / "ace"
            / "ntoskrnl"
            / "0001-ntoskrnl-compatibility-surface.patch"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "NTSTATUS WINAPI SeSetAuditParameter(void *audit_parameters, LONG type, ULONG index, void *data)",
            patch,
        )
        self.assertIn("@ stdcall SeSetAuditParameter(ptr long long ptr)", patch)
        self.assertIn(
            "if (!arknights_runtime_ace_compact_enabled()) return STATUS_NOT_IMPLEMENTED;",
            patch,
        )
        self.assertIn("return STATUS_SUCCESS;", patch)


if __name__ == "__main__":
    unittest.main()
