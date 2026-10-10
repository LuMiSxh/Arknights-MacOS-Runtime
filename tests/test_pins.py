# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from scripts.release import pins

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
NEW_WINE = "a" * 40
NEW_DXMT = "b" * 40
NEW_NIXPKGS = "c" * 40
NEW_RECIPE = "d" * 40
NEW_DIGEST = "e" * 64
ALLOWLIST = {"notice.txt": ("wine.commit", "wine.version", "dxmt.build")}
RELEASE_URL = (
    "https://github.com/dappermint/Whisky/releases/download/v4.8.0/Libraries.tar.gz"
)


def branch(name: str, sha: str) -> dict[str, Any]:
    return {"name": name, "commit": {"sha": sha}}


def fixture_routes() -> dict[str, Any]:
    return {
        "/repos/dappermint/winecx/branches": [
            branch("main", "1" * 40),
            branch("wine1118", "2" * 40),
            branch("wine1119", NEW_WINE),
            branch("wine119", "3" * 40),
            branch("wine1200", "4" * 40),
        ],
        f"/repos/dappermint/winecx/contents/VERSION?ref={NEW_WINE}": {
            "content": base64.b64encode(b"Wine version 11.19\n").decode()
        },
        "/repos/3Shain/dxmt": {"default_branch": "main"},
        "/repos/3Shain/dxmt/git/ref/heads/main": {"object": {"sha": NEW_DXMT}},
        "/repos/3Shain/dxmt/tags": [
            {"name": "v0.79"},
            {"name": "v0.81"},
            {"name": "nightly"},
        ],
        f"/repos/3Shain/dxmt/compare/v0.81...{NEW_DXMT}": {
            "status": "ahead",
            "ahead_by": 12,
        },
        "/repos/dappermint/Whisky/releases": [
            {"tag_name": "v4.9.0", "draft": False, "assets": [{"name": "Other.zip"}]},
            {
                "tag_name": "v4.8.0",
                "draft": False,
                "assets": [
                    {
                        "name": "Libraries.tar.gz",
                        "digest": f"sha256:{NEW_DIGEST}",
                        "browser_download_url": RELEASE_URL,
                    }
                ],
            },
        ],
        "/repos/dappermint/winecx-gptk/git/ref/tags/runtime-v4.8.0": {
            "object": {"type": "tag", "sha": "9" * 40}
        },
        "/repos/dappermint/winecx-gptk/git/tags/" + "9" * 40: {
            "object": {"sha": NEW_RECIPE}
        },
        "/repos/NixOS/nixpkgs/git/ref/heads/nixos-25.05": {
            "object": {"sha": NEW_NIXPKGS}
        },
    }


def make_fetch(routes: dict[str, Any]):
    def fetch(path: str) -> Any:
        base, _, query = path.partition("?")
        if "page=" in query and "page=1" not in query:
            return []
        for candidate in (path, base):
            if candidate in routes:
                return routes[candidate]
        raise pins.PinError(f"unexpected request: {path}")

    return fetch


class RecordingRunner:
    def __init__(self, failing_patch: str | None = None) -> None:
        self.failing_patch = failing_patch
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str]) -> tuple[int, str]:
        self.commands.append(command)
        if self.failing_patch and command[-1].endswith(self.failing_patch):
            return 1, "error: patch failed: file.c:10"
        return 0, ""


def snapshot(root: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}


