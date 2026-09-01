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
        self.assertIn("expected base, audio, cursor, cn, or combined", result.stderr)


if __name__ == "__main__":
    unittest.main()
