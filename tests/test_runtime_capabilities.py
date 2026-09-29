# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.runtime import ROOT, load_lock
from scripts.runtime_capabilities import (
    CapabilityContractError,
    load_capability_manifest,
    validate_capability_contract,
    validate_packaged_capability_manifest,
    validate_source_capability_contract,
)


class RuntimeCapabilityContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lock = load_lock()
        self.manifest_path = ROOT / self.lock["interface"]["runtimeCapabilities"]
        self.manifest = load_capability_manifest(self.manifest_path)
        self.patches = {
            patch["id"]: (ROOT / patch["path"]).read_text(encoding="utf-8")
            for patch in self.lock["patches"]
        }

    def test_manifest_matches_the_pinned_patch_behavior(self) -> None:
        validate_capability_contract(
            self.manifest,
            latency_patch=self.patches["dxmt-cursor-frame-latency"],
            hardware_cursor_patch=self.patches["wine-hardware-cursor-suppression"],
        )

        self.assertEqual(
            self.manifest,
            {
                "schemaVersion": 1,
                "capabilities": {
                    "dxmtMaximumFrameLatency": {
                        "minimum": 0,
                        "maximum": 3,
                        "defaultValue": 3,
                    },
                    "hardwareCursor": True,
                },
            },
        )

    def test_manifest_cannot_claim_zero_for_a_legacy_latency_patch(self) -> None:
        legacy_patch = self.patches["dxmt-cursor-frame-latency"].replace(
            "configured.front() >= '0'", "configured.front() >= '1'"
        )

        with self.assertRaisesRegex(CapabilityContractError, "latency patch"):
            validate_capability_contract(
                self.manifest,
                latency_patch=legacy_patch,
                hardware_cursor_patch=self.patches["wine-hardware-cursor-suppression"],
            )

    def test_capability_manifest_reader_rejects_fifo_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fifo = Path(directory) / "runtime-capabilities.json"
            os.mkfifo(fifo)
            command = (
                "import sys\n"
                "from pathlib import Path\n"
                "from scripts.runtime_capabilities import CapabilityContractError, load_capability_manifest\n"
                "try:\n"
                "    load_capability_manifest(Path(sys.argv[1]))\n"
                "except CapabilityContractError:\n"
                "    pass\n"
                "else:\n"
                "    raise SystemExit('FIFO was accepted')\n"
            )
            try:
                result = subprocess.run(
                    [sys.executable, "-c", command, str(fifo)],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                self.fail("opening a FIFO capability manifest blocked")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_release_package_requires_the_exact_contract_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory) / "Libraries"
            runtime_root.mkdir()

            for unsafe_path in (
                "",
                ".",
                "..",
                "../outside.json",
                "nested/manifest.json",
                "nested\\manifest.json",
                "manifest\x00.json",
            ):
                with self.subTest(manifest_path=unsafe_path):
                    with self.assertRaisesRegex(
                        CapabilityContractError, "single filename"
                    ):
                        validate_packaged_capability_manifest(
                            runtime_root,
                            manifest_path=unsafe_path,
                            source_manifest=self.manifest,
                            required=False,
                        )
                    lock = {
                        **self.lock,
                        "interface": {
                            **self.lock["interface"],
                            "runtimeCapabilities": unsafe_path,
                        },
                    }
                    with self.assertRaisesRegex(
                        CapabilityContractError, "single filename"
                    ):
                        validate_source_capability_contract(lock, ROOT)

            validate_packaged_capability_manifest(
                runtime_root,
                manifest_path=self.lock["interface"]["runtimeCapabilities"],
                source_manifest=self.manifest,
                required=False,
            )
            with self.assertRaisesRegex(CapabilityContractError, "missing"):
                validate_packaged_capability_manifest(
                    runtime_root,
                    manifest_path=self.lock["interface"]["runtimeCapabilities"],
                    source_manifest=self.manifest,
                    required=True,
                )

            package_manifest = (
                runtime_root / self.lock["interface"]["runtimeCapabilities"]
            )
            package_manifest.write_text(
                json.dumps(self.manifest, sort_keys=True), encoding="utf-8"
            )
            validate_packaged_capability_manifest(
                runtime_root,
                manifest_path=self.lock["interface"]["runtimeCapabilities"],
                source_manifest=self.manifest,
                required=True,
            )

            modified = dict(self.manifest)
            modified["capabilities"] = {
                **self.manifest["capabilities"],
                "hardwareCursor": False,
            }
            package_manifest.write_text(json.dumps(modified), encoding="utf-8")
            with self.assertRaisesRegex(CapabilityContractError, "does not match"):
                validate_packaged_capability_manifest(
                    runtime_root,
                    manifest_path=self.lock["interface"]["runtimeCapabilities"],
                    source_manifest=self.manifest,
                    required=True,
                )