class ResolutionTests(unittest.TestCase):
    def test_wine_uses_the_highest_numbered_branch_and_its_version_file(self) -> None:
        state = pins.resolve_wine(make_fetch(fixture_routes()))

        self.assertEqual(state, pins.WineState(NEW_WINE, "11.19"))

    def test_dxmt_version_follows_the_describe_format(self) -> None:
        state = pins.resolve_dxmt(make_fetch(fixture_routes()))

        self.assertEqual(state, pins.DxmtState(NEW_DXMT, "0.81-12-gbbbbbbb"))

    def test_dxmt_on_a_tag_has_no_count(self) -> None:
        routes = fixture_routes()
        routes[f"/repos/3Shain/dxmt/compare/v0.81...{NEW_DXMT}"] = {
            "status": "identical",
            "ahead_by": 0,
        }

        self.assertEqual(pins.resolve_dxmt(make_fetch(routes)).version, "0.81")

    def test_base_reads_digest_and_dereferences_the_recipe_tag(self) -> None:
        state = pins.resolve_base(make_fetch(fixture_routes()))

        self.assertEqual(state, pins.BaseState(RELEASE_URL, NEW_DIGEST, NEW_RECIPE))

    def test_base_without_digest_fails(self) -> None:
        routes = fixture_routes()
        del routes["/repos/dappermint/Whisky/releases"][1]["assets"][0]["digest"]

        with self.assertRaisesRegex(pins.PinError, "no sha256 digest"):
            pins.resolve_base(make_fetch(routes))

    def test_nixpkgs_uses_the_configured_channel(self) -> None:
        state = pins.resolve_nixpkgs(make_fetch(fixture_routes()))

        self.assertEqual(state.commit, NEW_NIXPKGS)
        self.assertEqual(pins.NIXPKGS_CHANNEL, "nixos-25.05")


class PinsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.lock = json.loads(
            (REPOSITORY_ROOT / "runtime.lock.json").read_text("utf-8")
        )
        (self.root / "runtime.lock.json").write_text(
            json.dumps(self.lock, indent=2) + "\n"
        )
        old = pins.pins_from_lock(self.lock)
        (self.root / "notice.txt").write_text(
            f"Wine {old['wine.version']} at {old['wine.commit']}\n"
            f"Pinned build {old['dxmt.build']} is not release {old['dxmt.tag']}.\n"
        )
        (self.root / "docs").mkdir()
        self.page = self.root / "docs" / "page.md"
        self.page.write_text(
            f"Wine <!-- pin:wine.version -->{old['wine.version']}<!-- /pin -->\n"
            f"<!-- pin:dxmt.commit|code -->`{old['dxmt.commit']}`<!-- /pin -->\n"
        )

    def update(
        self,
        runner: RecordingRunner | None = None,
        *,
        only: tuple[str, ...] = pins.COMPONENTS,
        dry_run: bool = False,
        routes: dict[str, Any] | None = None,
    ) -> pins.UpdateResult:
        return pins.run_update(
            self.root,
            only,
            dry_run=dry_run,
            fetch=make_fetch(routes or fixture_routes()),
            run=runner or RecordingRunner(),
            allowlist=ALLOWLIST,
        )

    def lock_on_disk(self) -> dict[str, Any]:
        return json.loads((self.root / "runtime.lock.json").read_text("utf-8"))

    def check(self) -> list[str]:
        return pins.run_check(self.root, ALLOWLIST)


