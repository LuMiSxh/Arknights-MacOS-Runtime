# SPDX-License-Identifier: MPL-2.0

"""Temporary re-exports of the runtime lock API.

Importers still use `scripts.runtime`. Move them to `scripts.lock`, then delete this file.
"""

from scripts.lock.model import (
    LOCK_PATH,
    Lock,
    LockError,
    SourcePin,
    load_lock,
    monitored_sources,
)
from scripts.lock.sources import BUILD_ROOT, fetch_base, prepare

__all__ = [
    "BUILD_ROOT",
    "LOCK_PATH",
    "Lock",
    "LockError",
    "SourcePin",
    "fetch_base",
    "load_lock",
    "monitored_sources",
    "prepare",
]
