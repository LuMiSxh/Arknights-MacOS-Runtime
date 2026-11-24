# SPDX-License-Identifier: MPL-2.0

"""Fail when a release tag or release already exists. Releases are never replaced."""

import argparse
import os

from scripts.lib.console import error, success
from scripts.lib.github import GitHubError, release_absent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="-m scripts release assert-absent")
    parser.add_argument("--tag", required=True, help="release tag, such as v1.0.2")
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="owner/name; the default is GITHUB_REPOSITORY",
    )
    arguments = parser.parse_args(argv)
    if not arguments.repository:
        parser.error("--repository or GITHUB_REPOSITORY is required")
    try:
        absent = release_absent(arguments.repository, arguments.tag)
    except GitHubError as failure:
        error(f"cannot prove that {arguments.tag} is absent: {failure}")
        return 1
    if not absent:
        error(
            f"tag or release {arguments.tag} already exists; "
            "corrections require a new version"
        )
        return 1
    success(f"{arguments.tag} does not exist yet")
    return 0
