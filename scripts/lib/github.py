# SPDX-License-Identifier: MPL-2.0

"""The one GitHub API client of the repository scripts."""

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

API_ROOT = "https://api.github.com"
PAGE_SIZE = 100

Fetch = Callable[[str], Any]


class GitHubError(RuntimeError):
    """A GitHub API request failed."""


class NotFoundError(GitHubError):
    """The API answered 404 for the requested path."""


def fetch(path: str) -> Any:
    """Return the decoded JSON of a GitHub API path. Use a token when one is set."""

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "arknights-macos-runtime-scripts",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(API_ROOT + path, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as failure:
        if (
            failure.code in (403, 429)
            and failure.headers.get("X-RateLimit-Remaining") == "0"
        ):
            raise GitHubError(
                "GitHub API rate limit reached. Set GITHUB_TOKEN or GH_TOKEN and retry."
            ) from failure
        if failure.code == 404:
            raise NotFoundError(f"GitHub API found nothing at {path}") from failure
        raise GitHubError(f"GitHub API returned {failure.code} for {path}") from failure
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as failure:
        raise GitHubError(f"cannot read {path}: {failure}") from failure


def paged(fetch_page: Fetch, path: str) -> list[Any]:
    """Collect every page of a list endpoint."""

    items: list[Any] = []
    separator = "&" if "?" in path else "?"
    page = 1
    while True:
        batch = fetch_page(f"{path}{separator}per_page={PAGE_SIZE}&page={page}")
        items.extend(batch)
        if len(batch) < PAGE_SIZE:
            return items
        page += 1


def release_absent(repository: str, tag: str, fetch_json: Fetch = fetch) -> bool:
    """Return True when neither a release nor a tag named `tag` exists."""

    for path in (
        f"/repos/{repository}/releases/tags/{tag}",
        f"/repos/{repository}/git/ref/tags/{tag}",
    ):
        try:
            fetch_json(path)
        except NotFoundError:
            continue
        return False
    return True
