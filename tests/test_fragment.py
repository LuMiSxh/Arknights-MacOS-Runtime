# SPDX-License-Identifier: MPL-2.0

import json
import tempfile
import unittest
from pathlib import Path

from scripts.lanes import arm64
from scripts.release.provenance import (
    ProvenanceInputError,
    runtime_lock_provenance,
    validation_provenance,
)

ROOT = Path(__file__).resolve().parents[1]


class ValidationProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.report = Path(self._temporary.name) / "validation.json"

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def _write(self, **fields: object) -> None:
        report = {
            "deploymentTarget": "26.5",
            "inheritedMachOAboveTarget": 0,
            "releaseEligible": True,
            "status": "valid",
            **fields,
        }
        self.report.write_text(json.dumps(report), encoding="utf-8")

    def test_gate_rejects_a_built_lane_that_is_not_release_eligible(self) -> None:
        self._write(releaseEligible=False, status="valid-canary")

        with self.assertRaisesRegex(ProvenanceInputError, "not release eligible"):
            validation_provenance(self.report, "26.5")

    def test_external_lane_is_recorded_as_built_externally(self) -> None:
        self._write(releaseEligible=True)

        record = validation_provenance(self.report, "26.5", external=True)

        self.assertFalse(record["releaseEligible"])
        self.assertTrue(record["builtExternally"])


class RuntimeLockViewTests(unittest.TestCase):
    def test_native_arm64_view_resolves_its_own_deployment_target(self) -> None:
        view = runtime_lock_provenance(ROOT, arm64.TARGET.name)["contents"]

        self.assertEqual(view["target"], arm64.TARGET.name)
        self.assertEqual(view["buildMode"], "external")
