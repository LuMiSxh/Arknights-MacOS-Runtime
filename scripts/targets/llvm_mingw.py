#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Print the llvm-mingw toolchain pin of the native-arm64 lock.

Two lines: the download URL, then the SHA-256. Both are empty when the lock
has no `toolchain.llvmMingw` entry, so the release workflow can fall back to
the repository variables.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lib.console import error
from scripts.lock.model import Lock, LockError, load_lock


def llvm_mingw_pin(lock: Lock) -> tuple[str, str]:
    """Return the pinned llvm-mingw URL and SHA-256, or two empty strings."""

    toolchain = lock.llvm_mingw
    if toolchain is None:
        return "", ""
    return toolchain.url, toolchain.sha256


def main() -> int:
    try:
        lock = load_lock()
    except (LockError, OSError) as caught:
        error(str(caught))
        return 1
    url, digest = llvm_mingw_pin(lock)
    print(url)
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
