# SPDX-License-Identifier: MPL-2.0

"""Update the upstream pins of the runtime and every mention of them.

`resolve` finds the newest upstream state and writes it into the lock. `mentions`
checks and rewrites each mention of a pin. `cli` holds the commands:
`-m scripts pins update|check|export`.
"""

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LOCK_NAME = "runtime.lock.json"
SHORT_LENGTH = 7


class PinError(RuntimeError):
    """A pin cannot be resolved, rewritten, or verified."""


def read_lock(root: Path) -> dict[str, Any]:
    try:
        return json.loads((root / LOCK_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as failure:
        raise PinError(f"cannot read {LOCK_NAME}: {failure}") from failure
