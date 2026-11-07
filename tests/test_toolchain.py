# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import unittest

from scripts.release.toolchain import UNAVAILABLE, collect_toolchain


class ToolchainReportTests(unittest.TestCase):
    def test_collects_brew_xcode_and_sdk_versions(self) -> None:
        outputs = {
            "brew": "meson 1.9.0\nninja 1.13.1\nmingw-w64 13.0.0_1 13.0.0_2\n",
            "xcodebuild": "Xcode 26.0\nBuild version 17A324",
            "--show-sdk-version": "26.0",
            "--show-sdk-path": "/SDKs/MacOSX26.0.sdk",
            "sw_vers": "26.0.1",
        }

        def run(command: list[str]) -> str | None:
            return outputs.get(command[0]) or outputs.get(command[-1])

        report = collect_toolchain(run)

        self.assertEqual(report["brew"]["meson"], "1.9.0")
        self.assertEqual(report["brew"]["mingw-w64"], "13.0.0_1 13.0.0_2")
        self.assertEqual(report["brew"]["ccache"], UNAVAILABLE)
        self.assertEqual(report["xcode"], "Xcode 26.0 Build version 17A324")
        self.assertEqual(report["sdkVersion"], "26.0")
        self.assertEqual(report["macOS"], "26.0.1")

    def test_marks_missing_tools_as_unavailable(self) -> None:
        report = collect_toolchain(lambda command: None)

        self.assertEqual(report["xcode"], UNAVAILABLE)
        self.assertEqual(report["sdkVersion"], UNAVAILABLE)
        self.assertEqual(report["sdkPath"], UNAVAILABLE)
        self.assertEqual(report["macOS"], UNAVAILABLE)
        self.assertTrue(all(value == UNAVAILABLE for value in report["brew"].values()))


if __name__ == "__main__":
    unittest.main()
