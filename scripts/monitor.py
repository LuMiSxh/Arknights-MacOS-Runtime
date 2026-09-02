#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Verify pinned runtime sources and summarize changed repository heads."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

if __package__:
    from .lib.console import error, success
    from .runtime import LOCK_PATH, SourcePin, load_lock, monitored_sources
else:
    from lib.console import error, success
    from runtime import LOCK_PATH, SourcePin, load_lock, monitored_sources

MAXIMUM_RESPONSE_BYTES = 1_048_576
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class SourceStatus:
    name: str
    repository: str
    pinned: str
    head: str | None
    state: str
    detail: str | None


@dataclass(frozen=True)
class MonitorReport:
    checked_at: str
    sources: tuple[SourceStatus, ...]

    @property
    def has_failures(self) -> bool:
        return any(source.state == "unavailable" for source in self.sources)


def api_urls(source: SourcePin) -> tuple[str, str]:
    parsed = urlparse(source.repository)
    project = parsed.path.removeprefix("/").removesuffix(".git")
    if parsed.hostname == "github.com":
        repository = f"https://api.github.com/repos/{project}"
        return repository, f"{repository}/commits/{source.commit}"
    if parsed.hostname == "gitlab.winehq.org":
        repository = "https://gitlab.winehq.org/api/v4/projects/" + quote(
            project, safe=""
        )
        return repository, f"{repository}/repository/commits/{source.commit}"
    raise ValueError(f"unsupported repository host: {parsed.hostname}")


def _head_url(repository_api: str, repository: str, branch: str) -> str:
    suffix = f"commits/{quote(branch, safe='')}"
    if urlparse(repository).hostname == "gitlab.winehq.org":
        suffix = f"repository/{suffix}"
    return f"{repository_api}/{suffix}"


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("API response is not an object")
    return value


def _string(value: object, field: str) -> str:
    mapping = _mapping(value)
    result = mapping.get(field)
    if not isinstance(result, str) or not result:
        raise ValueError(f"API response has no {field}")
    return result


def _commit_id(value: object, repository: str) -> str:
    field = "id" if urlparse(repository).hostname == "gitlab.winehq.org" else "sha"
    return _string(value, field)


def _safe_error(caught: BaseException) -> str:
    if isinstance(caught, urllib.error.HTTPError):
        return f"HTTP {caught.code}"
    match = re.search(r"\bHTTP ([1-5][0-9]{2})\b", str(caught))
    return f"HTTP {match.group(1)}" if match else type(caught).__name__


def probe_sources(
    sources: Iterable[SourcePin],
    fetch_json: Callable[[str], object],
    *,
    checked_at: str,
) -> MonitorReport:
    statuses: list[SourceStatus] = []
    for source in sources:
        try:
            repository_url, commit_url = api_urls(source)
            repository = fetch_json(repository_url)
            branch = _string(repository, "default_branch")
            pinned = _commit_id(fetch_json(commit_url), source.repository)
            if pinned != source.commit:
                raise ValueError("pinned commit response does not match lock")
            head = _commit_id(
                fetch_json(_head_url(repository_url, source.repository, branch)),
                source.repository,
            )
            if SHA_PATTERN.fullmatch(head) is None:
                raise ValueError("repository head is not a full commit hash")
            state = "current" if head == source.commit else "changed"
            statuses.append(
                SourceStatus(
                    source.name,
                    source.repository,
                    source.commit,
                    head,
                    state,
                    None,
                )
            )
        except (OSError, TypeError, ValueError) as caught:
            statuses.append(
                SourceStatus(
                    source.name,
                    source.repository,
                    source.commit,
                    None,
                    "unavailable",
                    _safe_error(caught),
                )
            )
    return MonitorReport(checked_at, tuple(statuses))


def report_value(report: MonitorReport) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "checkedAt": report.checked_at,
        "sources": [asdict(source) for source in report.sources],
    }


def report_markdown(report: MonitorReport) -> str:
    labels = {"current": "Current", "changed": "Changed", "unavailable": "Unavailable"}
    lines = [
        "## Runtime source monitor",
        "",
        f"Checked: `{report.checked_at}`",
        "",
        "| Source | State | Pinned | Repository head |",
        "| --- | --- | --- | --- |",
    ]
    for source in report.sources:
        head = source.head[:12] if source.head else source.detail or "Unavailable"
        lines.append(
            f"| {source.name} | {labels[source.state]} | `{source.pinned[:12]}` | `{head}` |"
        )
    lines.extend(
        [
            "",
            "A changed repository head is informational and never updates a pin automatically.",
        ]
    )
    return "\n".join(lines) + "\n"


def fetch_json(url: str) -> object:
    headers = {
        "Accept": "application/vnd.github+json, application/json",
        "User-Agent": "arknights-macos-runtime-monitor",
    }
    if urlparse(url).hostname == "api.github.com" and (
        token := os.getenv("GITHUB_TOKEN")
    ):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read(MAXIMUM_RESPONSE_BYTES + 1)
    if len(body) > MAXIMUM_RESPONSE_BYTES:
        raise ValueError("API response is too large")
    return json.loads(body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    arguments = parser.parse_args()
    checked_at = (
        datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    report = probe_sources(
        monitored_sources(load_lock(LOCK_PATH)),
        fetch_json,
        checked_at=checked_at,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report_value(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = report_markdown(report)
    if arguments.summary:
        with arguments.summary.open("a", encoding="utf-8") as output:
            output.write(summary)
    else:
        print(summary, end="")
    if report.has_failures:
        error("one or more pinned runtime sources could not be verified")
        return 1
    success("Verified pinned runtime sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
