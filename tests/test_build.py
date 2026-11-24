# SPDX-License-Identifier: MPL-2.0

import os
import tempfile
import unittest
from pathlib import Path

from scripts.lib.artifact import sha256, write_archive
from scripts.targets import runtime_archive_name, source_archive_name


class ArchiveNameTests(unittest.TestCase):
    def test_artifact_names_and_shasum_checksums_follow_the_release_convention(
        self,
    ) -> None:
        self.assertEqual(
            runtime_archive_name("0.9.0", "arm64"),
            "Arknights-MacOS-Runtime-v0.9.0-arm64.tar.xz",
        )
        self.assertEqual(
            source_archive_name("0.9.0", "arm64"),
            "Arknights-MacOS-Runtime-v0.9.0-arm64-source.tar.xz",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            member = root / "Runtime"
            member.mkdir()
            (member / "marker").write_bytes(b"x")
            name = runtime_archive_name("0.9.0", "arm64")

            path = write_archive(root, name, [(member, "Runtime")])

            self.assertEqual(path.name, name)
            self.assertEqual(
                path.with_name(f"{name}.sha256").read_text(encoding="utf-8"),
                f"{sha256(path)}  {name}\n",
            )


class ArchiveDeterminismTests(unittest.TestCase):
    def test_writing_the_same_tree_twice_yields_identical_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tree = root / "Runtime"
            (tree / "bin").mkdir(parents=True)
            (tree / "bin" / "tool").write_bytes(b"tool")
            os.chmod(tree / "bin" / "tool", 0o755)
            (tree / "data.txt").write_bytes(b"data")
            os.symlink("tool", tree / "bin" / "link")
            name = runtime_archive_name("0.9.0", "arm64")
            (root / "first").mkdir()
            (root / "second").mkdir()

            first = write_archive(root / "first", name, [(tree, "Runtime")])
            os.utime(tree / "data.txt", (1_000_000, 1_000_000))
            second = write_archive(root / "second", name, [(tree, "Runtime")])

            self.assertEqual(first.read_bytes(), second.read_bytes())


if __name__ == "__main__":
    unittest.main()
