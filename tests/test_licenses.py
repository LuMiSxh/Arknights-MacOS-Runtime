# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.release.licenses import (
    ARCHIVE_LICENSES_DIRECTORY,
    ARCHIVE_NOTICE,
    BUILD_SCRIPT,
    LicenseError,
    direct_nix_packages,
    generate,
    load_index,
    parse_inventory,
    resolve_shipped,
    spdx_identifiers,
    validate_index,
)

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / "runtime.lock.json").read_text(encoding="utf-8"))
INVENTORY = (
    "component\trole\tsource\n"
    "WineCX/Wine\tWindows compatibility runtime\tlock\n"
    "abc-freetype-2.13.3-bin\tBundled Nix library\tx\n".replace("abc", "a" * 32)
    + "{}-gnutls-3.8.9\tBundled Nix library\tx\n".format("b" * 32)
)


class LicenseIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = load_index(ROOT / "LICENSES")
        self.packages = direct_nix_packages(ROOT / BUILD_SCRIPT)

    def validate(self, index: dict) -> None:
        validate_index(
            index,
            licenses_root=ROOT / "LICENSES",
            lock=LOCK,
            nix_packages=self.packages,
        )

    def test_repository_index_is_valid(self) -> None:
        self.validate(self.index)

    def test_component_without_entry_fails(self) -> None:
        index = copy.deepcopy(self.index)
        index["components"] = [c for c in index["components"] if c["name"] != "GnuTLS"]
        with self.assertRaisesRegex(LicenseError, "gnutls"):
            self.validate(index)

    def test_missing_file_fails(self) -> None:
        index = copy.deepcopy(self.index)
        index["components"][0]["files"].append("runtime/Missing.txt")
        with self.assertRaisesRegex(LicenseError, "Missing.txt"):
            self.validate(index)

    def test_unknown_spdx_identifier_fails(self) -> None:
        index = copy.deepcopy(self.index)
        index["components"][0]["spdx"] = "Made-Up-1.0"
        with self.assertRaisesRegex(LicenseError, "unknown SPDX identifier"):
            self.validate(index)

    def test_unknown_status_fails(self) -> None:
        index = copy.deepcopy(self.index)
        index["components"][0]["status"] = "declared"
        with self.assertRaisesRegex(LicenseError, "unknown status"):
            self.validate(index)

    def test_unsafe_path_fails(self) -> None:
        index = copy.deepcopy(self.index)
        index["components"][0]["files"] = ["../README.md"]
        with self.assertRaisesRegex(LicenseError, "unsafe file path"):
            self.validate(index)

    def test_every_status_is_verified_or_unverified(self) -> None:
        statuses = {c["status"] for c in self.index["components"]}
        self.assertLessEqual(statuses, {"verified", "unverified"})

    def test_spdx_expression_parsing(self) -> None:
        self.assertEqual(
            spdx_identifiers("Apache-2.0 WITH LLVM-exception"),
            {"Apache-2.0", "LLVM-exception"},
        )
        with self.assertRaises(LicenseError):
            spdx_identifiers("MIT; rm -rf")


class LicenseAssemblyTests(unittest.TestCase):
    def test_inventory_resolves_realised_versions(self) -> None:
        index = load_index(ROOT / "LICENSES")
        shipped = resolve_shipped(index, parse_inventory(INVENTORY))
        names = {c["name"]: c for c in shipped["components"]}
        self.assertEqual(names["FreeType"]["version"], "2.13.3")
        self.assertEqual(names["GnuTLS"]["version"], "3.8.9")
        self.assertNotIn("zlib", names)

    def test_unknown_inventory_library_fails(self) -> None:
        text = INVENTORY + "{}-mystery-1.0\tBundled Nix library\tx\n".format("c" * 32)
        with self.assertRaisesRegex(LicenseError, "mystery"):
            resolve_shipped(load_index(ROOT / "LICENSES"), parse_inventory(text))

    def test_generate_writes_licenses_and_notice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "inventory.tsv"
            inventory.write_text(INVENTORY, encoding="utf-8")
            output = Path(directory) / "out"
            output.mkdir()
            generate(ROOT, output, inventory=inventory)

            archive_index = json.loads(
                (output / ARCHIVE_LICENSES_DIRECTORY / "index.json").read_text("utf-8")
            )
            for item in archive_index["components"]:
                for relative in (*item["files"], *filter(None, [item.get("notice")])):
                    self.assertTrue(
                        (output / ARCHIVE_LICENSES_DIRECTORY / relative).is_file()
                    )
            notice = (output / ARCHIVE_NOTICE).read_text(encoding="utf-8")
            self.assertIn("| Wine |", notice)
            self.assertIn("| GnuTLS | 3.8.9 |", notice)
            self.assertNotIn("| zlib |", notice)
            with self.assertRaisesRegex(LicenseError, "already exists"):
                generate(ROOT, output, inventory=inventory)


if __name__ == "__main__":
    unittest.main()
