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

    def validate(self, index: dict, target: str = "rosetta-x86_64") -> None:
        validate_index(
            index,
            licenses_root=ROOT / "LICENSES",
            lock=LOCK,
            nix_packages=self.packages,
            target=target,
        )

    def test_component_without_entry_fails(self) -> None:
        index = copy.deepcopy(self.index)
        index["components"] = [c for c in index["components"] if c["name"] != "GnuTLS"]
        with self.assertRaisesRegex(LicenseError, "gnutls"):
            self.validate(index)

    def test_unknown_spdx_identifier_fails(self) -> None:
        index = copy.deepcopy(self.index)
        index["components"][0]["spdx"] = "Made-Up-1.0"
        with self.assertRaisesRegex(LicenseError, "unknown SPDX identifier"):
            self.validate(index)

    def test_unsafe_path_fails(self) -> None:
        index = copy.deepcopy(self.index)
        index["components"][0]["files"] = ["../README.md"]
        with self.assertRaisesRegex(LicenseError, "unsafe file path"):
            self.validate(index)

    def test_target_required_component_fails(self) -> None:
        index = copy.deepcopy(self.index)
        index["components"] = [c for c in index["components"] if c["name"] != "FEX"]
        with self.assertRaisesRegex(LicenseError, "FEX"):
            self.validate(index, target="native-arm64")


class LicenseAssemblyTests(unittest.TestCase):
    def test_target_filters_the_shipped_components(self) -> None:
        index = load_index(ROOT / "LICENSES")
        libraries = parse_inventory(INVENTORY)
        x86 = {c["name"] for c in resolve_shipped(index, libraries)["components"]}
        arm = {
            c["name"]
            for c in resolve_shipped(index, libraries, target="native-arm64")[
                "components"
            ]
        }
        self.assertIn("MoltenVK", x86)
        self.assertNotIn("FEX", x86)
        self.assertIn("FEX", arm)
        self.assertNotIn("MoltenVK", arm)

    def test_generate_writes_the_target_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "inventory.tsv"
            inventory.write_text(INVENTORY, encoding="utf-8")
            output = Path(directory) / "out"
            output.mkdir()
            generate(ROOT, output, inventory=inventory, target="native-arm64")

            archive_index = json.loads(
                (output / ARCHIVE_LICENSES_DIRECTORY / "index.json").read_text("utf-8")
            )
            names = {item["name"] for item in archive_index["components"]}
            self.assertIn("FEX", names)
            self.assertNotIn("MoltenVK", names)
            notice = (output / ARCHIVE_NOTICE).read_text(encoding="utf-8")
            self.assertIn("| FEX |", notice)
            self.assertNotIn("| MoltenVK |", notice)
            self.assertIn("- FEX:", notice)

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
