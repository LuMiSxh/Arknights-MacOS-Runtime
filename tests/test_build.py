# SPDX-License-Identifier: MPL-2.0

import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import build_common as build_helpers
from scripts.build_common import (
    CLEARED_DOS_STUB,
    Builder,
    is_macho,
    sha256,
    write_archive,
)


class BuildHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_archive_carries_the_member_and_a_shasum_compatible_checksum(self) -> None:
        directory = self.root / "candidate"
        member = directory / "Libraries"
        member.mkdir(parents=True)
        (member / "Wine").write_bytes(b"payload")

        path = write_archive(directory, "runtime.tar.gz", ("Libraries",))

        with tarfile.open(path) as archive:
            self.assertEqual(archive.getnames()[0], "Libraries")
        checksum = path.with_name(f"{path.name}.sha256").read_text(encoding="utf-8")
        self.assertEqual(checksum, f"{sha256(path)}  runtime.tar.gz\n")

    def test_archive_round_trips_nested_files(self) -> None:
        member = self.root / "Libraries" / "Wine" / "bin"
        member.mkdir(parents=True)
        (member / "wine64").write_bytes(b"x")
        path = write_archive(self.root, "runtime.tar.gz", ("Libraries",))

        with tarfile.open(path) as archive:
            extracted = archive.extractfile("Libraries/Wine/bin/wine64")
            self.assertIsNotNone(extracted)
            self.assertEqual(extracted.read(), b"x")

    def test_archive_reads_members_from_another_content_root(self) -> None:
        content = self.root / "candidate"
        member = content / "Libraries" / "Wine"
        member.mkdir(parents=True)
        (member / "wine64").write_bytes(b"x")
        self.root.mkdir(exist_ok=True)

        path = write_archive(
            self.root, "runtime.tar.gz", ("Libraries",), content_root=content
        )

        self.assertEqual(path.parent, self.root)
        with tarfile.open(path) as archive:
            self.assertEqual(archive.getnames()[0], "Libraries")

    def test_is_macho_reads_the_thin_magic(self) -> None:
        macho = self.root / "loader"
        macho.write_bytes(b"\xcf\xfa\xed\xfe" + bytes(60))
        self.assertTrue(is_macho(macho))

        script = self.root / "loader.sh"
        script.write_bytes(b"#!/bin/sh\n")
        self.assertFalse(is_macho(script))
        self.assertFalse(is_macho(self.root / "missing"))

    def test_dos_stub_marker_has_the_documented_length(self) -> None:
        self.assertEqual(len(CLEARED_DOS_STUB), 16)
        self.assertEqual(CLEARED_DOS_STUB[:2], b"\x0e\x1f")

    def test_pe_cross_builds_drop_host_compiler_variables(self) -> None:
        builder = Builder(
            environment={
                "PATH": "/usr/bin",
                "CFLAGS": "-O2",
                "CC": "ccache clang",
                "SDKROOT": "/sdk",
                "MACOSX_DEPLOYMENT_TARGET": "15.0",
                "KEPT": "1",
            }
        )

        environment = builder.without_host_build_variables()

        self.assertNotIn("CFLAGS", environment)
        self.assertNotIn("CC", environment)
        self.assertNotIn("SDKROOT", environment)
        self.assertNotIn("MACOSX_DEPLOYMENT_TARGET", environment)
        self.assertEqual(environment["KEPT"], "1")
        self.assertEqual(builder.environment["CFLAGS"], "-O2")

    def test_builder_uses_the_default_nix_profile_when_path_lacks_nix(self) -> None:
        nix_directory = self.root / "nix-bin"
        nix_directory.mkdir()
        (nix_directory / "nix").touch()

        with mock.patch.object(build_helpers, "NIX_DEFAULT_BIN", nix_directory):
            builder = Builder(environment={"PATH": "/usr/bin"})

        self.assertEqual(builder.environment["PATH"], f"{nix_directory}:/usr/bin")

    def test_sha256_reads_a_file_incrementally(self) -> None:
        path = self.root / "payload"
        path.write_bytes(b"abc")
        self.assertEqual(
            sha256(path),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )

    def test_archive_name_matches_the_release_convention(self) -> None:
        member = self.root / "Libraries"
        member.mkdir()
        (member / "marker").write_bytes(b"x")
        path = write_archive(
            self.root,
            "Arknights-MacOS-Runtime-arm64-canary.tar.gz",
            ("Libraries",),
        )

        with io.BytesIO(path.read_bytes()) as buffer, tarfile.open(fileobj=buffer):
            pass


if __name__ == "__main__":
    unittest.main()
