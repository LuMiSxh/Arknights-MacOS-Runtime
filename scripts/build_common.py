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


RUNTIME_CLI = ROOT / "scripts" / "runtime.py"


VALIDATE_CLI = ROOT / "scripts" / "validate_runtime.py"


LICENSE_CLI = ROOT / "scripts" / "release" / "licenses.py"


TOOLCHAIN_CLI = ROOT / "scripts" / "release" / "toolchain.py"


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


NIX_DEFAULT_BIN = Path("/nix/var/nix/profiles/default/bin")


NIX_PACKAGES = (
    "freetype",
    "gnutls",
    "libpng",
    "zlib",
    "brotli",
    "bzip2",
    "nettle",
    "libtasn1",
    "libidn2",
    "p11-kit",
    "libunistring",
    "gmp",
    "vulkan-headers",
)


class BuildError(RuntimeError):
    """The build cannot continue."""


@dataclass
class Builder:
    """Run build commands with one explicit environment."""

    environment: dict[str, str] = field(default_factory=lambda: dict(os.environ))

    def __post_init__(self) -> None:
        """Use the default Nix profile when the shell does not export it."""
        path = self.environment.get("PATH", "")
        if (
            shutil.which("nix", path=path) is None
            and (NIX_DEFAULT_BIN / "nix").is_file()
        ):
            self.environment["PATH"] = f"{NIX_DEFAULT_BIN}:{path}"

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


def write_archive(
    directory: Path,
    tar_name: str,
    members: tuple[str, ...],
    *,
    content_root: Path | None = None,
) -> Path:
    """Create the tar.gz and its shasum-compatible checksum file.

    `content_root` holds the members when the archive itself is written elsewhere.
    """

    root = content_root or directory
    path = directory / tar_name
    with tarfile.open(path, "w:gz") as tar:
        for member in members:
            tar.add(root / member, arcname=member)
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


def nix_build(builder: Builder, attribute: str) -> Path | None:
    output = builder.capture(
        "nix",
        "--extra-experimental-features",
        "nix-command flakes",
        "build",
        "--no-link",
        "--print-out-paths",
        attribute,
        allow_failure=True,
    ).strip()
    return Path(output) if output else None


def nix_package_outputs(
    builder: Builder, nixpkgs: str, system: str, packages: tuple[str, ...]
) -> list[Path]:
    """Resolve the dev, out, and lib outputs of the pinned packages."""

    outputs: list[Path] = []
    for package in packages:
        for output_name in ("dev", "out", "lib"):
            output = nix_build(
                builder,
                f"{nixpkgs}#legacyPackages.{system}.{package}.{output_name}",
            )
            if output is not None:
                outputs.append(output)
    return outputs


def fix_release_macho(builder: Builder, directory: Path, binary: Path) -> None:
    """Relocate a bundled Nix library next to the modules that load it."""

    relative = os.path.relpath(directory, binary.parent)
    binary.chmod(binary.stat().st_mode | 0o200)
    if ".dylib" in binary.name:
        builder.run("install_name_tool", "-id", f"@loader_path/{binary.name}", binary)
    for reference in references_in(builder, binary, NIX_STORE):
        name = Path(reference).name
        if name.startswith("libiconv") and "_iconv" in builder.capture(
            "nm", "-u", binary, allow_failure=True
        ):
            builder.run(
                "install_name_tool",
                "-change",
                reference,
                "/usr/lib/libiconv.2.dylib",
                binary,
            )
        else:
            builder.run(
                "install_name_tool",
                "-change",
                reference,
                f"@loader_path/{relative}/{name}",
                binary,
            )
    builder.run("codesign", "--force", "--sign", "-", binary)


def write_dxmt_native_file(root: Path, deployment: str) -> Path:
    """Pin the native macOS targets, which Meson otherwise builds for the SDK."""

    path = root / "dxmt-native.ini"
    flags = f"['-mmacosx-version-min={deployment}']"
    path.write_text(
        "[built-in options]\n"
        f"c_args = {flags}\n"
        f"cpp_args = {flags}\n"
        f"c_link_args = {flags}\n"
        f"cpp_link_args = {flags}\n",
        encoding="utf-8",
    )
    return path


def library_flags(outputs: list[Path]) -> tuple[str, str, str]:
    """Return the pkg-config path and the include and library flags of the outputs."""

    pkg_config: list[str] = []
    includes: list[str] = []
    libraries: list[str] = []
    for output in outputs:
        if (output / "lib" / "pkgconfig").is_dir():
            pkg_config.append(str(output / "lib" / "pkgconfig"))
        if (output / "include").is_dir():
            includes.append(f"-I{output / 'include'}")
        if (output / "lib").is_dir():
            libraries.append(f"-L{output / 'lib'}")
    return ":".join(pkg_config), " ".join(includes), " ".join(libraries)


def bundle_nix_libraries(
    builder: Builder, candidate: Path, outputs: list[Path]
) -> list[str]:
    """Copy the Nix library closure of the Wine unix modules next to the loader.

    Returns the store paths to record in the release component inventory.
    """

    directory = candidate / "Wine" / "lib"
    inventory: list[str] = []
    queue = [
        output / "lib" / name
        for output in outputs
        for name in ARCHIVE_BUNDLED_LIBRARIES
        if (output / "lib" / name).is_file()
    ]
    for module in sorted((directory / "wine").glob("*-unix/*.so")):
        queue.extend(
            Path(reference) for reference in references_in(builder, module, NIX_STORE)
        )

    while queue:
        reference = queue.pop(0)
        name = reference.name
        if (directory / name).exists():
            continue
        shutil.copy2(reference, directory / name)
        destination = directory / name
        destination.chmod(0o644)
        if reference.as_posix().startswith(NIX_STORE):
            inventory.append(
                NIX_STORE + reference.as_posix().split(NIX_STORE, 1)[1].split("/", 1)[0]
            )
        queue.extend(
            Path(next_reference)
            for next_reference in references_in(builder, destination, NIX_STORE)
        )

    for binary in sorted(directory.glob("*.dylib*")) + sorted(
        (directory / "wine").glob("*-unix/*.so")
    ):
        fix_release_macho(builder, directory, binary)
    link = directory / "libfreetype.dylib"
    link.unlink(missing_ok=True)
    link.symlink_to("libfreetype.6.dylib")
    for binary in sorted((directory / "wine").glob("*-unix/*.so")):
        if "@loader_path/../../" not in builder.capture("otool", "-l", binary):
            builder.run(
                "install_name_tool", "-add_rpath", "@loader_path/../../", binary
            )
        builder.run("codesign", "--force", "--sign", "-", binary)
    return sorted(set(inventory))
