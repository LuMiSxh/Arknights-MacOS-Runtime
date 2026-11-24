# SPDX-License-Identifier: MPL-2.0


import base64
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from scripts import pins
from scripts.pins import cli, mentions, resolve

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
    def test_base_without_digest_fails(self) -> None:
        routes = fixture_routes()
        del routes["/repos/dappermint/Whisky/releases"][1]["assets"][0]["digest"]

        with self.assertRaisesRegex(pins.PinError, "no sha256 digest"):
            resolve.resolve_base(make_fetch(routes))


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
        old = mentions.pins_from_lock(self.lock)
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
        only: tuple[str, ...] = resolve.COMPONENTS,
        dry_run: bool = False,
        routes: dict[str, Any] | None = None,
    ) -> cli.UpdateResult:
        return cli.run_update(
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
        return mentions.run_check(self.root, ALLOWLIST)


class UpdateTests(PinsTestCase):
    def test_update_rewrites_lock_markers_and_allowlisted_files(self) -> None:
        result = self.update()

        lock = self.lock_on_disk()
        lane = lock["lanes"]["rosetta-x86_64"]
        self.assertEqual(lane["sources"]["wine"]["commit"], NEW_WINE)
        self.assertEqual(lane["sources"]["dxmt"]["version"], "0.81-12-gbbbbbbb")
        self.assertEqual(lane["base"]["recipe"]["commit"], NEW_RECIPE)
        self.assertEqual(lock["shared"]["nixpkgs"]["commit"], NEW_NIXPKGS)
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

    def test_guard_keeps_the_old_pin_when_a_patch_fails(self) -> None:
        runner = RecordingRunner(
            failing_patch="0010-ntdll-hide-software-cursor-asset.patch"
        )

        result = self.update(runner)

        lock = self.lock_on_disk()
        lane = lock["lanes"]["rosetta-x86_64"]
        original = self.lock["lanes"]["rosetta-x86_64"]
        self.assertEqual(lane["sources"]["wine"], original["sources"]["wine"])
        self.assertEqual(lane["sources"]["dxmt"]["commit"], NEW_DXMT)
        kept = next(o for o in result.outcomes if o.component == "wine")
        self.assertEqual(kept.status, "kept")
        self.assertIn("wine-hardware-cursor-suppression", kept.reason)
        self.assertNotIn(NEW_WINE, (self.root / "notice.txt").read_text())

    def test_unresolved_base_aborts_without_writing(self) -> None:
        routes = fixture_routes()
        del routes["/repos/dappermint/winecx-gptk/git/ref/tags/runtime-v4.8.0"]
        before = snapshot(self.root)

        with self.assertRaises(pins.PinError):
            self.update(routes=routes)

        self.assertEqual(snapshot(self.root), before)

    def wine_arm64_catalog(self) -> tuple[bytes, dict[str, bytes]]:
        archives = {
            "https://c.example/v4.tar.xz": b"version four",
            "https://c.example/v6.tar.xz": b"version six",
        }
        catalog = json.dumps(
            {
                "releases": [
                    {
                        "id": "wine-11-18-arm64-v4",
                        "arch": "arm64",
                        "published_at": "2026-11-07T12:14:35Z",
                        "sha256": "1" * 64,
                        "url": "https://c.example/v4.tar.xz",
                    },
                    {
                        "id": "wine-11-18-arm64-v6",
                        "arch": "arm64",
                        "published_at": "2026-11-07T12:14:35Z",
                        "sha256": "2" * 64,
                        "url": "https://c.example/v6.tar.xz",
                    },
                    {"id": "other-x86", "arch": "x86_64", "sha256": "3" * 64},
                ]
            }
        ).encode()
        return catalog, archives

    def update_wine_arm64(
        self, catalog: bytes, archives: dict[str, bytes], release_id: str | None = None
    ) -> cli.UpdateResult:
        def fetch_archive(url: str, path: Path) -> None:
            path.write_bytes(archives[url])

        with mock.patch.dict(
            os.environ, {"ARM64_RUNTIME_CATALOG_URL": "https://c.example/"}
        ):
            return cli.run_update(
                self.root,
                ("wine-arm64",),
                dry_run=False,
                fetch=make_fetch({}),
                fetch_catalog=lambda url: catalog,
                fetch_archive=fetch_archive,
                release_id=release_id,
                allowlist=ALLOWLIST,
            )

    def test_wine_arm64_moves_to_the_newest_catalog_release(self) -> None:
        catalog, archives = self.wine_arm64_catalog()

        result = self.update_wine_arm64(catalog, archives)

        artifact = self.lock_on_disk()["lanes"]["native-arm64"]["artifact"]
        self.assertEqual(artifact["release"], "wine-11-18-arm64-v6")
        self.assertEqual(artifact["sha256"], hashlib.sha256(b"version six").hexdigest())
        self.assertEqual([o.status for o in result.outcomes], ["updated"])

    def test_wine_arm64_pins_the_named_release(self) -> None:
        catalog, archives = self.wine_arm64_catalog()

        self.update_wine_arm64(catalog, archives, release_id="wine-11-18-arm64-v4")

        artifact = self.lock_on_disk()["lanes"]["native-arm64"]["artifact"]
        self.assertEqual(artifact["release"], "wine-11-18-arm64-v4")
        self.assertEqual(
            artifact["sha256"], hashlib.sha256(b"version four").hexdigest()
        )

    def test_wine_arm64_rejects_an_unknown_release_id(self) -> None:
        catalog, archives = self.wine_arm64_catalog()
        before = snapshot(self.root)

        with self.assertRaisesRegex(pins.PinError, "no arm64 release with id"):
            self.update_wine_arm64(catalog, archives, release_id="wine-11-18-arm64-v9")

        self.assertEqual(snapshot(self.root), before)


class CheckTests(PinsTestCase):
    def test_current_state_passes(self) -> None:
        self.assertEqual(self.check(), [])

    def test_stale_marker_is_reported(self) -> None:
        current = mentions.pins_from_lock(self.lock)["wine.version"]
        self.page.write_text(self.page.read_text().replace(current, "0.0"))

        self.assertEqual(self.check(), ["docs/page.md:1: pin:wine.version is stale"])


if __name__ == "__main__":
    unittest.main()
