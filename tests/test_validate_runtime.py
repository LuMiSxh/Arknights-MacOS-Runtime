# SPDX-License-Identifier: MPL-2.0

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from scripts.validate_runtime import (
    RuntimeValidationError,
    validate_link_references,
    validate_macho_targets,
    validate_required_architectures,
    validate_structure,
)


class RuntimeStructureTests(unittest.TestCase):
    def test_script_entrypoint_loads_its_runtime_module(self) -> None:
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(root / "scripts" / "validate_runtime.py"), "--help"],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.required = ["Wine/bin/wine64", "DXMT/x64/d3d11.dll"]

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def create_required_files(self) -> None:
        for relative in self.required:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")

    def test_accepts_required_regular_files(self) -> None:
        self.create_required_files()
        validate_structure(self.root, self.required)

    def test_rejects_a_missing_required_file(self) -> None:
        with self.assertRaisesRegex(RuntimeValidationError, "missing required file"):
            validate_structure(self.root, self.required)

    def test_rejects_a_required_directory(self) -> None:
        (self.root / self.required[0]).mkdir(parents=True)
        with self.assertRaisesRegex(RuntimeValidationError, "missing required file"):
            validate_structure(self.root, self.required)

    def test_validates_locked_payload_architectures(self) -> None:
        self.create_required_files()

        def command_result(command: list[str], **_: object) -> CompletedProcess[str]:
            kind = (
                "PE32+ executable (DLL) x86-64"
                if "DXMT/x64" in command[-1]
                else "Mach-O 64-bit executable x86_64"
            )
            return CompletedProcess(command, 0, kind, "")

        with patch(
            "scripts.validate_runtime.subprocess.run", side_effect=command_result
        ):
            self.assertEqual(
                validate_required_architectures(self.root, self.required), 2
            )

    def test_rejects_the_wrong_locked_payload_architecture(self) -> None:
        self.create_required_files()
        result = CompletedProcess([], 0, "PE32 executable Intel 80386", "")
        with (
            patch("scripts.validate_runtime.subprocess.run", return_value=result),
            self.assertRaisesRegex(RuntimeValidationError, "unexpected architecture"),
        ):
            validate_required_architectures(self.root, self.required)

    def test_rejects_a_symlink_that_escapes_the_runtime(self) -> None:
        self.create_required_files()
        outside = self.root.parent / "outside-runtime"
        outside.write_bytes(b"outside")
        link = self.root / "Wine" / "escape"
        link.symlink_to(outside)
        try:
            with self.assertRaisesRegex(RuntimeValidationError, "escapes runtime root"):
                validate_structure(self.root, self.required)
        finally:
            outside.unlink()

    def test_allows_an_inherited_newer_target_only_when_identical_to_baseline(
        self,
    ) -> None:
        candidate = self.root / "candidate"
        baseline = self.root / "baseline"
        (candidate / "Wine").mkdir(parents=True)
        (baseline / "Wine").mkdir(parents=True)
        (candidate / "Wine" / "driver.so").write_bytes(b"same")
        (baseline / "Wine" / "driver.so").write_bytes(b"same")

        def command_result(command: list[str], **_: object) -> CompletedProcess[str]:
            output = (
                "Mach-O 64-bit bundle\n" if command[0] == "file" else "  minos 26.0\n"
            )
            return CompletedProcess(command, 0, output, "")

        with patch(
            "scripts.validate_runtime.subprocess.run", side_effect=command_result
        ):
            self.assertEqual(
                validate_macho_targets(candidate, "15.0", baseline), (1, 1)
            )

        (candidate / "Wine" / "driver.so").write_bytes(b"changed")
        with (
            patch(
                "scripts.validate_runtime.subprocess.run", side_effect=command_result
            ),
            self.assertRaisesRegex(RuntimeValidationError, "newer than 15.0"),
        ):
            validate_macho_targets(candidate, "15.0", baseline)

    def test_rejects_non_system_absolute_macho_dependencies(self) -> None:
        with self.assertRaisesRegex(RuntimeValidationError, "/nix/store"):
            validate_link_references(
                Path("Wine/lib/wine/x86_64-unix/coreaudio.so"),
                "coreaudio.so:\n\t/nix/store/hash/lib/libfoo.dylib (compatibility version 1.0.0)\n",
            )

    def test_accepts_relative_and_system_macho_dependencies(self) -> None:
        validate_link_references(
            Path("Wine/lib/wine/x86_64-unix/coreaudio.so"),
            "coreaudio.so:\n\t@rpath/libfoo.dylib (compatibility version 1.0.0)\n"
            "\t/System/Library/Frameworks/CoreAudio.framework/CoreAudio (compatibility version 1.0.0)\n"
            "\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0)\n",
        )


if __name__ == "__main__":
    unittest.main()
