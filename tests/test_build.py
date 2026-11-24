# SPDX-License-Identifier: MPL-2.0

import os
import tempfile
import unittest
from pathlib import Path

from scripts.lanes import runtime_archive_name
from scripts.lib.artifact import write_archive


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
            name = runtime_archive_name("arm64")
            (root / "first").mkdir()
            (root / "second").mkdir()

            first = write_archive(root / "first", name, [(tree, "Runtime")])
            os.utime(tree / "data.txt", (1_000_000, 1_000_000))
            second = write_archive(root / "second", name, [(tree, "Runtime")])

            self.assertEqual(first.read_bytes(), second.read_bytes())


if __name__ == "__main__":
    unittest.main()