class UpdateTests(PinsTestCase):
    def test_update_rewrites_lock_markers_and_allowlisted_files(self) -> None:
        result = self.update()

        lock = self.lock_on_disk()
        self.assertEqual(lock["sources"]["wine"]["commit"], NEW_WINE)
        self.assertEqual(lock["sources"]["dxmt"]["version"], "0.81-12-gbbbbbbb")
        self.assertEqual(lock["baseArtifact"]["recipe"]["commit"], NEW_RECIPE)
        self.assertEqual(lock["build"]["nixpkgs"]["commit"], NEW_NIXPKGS)
        self.assertEqual(
            (self.root / "notice.txt").read_text(),
            f"Wine 11.19 at {NEW_WINE}\nPinned build 0.81-12 is not release 0.80.\n",
        )
        self.assertIn(
            "<!-- pin:wine.version -->11.19<!-- /pin -->", self.page.read_text()
        )
        self.assertIn(f"`{NEW_DXMT}`", self.page.read_text())
        self.assertEqual({o.status for o in result.outcomes}, {"updated"})
        self.assertEqual(self.check(), [])

    def test_dry_run_writes_nothing(self) -> None:
        before = snapshot(self.root)

        result = self.update(dry_run=True)

        self.assertEqual(snapshot(self.root), before)
        self.assertIn("runtime.lock.json", result.written)
        self.assertIn("notice.txt", result.written)

    def test_update_is_idempotent(self) -> None:
        self.update()
        before = snapshot(self.root)

        result = self.update()

        self.assertEqual(result.written, [])
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual({o.status for o in result.outcomes}, {"current"})

    def test_lock_serialization_matches_the_repository_format(self) -> None:
        text = (REPOSITORY_ROOT / "runtime.lock.json").read_text("utf-8")

        self.assertEqual(json.dumps(json.loads(text), indent=2) + "\n", text)

    def test_only_limits_the_components(self) -> None:
        self.update(only=("nixpkgs",))

        lock = self.lock_on_disk()
        self.assertEqual(lock["build"]["nixpkgs"]["commit"], NEW_NIXPKGS)
        self.assertEqual(lock["sources"], self.lock["sources"])

    def test_guard_keeps_the_old_pin_when_a_patch_fails(self) -> None:
        runner = RecordingRunner(
            failing_patch="0001-ntdll-hide-software-cursor-asset.patch"
        )

        result = self.update(runner)

        lock = self.lock_on_disk()
        self.assertEqual(lock["sources"]["wine"], self.lock["sources"]["wine"])
        self.assertEqual(lock["sources"]["dxmt"]["commit"], NEW_DXMT)
        kept = next(o for o in result.outcomes if o.component == "wine")
        self.assertEqual(kept.status, "kept")
        self.assertIn("wine-hardware-cursor-suppression", kept.reason)
        self.assertNotIn(NEW_WINE, (self.root / "notice.txt").read_text())

    def test_guard_applies_dxmt_patches_in_lock_order(self) -> None:
        runner = RecordingRunner()

        self.update(runner, only=("dxmt",))

        applied = [
            Path(command[-1]).name
            for command in runner.commands
            if "apply" in command and "--check" not in command
        ]
        expected = [
            Path(p["path"]).name
            for p in self.lock["patches"]
            if p["component"] == "dxmt"
        ]
        self.assertEqual(applied, expected)

    def test_unresolved_base_aborts_without_writing(self) -> None:
        routes = fixture_routes()
        del routes["/repos/dappermint/winecx-gptk/git/ref/tags/runtime-v4.8.0"]
        before = snapshot(self.root)

        with self.assertRaises(pins.PinError):
            self.update(routes=routes)

        self.assertEqual(snapshot(self.root), before)


class CheckTests(PinsTestCase):
    def test_current_state_passes(self) -> None:
        self.assertEqual(self.check(), [])

    def test_stale_marker_is_reported(self) -> None:
        self.page.write_text(self.page.read_text().replace("11.17", "11.16"))

        self.assertEqual(self.check(), ["docs/page.md:1: pin:wine.version is stale"])

    def test_missing_token_is_reported(self) -> None:
        (self.root / "notice.txt").write_text("Nothing here\n")

        problems = self.check()

        self.assertEqual(len(problems), 3)
        self.assertTrue(
            all(p.startswith("notice.txt: lacks the value of") for p in problems)
        )

    def test_update_fails_on_a_missing_token(self) -> None:
        (self.root / "notice.txt").write_text("Nothing here\n")

        with self.assertRaisesRegex(pins.PinError, "lacks the value"):
            self.update()

    def test_unknown_key_fails(self) -> None:
        self.page.write_text("<!-- pin:wine.nope -->x<!-- /pin -->\n")

        with self.assertRaisesRegex(pins.PinError, "unknown pin key 'wine.nope'"):
            self.check()

    def test_unbalanced_marker_fails(self) -> None:
        self.page.write_text("<!-- pin:wine.version -->11.17\n")

        with self.assertRaisesRegex(pins.PinError, "unbalanced"):
            self.check()

    def test_documented_markers_in_code_are_ignored(self) -> None:
        self.page.write_text(
            "Write `<!-- pin:nope -->x<!-- /pin -->` like this.\n"
            "```\n<!-- pin:nope -->x<!-- /pin -->\n```\n"
        )

        self.assertEqual(self.check(), [])

    def test_table_block_is_regenerated_by_update(self) -> None:
        self.page.write_text("<!-- pin-block:table -->\nold\n<!-- /pin-block -->\n")

        self.assertEqual(self.check(), ["docs/page.md:1: pin-block:table is stale"])
        self.update()
        self.assertIn(NEW_WINE, self.page.read_text())


class RepositoryTests(unittest.TestCase):
    def test_repository_mentions_agree_with_the_lock(self) -> None:
        self.assertEqual(pins.run_check(REPOSITORY_ROOT), [])


if __name__ == "__main__":
    unittest.main()
