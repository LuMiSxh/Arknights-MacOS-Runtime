# SPDX-License-Identifier: MPL-2.0

import unittest

from scripts.monitor import (
    probe_sources,
)
from scripts.runtime import SourcePin


class SourceMonitorTests(unittest.TestCase):
    def test_reads_gitlab_commit_ids(self) -> None:
        pin = SourcePin(
            "wineGecko",
            "https://gitlab.winehq.org/wine/wine-gecko.git",
            "a" * 40,
        )

        def fetch(url: str) -> object:
            if url.endswith("projects/wine%2Fwine-gecko"):
                return {"default_branch": "main"}
            return {"id": "a" * 40}

        report = probe_sources((pin,), fetch, checked_at="2026-09-02T12:00:00Z")

        self.assertEqual(report.sources[0].state, "current")
        self.assertFalse(report.has_failures)


if __name__ == "__main__":
    unittest.main()
