# SPDX-License-Identifier: MPL-2.0

import json
import unittest

from scripts.monitor import (
    MonitorReport,
    SourceStatus,
    api_urls,
    probe_sources,
    report_markdown,
    report_value,
)
from scripts.runtime import SourcePin


class SourceMonitorTests(unittest.TestCase):
    def test_builds_github_and_gitlab_commit_urls(self) -> None:
        github = SourcePin(
            "wine",
            "https://github.com/dappermint/winecx.git",
            "a" * 40,
        )
        gitlab = SourcePin(
            "wineGecko",
            "https://gitlab.winehq.org/wine/wine-gecko.git",
            "b" * 40,
        )

        self.assertEqual(
            api_urls(github),
            (
                "https://api.github.com/repos/dappermint/winecx",
                f"https://api.github.com/repos/dappermint/winecx/commits/{'a' * 40}",
            ),
        )
        self.assertEqual(
            api_urls(gitlab),
            (
                "https://gitlab.winehq.org/api/v4/projects/wine%2Fwine-gecko",
                f"https://gitlab.winehq.org/api/v4/projects/wine%2Fwine-gecko/repository/commits/{'b' * 40}",
            ),
        )

    def test_reports_current_and_changed_repository_heads(self) -> None:
        pins = (
            SourcePin("wine", "https://github.com/acme/wine.git", "a" * 40),
            SourcePin("dxmt", "https://github.com/acme/dxmt.git", "b" * 40),
        )

        def fetch(url: str) -> object:
            if url.endswith(("/repos/acme/wine", "/repos/acme/dxmt")):
                return {"default_branch": "main"}
            if url.endswith("/commits/main"):
                return {"sha": "a" * 40 if "/wine/" in url else "c" * 40}
            return {"sha": "a" * 40 if "/wine/" in url else "b" * 40}

        report = probe_sources(pins, fetch, checked_at="2026-09-02T12:00:00Z")

        self.assertEqual(
            [source.state for source in report.sources], ["current", "changed"]
        )
        self.assertEqual(report.sources[1].head, "c" * 40)
        self.assertFalse(report.has_failures)

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

    def test_records_only_sanitized_failure_text(self) -> None:
        pin = SourcePin("wine", "https://github.com/acme/wine.git", "a" * 40)

        def fetch(_: str) -> object:
            raise OSError("HTTP 404: secret response body")

        report = probe_sources((pin,), fetch, checked_at="2026-09-02T12:00:00Z")
        encoded = json.dumps(report_value(report))

        self.assertTrue(report.has_failures)
        self.assertEqual(report.sources[0].detail, "HTTP 404")
        self.assertNotIn("secret response body", encoded)

    def test_markdown_summarizes_every_source(self) -> None:
        report = MonitorReport(
            checked_at="2026-09-02T12:00:00Z",
            sources=(
                SourceStatus("wine", "repo", "a" * 40, "a" * 40, "current", None),
                SourceStatus("dxmt", "repo", "b" * 40, "c" * 40, "changed", None),
            ),
        )

        markdown = report_markdown(report)

        self.assertIn("## Runtime source monitor", markdown)
        self.assertIn("| wine | Current |", markdown)
        self.assertIn("| dxmt | Changed |", markdown)


if __name__ == "__main__":
    unittest.main()
