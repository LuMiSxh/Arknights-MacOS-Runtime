#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Print the llvm-mingw toolchain pin of the native-arm64 lock.

Two lines: the download URL, then the SHA-256. Both are empty when the lock
has no `toolchain.llvmMingw` entry, so the release workflow can fall back to
the repository variables.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if __package__:
    from ..build_common import NATIVE_ARM64_TARGET
    from ..lib.console import error
    from ..runtime import LockError, load_lock
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.build_common import NATIVE_ARM64_TARGET
    from scripts.lib.console import error
    from scripts.runtime import LockError, load_lock


def llvm_mingw_pin(lock: dict[str, Any]) -> tuple[str, str]:
    """Return the pinned llvm-mingw URL and SHA-256, or two empty strings."""

    entry = (lock.get("toolchain") or {}).get("llvmMingw")
    if not isinstance(entry, dict):
        return "", ""
    return str(entry.get("url", "")), str(entry.get("sha256", ""))


def main() -> int:
    try:
        lock = load_lock(target=NATIVE_ARM64_TARGET)
    except (LockError, OSError) as caught:
        error(str(caught))
        return 1
    url, digest = llvm_mingw_pin(lock)
    print(url)
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
