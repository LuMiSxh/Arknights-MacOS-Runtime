# SPDX-License-Identifier: MPL-2.0

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
            "Arknights-MacOS-Runtime-v0.9.0-arm64.tar.gz",
        )
        self.assertEqual(
            source_archive_name("0.9.0", "arm64"),
            "Arknights-MacOS-Runtime-v0.9.0-arm64-source.tar.gz",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            member = root / "Libraries"
            member.mkdir()
            (member / "marker").write_bytes(b"x")
            name = runtime_archive_name("0.9.0", "arm64")

            path = write_archive(root, name, [(member, "Libraries")])

            self.assertEqual(path.name, name)
            self.assertEqual(
                path.with_name(f"{name}.sha256").read_text(encoding="utf-8"),
                f"{sha256(path)}  {name}\n",
            )


if __name__ == "__main__":
    unittest.main()
