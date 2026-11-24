# SPDX-License-Identifier: MPL-2.0

"""Check and rewrite every mention of a pin.

Mentions use two mechanisms:

- Markdown files hold generated markers. `<!-- pin:KEY -->text<!-- /pin -->` holds one
  value. `KEY|code` wraps the value in a code span. `<!-- pin-block:NAME -->` holds a
  generated block. Fenced code blocks and code spans with a comment are ignored.
- Other files appear in `ALLOWLIST`. `update` replaces the old value of each listed pin
  with the new one. `check` fails when a file lacks the value of the lock.
"""

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts.lock.model import DEFAULT_LANE
from scripts.pins import SHORT_LENGTH, PinError, read_lock

DESCRIBE = re.compile(r"(?P<tag>.+)-(?P<count>\d+)-g[0-9a-f]+")
DOWNLOAD_TAG = re.compile(r"/releases/download/(?P<tag>[^/]+)/")

# Files that are not Markdown. Each entry lists the pins that the file states.
ALLOWLIST: dict[str, tuple[str, ...]] = {
    "LICENSES/index.json": (
        "wine.commit",
        "dxmt.commit",
        "nixpkgs.commit",
        "wine.version",
        "dxmt.version",
    ),
    "LICENSES/notices/wine.txt": ("wine.commit", "wine.version"),
    "LICENSES/notices/wine-bundled.txt": ("wine.commit",),
    "LICENSES/notices/dxmt.txt": ("dxmt.commit", "dxmt.version", "dxmt.build"),
    "LICENSES/notices/dxmt-toolchain.txt": ("dxmt.commit", "dxmt.version"),
    "LICENSES/notices/dxmt-headers.txt": ("dxmt.commit", "dxmt.version"),
    "LICENSES/notices/dxmt-vendored.txt": ("dxmt.commit", "dxmt.version"),
}
SKIPPED_DIRECTORIES = frozenset((".git", ".venv", ".build", "node_modules"))

# Documentation may show marker syntax in a fenced block or in a code span.
FENCE = re.compile(r"^(```|~~~).*?^\1[^\n]*$|`[^`\n]*`", re.MULTILINE | re.DOTALL)
INLINE_MARKER = re.compile(
    r"<!-- pin:(?P<key>[\w.]+)(?:\|(?P<format>code))? -->(?P<body>.*?)<!-- /pin -->"
)
BLOCK_MARKER = re.compile(
    r"<!-- pin-block:(?P<name>[\w-]+) -->\n(?P<body>.*?)<!-- /pin-block -->",
    re.DOTALL,
)


def _slug(repository: str) -> str:
    return repository.removeprefix("https://github.com/").removesuffix(".git")


def _link(repository: str, commit: str) -> str:
    slug = _slug(repository)
    short = commit[:SHORT_LENGTH]
    return f"[`{slug}@{short}`](https://github.com/{slug}/tree/{commit})"


def pins_from_lock(lock: dict[str, Any]) -> dict[str, str]:
    """Derive every pin key that a marker or an allowlisted file may name."""

    pins: dict[str, str] = {}
    lane = lock["lanes"][DEFAULT_LANE]
    for name in ("wine", "dxmt"):
        source = lane["sources"][name]
        pins[f"{name}.commit"] = source["commit"]
        pins[f"{name}.short"] = source["commit"][:SHORT_LENGTH]
        pins[f"{name}.version"] = source["version"]
        pins[f"{name}.link"] = _link(source["repository"], source["commit"])
    describe = DESCRIBE.fullmatch(pins["dxmt.version"])
    pins["dxmt.tag"] = describe["tag"] if describe else pins["dxmt.version"]
    pins["dxmt.build"] = (
        f"{describe['tag']}-{describe['count']}" if describe else pins["dxmt.version"]
    )
    pins["dxmt.describe"] = "v" + pins["dxmt.version"]
    artifact = lane["base"]
    release = DOWNLOAD_TAG.search(artifact["url"])
    if release is None:
        raise PinError(f"cannot read the release tag from {artifact['url']}")
    pins["base.tag"] = release["tag"]
    pins["base.version"] = release["tag"].removeprefix("v")
    pins["base.url"] = artifact["url"]
    pins["base.sha256"] = artifact["sha256"]
    pins["base.recipe"] = artifact["recipe"]["commit"]
    pins["base.recipeShort"] = artifact["recipe"]["commit"][:SHORT_LENGTH]
    nixpkgs = lock["shared"]["nixpkgs"]
    pins["nixpkgs.commit"] = nixpkgs["commit"]
    pins["nixpkgs.short"] = nixpkgs["commit"][:SHORT_LENGTH]
    pins["nixpkgs.link"] = _link(nixpkgs["repository"], nixpkgs["commit"])
    return pins


def render_table(pins: dict[str, str]) -> str:
    rows = ["| Pin | Value |", "| --- | --- |"]
    rows += [f"| `{key}` | `{pins[key]}` |" for key in PIN_TABLE_KEYS]
    return "\n".join(rows) + "\n"


