# SPDX-License-Identifier: MPL-2.0

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from scripts.frametime import FrametimeError, record


class FakeCollector:
    def __init__(
        self,
        *,
        trace_names: tuple[str, ...] = ("capture.atrc",),
        fail_overview_at: int | None = None,
    ) -> None:
        self.commands: list[list[str]] = []
        self.trace_names = trace_names
        self.fail_overview_at = fail_overview_at
        self.overview_count = 0

    def __call__(self, command: list[str]) -> str:
        self.commands.append(command)
        if command[1] == "collect":
            raw_directory = Path(command[-1])
            raw_directory.mkdir(parents=True)
            traces = [raw_directory / name for name in self.trace_names]
            for trace in traces:
                trace.write_text("trace", encoding="utf-8")
            return json.dumps({"traces": [str(trace) for trace in traces]})
        self.overview_count += 1
        if self.overview_count == self.fail_overview_at:
            raise subprocess.CalledProcessError(1, command)
        return '{"timeline": []}'


class FrametimeRecordTests(unittest.TestCase):
    def test_record_creates_raw_overview_and_manifest_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tool = root / "metalperftrace"
            tool.touch()
            tool.chmod(0o755)
            collector = FakeCollector()
            times = iter(
                (
                    datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC),
                    datetime(2026, 9, 19, 12, 0, 5, tzinfo=UTC),
                )
            )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                run_directory = record(
                    "fixed-scene",
                    seconds=5,
                    output_root=root / "frametimes",
                    tool_path=tool,
                    run=collector,
                    wait=lambda _: None,
                    clock=lambda: next(times),
                )

            manifest = json.loads((run_directory / "manifest.json").read_text())
            self.assertEqual(manifest["case"], "fixed-scene")
            self.assertEqual(manifest["requestedDurationSeconds"], 5)
            self.assertEqual(len(manifest["rawTracePaths"]), 1)
            self.assertEqual(len(manifest["overviewPaths"]), 1)
            self.assertTrue(Path(manifest["rawTracePaths"][0]).is_file())
            self.assertTrue(Path(manifest["overviewPaths"][0]).is_file())
            self.assertEqual(
                collector.commands,
                [
                    [
                        str(tool),
                        "collect",
                        "--start",
                        "2026-09-19T12:00:00Z",
                        "--end",
                        "2026-09-19T12:00:05Z",
                        "--prefix",
                        "fixed-scene",
                        "--json",
                        str(run_directory / "raw"),
                    ],
                    [
                        str(tool),
                        "overview",
                        "--json-include-timeline",
                        str(run_directory / "raw" / "capture.atrc"),
                    ],
                ],
            )
            self.assertEqual(
                output.getvalue(),
                "Begin the fixed scene now; recording for 5 seconds.\n"
                f"Frametime recording complete: {run_directory}\n",
            )

    def test_record_rejects_unsafe_case_name(self) -> None:
        with self.assertRaisesRegex(FrametimeError, "safe path component"):
            record("../unsafe", seconds=1)

    def test_record_reports_an_unavailable_collector(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            unavailable = Path(temporary) / "metalperftrace"

            with self.assertRaisesRegex(FrametimeError, "unavailable"):
                record("fixed-scene", seconds=1, tool_path=unavailable)

    def test_record_propagates_collector_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tool = root / "metalperftrace"
            tool.touch()
            tool.chmod(0o755)

            def fail(_: list[str]) -> str:
                raise subprocess.CalledProcessError(1, [str(tool), "collect"])

            with self.assertRaises(subprocess.CalledProcessError):
                record(
                    "fixed-scene",
                    seconds=1,
                    output_root=root / "frametimes",
                    tool_path=tool,
                    run=fail,
                    wait=lambda _: None,
                )

    def test_record_rejects_an_empty_collector_trace_list(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tool = root / "metalperftrace"
            tool.touch()
            tool.chmod(0o755)
            output = io.StringIO()

            with (
                contextlib.redirect_stdout(output),
                self.assertRaisesRegex(FrametimeError, "no traces"),
            ):
                record(
                    "fixed-scene",
                    seconds=1,
                    output_root=root / "frametimes",
                    tool_path=tool,
                    run=FakeCollector(trace_names=()),
                    wait=lambda _: None,
                )

            self.assertNotIn("complete", output.getvalue())

    def test_record_preserves_partial_artifacts_when_an_overview_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tool = root / "metalperftrace"
            tool.touch()
            tool.chmod(0o755)
            collector = FakeCollector(
                trace_names=("first.atrc", "second.atrc"), fail_overview_at=2
            )

            with self.assertRaisesRegex(FrametimeError, "partial artifacts") as caught:
                record(
                    "fixed-scene",
                    seconds=1,
                    output_root=root / "frametimes",
                    tool_path=tool,
                    run=collector,
                    wait=lambda _: None,
                )

            run_directory = Path(str(caught.exception).rsplit(": ", maxsplit=1)[1])
            manifest = json.loads((run_directory / "manifest.json").read_text())
            self.assertEqual(len(manifest["rawTracePaths"]), 2)
            self.assertEqual(len(manifest["overviewPaths"]), 1)
            self.assertTrue(Path(manifest["overviewPaths"][0]).is_file())
            self.assertIn(str(run_directory), str(caught.exception))


if __name__ == "__main__":
    unittest.main()
