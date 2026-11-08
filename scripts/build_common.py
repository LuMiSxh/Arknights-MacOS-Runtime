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
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

if __package__:
    from .lib.console import info
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from lib.console import info


ROOT = Path(__file__).resolve().parents[1]


WINE_PREFIX = "/opt/whiskywine"


WINE_CONFIGURE_FLAGS = (
    "--without-ffmpeg",
    "--without-gstreamer",
    "--without-x",
    "--without-wayland",
    "--without-oss",
    "--without-alsa",
    "--without-pulse",
    "--without-sane",
    "--without-usb",
    "--without-v4l2",
    "--without-pcap",
    "--without-capi",
    "--without-opencl",
    "--without-cups",
)


NATIVE_ARM64_TARGET = "native-arm64"


WINE_BUILD_NEW_REPOSITORY = "https://github.com/riverfog7/wine-build-new"


VALIDATE_CLI = ROOT / "scripts" / "validate_runtime.py"


LICENSE_CLI = ROOT / "scripts" / "release" / "licenses.py"


TOOLCHAIN_CLI = ROOT / "scripts" / "release" / "toolchain.py"


ARCHIVE_BUNDLED_LIBRARIES = ("libfreetype.6.dylib", "libgnutls.30.dylib")


MACHO_MAGIC = (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe")


MACHO_SUFFIXES = (".so", ".dylib")


LOADER_RPATH = "@loader_path/../../"


CLEARED_DOS_STUB = bytes.fromhex("0e1fba0e00b409cd21b8014ccd219090")


HOST_BUILD_VARIABLES = (
    "CFLAGS",
    "CXXFLAGS",
    "CPPFLAGS",
    "CROSSCFLAGS",
    "LDFLAGS",
    "OBJCFLAGS",
    "CC",
    "CXX",
    "OBJC",
    "SDKROOT",
    "MACOSX_DEPLOYMENT_TARGET",
)


# Set this to a launcher command, for example `ccache`, to route the Meson
# cross-compilers of a build lane through a compiler cache.
CCACHE_ENVIRONMENT_VARIABLE = "LMISXH_AKMOCL_CCACHE"


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
            message = f"command failed: {' '.join(str(part) for part in command)}"
            tail = result.stderr.strip().splitlines()[-20:]
            if tail:
                message = f"{message}\n{'\n'.join(tail)}"
            raise BuildError(message)
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
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode == 0:
        return
    if destination.is_symlink() or not destination.is_dir():
        destination.unlink(missing_ok=True)
    else:
        shutil.rmtree(destination)
    try:
        shutil.copytree(source, destination, symlinks=True)
    except OSError as failure:
        stderr = result.stderr.decode(errors="replace").strip()
        raise BuildError(f"cannot copy {source}: {failure}\ncp: {stderr}") from failure


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


def clear_dos_stub(path: Path) -> None:
    """Blank the DOS stub of a PE so the loader skips it."""

    with path.open("r+b") as file:
        file.seek(64)
        file.write(CLEARED_DOS_STUB)


def adhoc_sign(builder: Builder, path: Path) -> None:
    builder.run("codesign", "--force", "--sign", "-", path)


def references_in(builder: Builder, binary: Path, prefix: str) -> list[str]:
    references: list[str] = []
    for line in builder.capture("otool", "-L", binary).splitlines()[1:]:
        reference = line.strip().split(" (", 1)[0]
        if reference.startswith(prefix):
            references.append(reference)
    return references


def ensure_loader_rpath(builder: Builder, binary: Path) -> None:
    if LOADER_RPATH not in builder.capture("otool", "-l", binary):
        builder.run("install_name_tool", "-add_rpath", LOADER_RPATH, binary)


def nix_build(builder: Builder, attribute: str) -> Path:
    output = builder.capture(
        "nix",
        "--extra-experimental-features",
        "nix-command flakes",
        "build",
        "--no-link",
        "--print-out-paths",
        attribute,
    ).strip()
    if not output:
        raise BuildError(f"nix build produced no output for {attribute}")
    return Path(output)


def nix_package_outputs(
    builder: Builder, nixpkgs: str, system: str, packages: tuple[str, ...]
) -> list[Path]:
    """Resolve the dev, out, and lib outputs of the pinned packages."""

    outputs: list[Path] = []
    for package in packages:
        for output_name in ("dev", "out", "lib"):
            outputs.append(
                nix_build(
                    builder,
                    f"{nixpkgs}#legacyPackages.{system}.{package}.{output_name}",
                )
            )
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
    adhoc_sign(builder, binary)


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


def compiler_launcher(environment: dict[str, str]) -> tuple[str, ...]:
    """Return the opt-in compiler launcher prefix of the build environment."""

    value = environment.get(CCACHE_ENVIRONMENT_VARIABLE, "").strip()
    return tuple(value.split()) if value else ()


def write_compiler_launcher_cross_file(
    directory: Path, compilers: dict[str, str], environment: dict[str, str]
) -> Path | None:
    """Write a Meson cross-file that routes compilers through the launcher.

    The lane passes the file after the upstream cross-file, so Meson prefers
    these compiler entries. The function returns None when no launcher is set,
    which keeps local builds unchanged.
    """

    launcher = compiler_launcher(environment)
    if not launcher:
        return None
    lines = ["[binaries]"]
    for language, compiler in compilers.items():
        parts = ", ".join(f"'{part}'" for part in (*launcher, compiler))
        lines.append(f"{language} = [{parts}]")
    path = directory / "compiler-launcher.ini"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
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
    inventory: set[str] = set()
    queue = deque(
        output / "lib" / name
        for output in outputs
        for name in ARCHIVE_BUNDLED_LIBRARIES
        if (output / "lib" / name).is_file()
    )
    for module in sorted((directory / "wine").glob("*-unix/*.so")):
        queue.extend(
            Path(reference) for reference in references_in(builder, module, NIX_STORE)
        )

    copied: dict[str, Path] = {}
    seen: set[Path] = set()
    while queue:
        reference = queue.popleft()
        if reference in seen:
            continue
        seen.add(reference)
        name = reference.name
        if name in copied:
            if copied[name] != reference:
                raise BuildError(
                    f"library name collision: {name} from "
                    f"{copied[name]} and {reference}"
                )
            continue
        if (directory / name).exists():
            continue
        shutil.copy2(reference, directory / name)
        destination = directory / name
        destination.chmod(0o644)
        copied[name] = reference
        if reference.as_posix().startswith(NIX_STORE):
            inventory.add(str(Path(*reference.parts[:4])))
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
        ensure_loader_rpath(builder, binary)
        adhoc_sign(builder, binary)
    return sorted(inventory)