PIN_TABLE_KEYS = (
    "wine.commit",
    "wine.version",
    "dxmt.commit",
    "dxmt.version",
    "base.tag",
    "base.url",
    "base.sha256",
    "base.recipe",
    "nixpkgs.commit",
)
BLOCKS: dict[str, Callable[[dict[str, str]], str]] = {"table": render_table}


# --- Mentions ---------------------------------------------------------------------


def _rewrite_segment(
    text: str, start: int, end: int, pins: dict[str, str], name: str, stale: list[str]
) -> str:
    segment = text[start:end]

    def line_of(offset: int) -> int:
        return text.count("\n", 0, start + offset) + 1

    def inline(match: re.Match[str]) -> str:
        key = match["key"]
        if key not in pins:
            raise PinError(f"{name}:{line_of(match.start())}: unknown pin key '{key}'")
        value = f"`{pins[key]}`" if match["format"] else pins[key]
        if match["body"] != value:
            stale.append(f"{name}:{line_of(match.start())}: pin:{key} is stale")
        return f"<!-- pin:{key}{'|code' if match['format'] else ''} -->{value}<!-- /pin -->"

    def block(match: re.Match[str]) -> str:
        key = match["name"]
        if key not in BLOCKS:
            raise PinError(
                f"{name}:{line_of(match.start())}: unknown pin block '{key}'"
            )
        value = BLOCKS[key](pins)
        if match["body"] != value:
            stale.append(f"{name}:{line_of(match.start())}: pin-block:{key} is stale")
        return f"<!-- pin-block:{key} -->\n{value}<!-- /pin-block -->"

    segment = INLINE_MARKER.sub(inline, segment)
    segment = BLOCK_MARKER.sub(block, segment)
    openers = len(re.findall(r"<!-- pin(?:-block)?:", segment))
    closers = len(re.findall(r"<!-- /pin(?:-block)? -->", segment))
    matched = len(INLINE_MARKER.findall(segment)) + len(BLOCK_MARKER.findall(segment))
    if openers != matched or closers != matched:
        raise PinError(f"{name}: unbalanced or malformed pin marker")
    return segment


def rewrite_markdown(
    text: str, pins: dict[str, str], name: str, stale: list[str]
) -> str:
    """Return the text with every marker regenerated. Fenced code blocks stay as is."""

    parts: list[str] = []
    cursor = 0
    for fence in FENCE.finditer(text):
        span = fence[0]
        if not span.startswith(("```", "~~~")) and "<!--" not in span:
            continue
        parts.append(_rewrite_segment(text, cursor, fence.start(), pins, name, stale))
        parts.append(fence.group())
        cursor = fence.end()
    parts.append(_rewrite_segment(text, cursor, len(text), pins, name, stale))
    return "".join(parts)


def _token(value: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\w.-])" + re.escape(value) + r"(?![\w-]|\.\d)")


def rewrite_allowlisted(
    text: str,
    keys: tuple[str, ...],
    old: dict[str, str],
    new: dict[str, str],
    name: str,
) -> str:
    """Replace the old value of each listed pin. Fail when the new value is missing."""

    for key in keys:
        if old[key] != new[key]:
            text = _token(old[key]).sub(new[key].replace("\\", r"\\"), text)
        if _token(new[key]).search(text) is None:
            raise PinError(f"{name}: lacks the value of {key} ({new[key]})")
    return text


def markdown_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.md")
        if not SKIPPED_DIRECTORIES.intersection(path.relative_to(root).parts)
    )


def plan_rewrites(
    root: Path,
    old: dict[str, str],
    new: dict[str, str],
    allowlist: dict[str, tuple[str, ...]],
) -> tuple[dict[Path, str], list[str]]:
    """Return the new text of every changed mention and the list of stale markers."""

    changes: dict[Path, str] = {}
    stale: list[str] = []
    for path in markdown_files(root):
        text = path.read_text(encoding="utf-8")
        rewritten = rewrite_markdown(
            text, new, path.relative_to(root).as_posix(), stale
        )
        if rewritten != text:
            changes[path] = rewritten
    for relative, keys in allowlist.items():
        path = root / relative
        if not path.is_file():
            raise PinError(f"{relative}: allowlisted file is missing")
        text = path.read_text(encoding="utf-8")
        rewritten = rewrite_allowlisted(text, keys, old, new, relative)
        if rewritten != text:
            changes[path] = rewritten
    return changes, stale


def run_check(
    root: Path, allowlist: dict[str, tuple[str, ...]] = ALLOWLIST
) -> list[str]:
    """Return one line per mention that disagrees with the lock."""

    pins = pins_from_lock(read_lock(root))
    problems: list[str] = []
    for path in markdown_files(root):
        rewrite_markdown(
            path.read_text(encoding="utf-8"),
            pins,
            path.relative_to(root).as_posix(),
            problems,
        )
    for relative, keys in allowlist.items():
        path = root / relative
        if not path.is_file():
            problems.append(f"{relative}: allowlisted file is missing")
            continue
        text = path.read_text(encoding="utf-8")
        problems += [
            f"{relative}: lacks the value of {key} ({pins[key]})"
            for key in keys
            if _token(pins[key]).search(text) is None
        ]
    return problems
