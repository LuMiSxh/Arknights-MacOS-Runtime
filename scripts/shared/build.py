#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Shared helpers for every runtime build lane."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

if __package__:
    from .lib.console import info
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from lib.console import info


ROOT = Path(__file__).resolve().parents[1]


RUNTIME_CLI = ROOT / "scripts" / "shared" / "runtime.py"


VALIDATE_CLI = ROOT / "scripts" / "shared" / "validate_runtime.py"


LICENSE_CLI = ROOT / "scripts" / "shared" / "release" / "licenses.py"


TOOLCHAIN_CLI = ROOT / "scripts" / "shared" / "release" / "toolchain.py"


ARCHIVE_BUNDLED_LIBRARIES = ("libfreetype.6.dylib", "libgnutls.30.dylib")


MACHO_MAGIC = (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe")


CLEARED_DOS_STUB = bytes.fromhex("0e1fba0e00b409cd21b8014ccd219090")


LOADER_SDK_VERSION = "12.0"


HOST_BUILD_VARIABLES = (
    "CFLAGS",
    "CXXFLAGS",
    "CPPFLAGS",
    "LDFLAGS",
    "OBJCFLAGS",
    "CC",
    "CXX",
    "OBJC",
    "SDKROOT",
    "MACOSX_DEPLOYMENT_TARGET",
)


NIX_STORE = "/nix/store/"


class BuildError(RuntimeError):
    """The build cannot continue."""


@dataclass
class Builder:
    """Run build commands with one explicit environment."""

    environment: dict[str, str] = field(default_factory=lambda: dict(os.environ))

    def run(
        self,
        *command: object,
        cwd: Path | None = None,
        environment: dict[str, str] | None = None,
    ) -> None:
        info("$ " + " ".join(str(part) for part in command))
        subprocess.run(
            [str(part) for part in command],
            cwd=cwd,
            env=environment if environment is not None else self.environment,
            check=True,
        )

    def capture(
        self,
        *command: object,
        cwd: Path | None = None,
        environment: dict[str, str] | None = None,
        allow_failure: bool = False,
    ) -> str:
        result = subprocess.run(
            [str(part) for part in command],
            cwd=cwd,
            env=environment if environment is not None else self.environment,
            capture_output=True,
            check=False,
            text=True,
        )
        if result.returncode != 0 and not allow_failure:
            raise BuildError(
                f"command failed: {' '.join(str(part) for part in command)}"
            )
        return result.stdout

    def require(self, *names: str) -> None:
        for name in names:
            if shutil.which(name, path=self.environment.get("PATH")) is None:
                raise BuildError(f"required command not found: {name}")

    def without_host_build_variables(self) -> dict[str, str]:
        """A PE cross build must not see the host compiler or SDK settings."""

        environment = dict(self.environment)
        for name in HOST_BUILD_VARIABLES:
            environment.pop(name, None)
        return environment


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_archive(directory: Path, tar_name: str, members: tuple[str, ...]) -> Path:
    """Create the tar.gz and its shasum-compatible checksum file."""

    path = directory / tar_name
    with tarfile.open(path, "w:gz") as tar:
        for member in members:
            tar.add(directory / member, arcname=member)
    (directory / f"{tar_name}.sha256").write_text(
        f"{sha256(path)}  {tar_name}\n", encoding="utf-8"
    )
    return path


def extract_archive(source: Path, destination: Path) -> None:
    with tarfile.open(source) as tar:
        tar.extractall(destination, filter="tar")


def clone_tree(source: Path, destination: Path) -> None:
    """Copy a tree with APFS clones when the host supports them."""

    result = subprocess.run(
        ["cp", "-cR", str(source), str(destination)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        shutil.copytree(source, destination, symlinks=True)


def logical_cpu_count() -> str:
    return subprocess.run(
        ["sysctl", "-n", "hw.logicalcpu"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()


def is_macho(path: Path) -> bool:
    try:
        with path.open("rb") as file:
            return file.read(4) in MACHO_MAGIC
    except OSError:
        return False


def sign_directory(builder: Builder, directory: Path) -> None:
    for path in sorted(directory.rglob("*")):
        if path.is_symlink() or not path.is_file() or not is_macho(path):
            continue
        builder.run("codesign", "--force", "--sign", "-", path)


def references_in(builder: Builder, binary: Path, prefix: str) -> list[str]:
    references: list[str] = []
    for line in builder.capture("otool", "-L", binary).splitlines()[1:]:
        reference = line.strip().split(" (", 1)[0]
        if reference.startswith(prefix):
            references.append(reference)
    return references


def rewrite_references(builder: Builder, directory: Path, binary: Path) -> None:
    relative = os.path.relpath(directory, binary.parent)
    if ".dylib" in binary.name:
        builder.run(
            "install_name_tool",
            "-id",
            f"@loader_path/{binary.name}",
            binary,
        )
    for reference in references_in(builder, binary, "/opt/homebrew/"):
        builder.run(
            "install_name_tool",
            "-change",
            reference,
            f"@loader_path/{relative}/{Path(reference).name}",
            binary,
        )
    builder.run("codesign", "--force", "--sign", "-", binary)
