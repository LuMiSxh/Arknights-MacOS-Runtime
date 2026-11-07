#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Record a manually started Arknights scene with Metal Performance Trace."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ROOT / ".build" / "frametimes"
DEFAULT_TOOL_PATH = Path("/usr/bin/metalperftrace")
CASE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")

CommandRunner = Callable[[list[str]], str]


class FrametimeError(ValueError):
    """The requested frametime recording is unsafe or cannot be collected."""


def _utc_timestamp(value: datetime) -> str:
    return (
        value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


def _run(command: list[str]) -> str:
    return subprocess.run(command, capture_output=True, check=True, text=True).stdout


def _case_name(case: str) -> str:
    if case in {".", ".."} or CASE_PATTERN.fullmatch(case) is None:
        raise FrametimeError("case must be a safe path component")
    return case


def _run_directory(output_root: Path, case: str, start: datetime) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    stem = f"{case}-{start.astimezone(UTC):%Y%m%dT%H%M%SZ}"
    for sequence in range(1, 10_000):
        suffix = "" if sequence == 1 else f"-{sequence}"
        candidate = output_root / f"{stem}{suffix}"
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise FrametimeError("could not allocate a frametime run directory")


def _trace_paths(output: str) -> list[Path]:
    try:
        value: Any = json.loads(output)
    except json.JSONDecodeError as error:
        raise FrametimeError("metalperftrace collect did not return JSON") from error
    if not isinstance(value, dict) or not isinstance(value.get("traces"), list):
        raise FrametimeError("metalperftrace collect JSON has no traces list")
    traces = value["traces"]
    if not traces:
        raise FrametimeError("metalperftrace collect returned no traces")
    if not all(isinstance(trace, str) and trace for trace in traces):
        raise FrametimeError("metalperftrace collect JSON has an invalid trace path")
    return [Path(trace) for trace in traces]


def _write_manifest(
    run_directory: Path,
    *,
    case: str,
    start: datetime,
    end: datetime,
    seconds: int,
    tool_path: Path,
    traces: list[Path],
    overview_paths: list[Path],
) -> None:
    manifest = {
        "case": case,
        "start": _utc_timestamp(start),
        "end": _utc_timestamp(end),
        "requestedDurationSeconds": seconds,
        "toolPath": str(tool_path),
        "rawTracePaths": [str(trace) for trace in traces],
        "overviewPaths": [str(path) for path in overview_paths],
    }
    (run_directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def record(
    case: str,
    *,
    seconds: int,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    tool_path: Path = DEFAULT_TOOL_PATH,
    run: CommandRunner = _run,
    wait: Callable[[float], None] = time.sleep,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Path:
    """Collect one manually controlled window and return its artifact directory."""

    case = _case_name(case)
    if seconds <= 0:
        raise FrametimeError("seconds must be greater than zero")
    if not tool_path.is_file() or not os.access(tool_path, os.X_OK):
        raise FrametimeError(f"metalperftrace is unavailable at {tool_path}")

    start = clock()
    print(f"Begin the fixed scene now; recording for {seconds} seconds.", flush=True)
    wait(seconds)
    end = clock()
    run_directory = _run_directory(output_root, case, start)
    raw_directory = run_directory / "raw"
    traces = _trace_paths(
        run(
            [
                str(tool_path),
                "collect",
                "--start",
                _utc_timestamp(start),
                "--end",
                _utc_timestamp(end),
                "--prefix",
                case,
                "--json",
                str(raw_directory),
            ]
        )
    )
    overview_directory = run_directory / "overview"
    overview_directory.mkdir()
    overview_paths: list[Path] = []
    try:
        for index, trace in enumerate(traces, start=1):
            overview = overview_directory / f"trace-{index}.json"
            overview.write_text(
                run(
                    [
                        str(tool_path),
                        "overview",
                        "--json-include-timeline",
                        str(trace),
                    ]
                ),
                encoding="utf-8",
            )
            overview_paths.append(overview)
    except subprocess.CalledProcessError as error:
        _write_manifest(
            run_directory,
            case=case,
            start=start,
            end=end,
            seconds=seconds,
            tool_path=tool_path,
            traces=traces,
            overview_paths=overview_paths,
        )
        raise FrametimeError(
            f"overview failed; partial artifacts: {run_directory}"
        ) from error
    _write_manifest(
        run_directory,
        case=case,
        start=start,
        end=end,
        seconds=seconds,
        tool_path=tool_path,
        traces=traces,
        overview_paths=overview_paths,
    )
    print(f"Frametime recording complete: {run_directory}")
    return run_directory


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    record_parser = commands.add_parser("record", help="collect one named time window")
    record_parser.add_argument("case")
    record_parser.add_argument("--seconds", type=int, required=True)
    parsed = parser.parse_args(arguments)

    try:
        record(parsed.case, seconds=parsed.seconds)
    except FrametimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        print(
            f"error: metalperftrace exited with status {error.returncode}",
            file=sys.stderr,
        )
        return error.returncode or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
