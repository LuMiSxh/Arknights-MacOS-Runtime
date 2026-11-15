# SPDX-License-Identifier: MPL-2.0

"""Unified colored, unicode-aware terminal output for repository scripts.

Status lines (`info`/`success`/`warning`/`error`) always print immediately. `progress` is for
byte-counted work with a known or unknown total, like a download.

All output goes to stderr, so scripts that print a result to stdout (paths, values) stay
pipeable.
"""

import os
import sys
import time

_IS_TTY = sys.stderr.isatty()
USE_COLOR = _IS_TTY and os.environ.get("NO_COLOR") is None
USE_UNICODE = "UTF" in (sys.stderr.encoding or "").upper()
USE_ANIMATION = _IS_TTY and os.environ.get("CI") is None

_SYMBOLS = {
    "info": ("→", "->"),
    "child": ("↳", "->"),
    "success": ("✓", "OK"),
    "warning": ("!", "!!"),
    "error": ("✗", "XX"),
}
_CODES = {
    "info": "36;1",
    "child": "90",
    "success": "32;1",
    "warning": "33;1",
    "error": "31;1",
}

_BAR_FULL = "█" if USE_UNICODE else "#"
_BAR_EMPTY = "░" if USE_UNICODE else "-"
_CLEAR_LINE = "\033[K"


def _symbol(kind: str) -> str:
    return _SYMBOLS[kind][0 if USE_UNICODE else 1]


def styled(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def _line(kind: str, message: str) -> None:
    print(f"{styled(_symbol(kind), _CODES[kind])} {message}", file=sys.stderr)


def info(message: str) -> None:
    _line("info", message)


def success(message: str) -> None:
    _line("success", message)


def warning(message: str) -> None:
    _line("warning", message)


def error(message: str) -> None:
    _line("error", message)


class Progress:
    """Byte-counted progress for a single operation, animated on a TTY and reduced to
    periodic plain lines otherwise (CI logs, redirected output)."""

    def __init__(self, message: str, total: int) -> None:
        self.message = message
        self.total = total
        self._last_render = 0.0
        self._next_report = 0.1
        if not USE_ANIMATION:
            info(message)

    def update(self, current: int) -> None:
        if USE_ANIMATION:
            now = time.monotonic()
            if now - self._last_render < 0.08:
                return
            self._last_render = now
            self._render(current)
        elif self.total and current / self.total >= self._next_report:
            percentage = min(current / self.total * 100, 100)
            info(f"{self.message}: {percentage:.0f}% ({current / 1_048_576:,.0f} MiB)")
            self._next_report += 0.1

    def _render(self, current: int) -> None:
        import shutil

        columns = shutil.get_terminal_size((80, 24)).columns

        bar_width = 16
        mib = f"{current / 1_048_576:,.0f} MiB"
        if self.total:
            fraction = min(current / self.total, 1.0)
            filled = int(bar_width * fraction)
            bar = _BAR_FULL * filled + _BAR_EMPTY * (bar_width - filled)
            percent = f"{fraction * 100:5.1f}%"
            stats = f"{percent}  {mib}"

            available_msg = max(columns - bar_width - len(stats) - 6, 8)
            msg = (
                self.message
                if len(self.message) <= available_msg
                else self.message[: available_msg - 1] + "…"
            )
            text = f"{styled(bar, _CODES['info'])} {stats}  {msg}"
        else:
            text = f"{mib}  {self.message}"
        print(f"\r{text}{_CLEAR_LINE}", end="", file=sys.stderr, flush=True)

    def finish(self) -> None:
        if USE_ANIMATION:
            print(file=sys.stderr)
