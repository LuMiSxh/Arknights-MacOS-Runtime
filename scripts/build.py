# SPDX-License-Identifier: MPL-2.0

"""Build one runtime lane and write its release outputs.

`candidate` builds the lane for testing. `release` builds the gated artifact. Both write the
same files to the output directory. The toolchain stays the caller's job: Nix for
rosetta-x86_64, and llvm-mingw through `LLVM_MINGW_ROOT` for native-arm64.
"""

import argparse
import subprocess
from pathlib import Path

from scripts.build_common import ROOT, Builder, BuildError
from scripts.lanes import arm64, x86_64
from scripts.lanes.arm64_assemble import AssemblyError
from scripts.lanes.arm64_external import FetchError
from scripts.lib.artifact import ArtifactError
from scripts.lib.console import error, success
from scripts.lock.model import LockError
from scripts.lock.sources import BUILD_ROOT
from scripts.release.licenses import LicenseError
from scripts.release.provenance import ProvenanceInputError
from scripts.release.verify import (
    ReleaseValidationError,
    normalize_version,
)

LANES = {lane.TARGET.name: lane for lane in (x86_64, arm64)}
FAILURES = (
    ArtifactError,
    AssemblyError,
    BuildError,
    FetchError,
    LicenseError,
    LockError,
    ProvenanceInputError,
    ReleaseValidationError,
    OSError,
    subprocess.CalledProcessError,
)


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("candidate", "release"))
    parser.add_argument("--target", required=True, choices=sorted(LANES))
    parser.add_argument(
        "--version", required=True, help="plain SemVer version, such as 0.9.0"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="output directory; the default is .build/out/<target>",
    )
    parsed = parser.parse_args(arguments)
    output = (parsed.output or BUILD_ROOT / "out" / parsed.target).resolve()
    builder = Builder()
    try:
        version = normalize_version(parsed.version)
        if version != parsed.version:
            raise ReleaseValidationError(
                f"version must be bare SemVer without a leading v, such as 0.9.0: "
                f"{parsed.version!r}"
            )
        source_commit = builder.capture(
            "git", "-C", str(ROOT), "rev-parse", "--verify", "HEAD"
        ).strip()
        LANES[parsed.target].build_runtime(
            builder,
            release=parsed.mode == "release",
            version=version,
            output=output,
            source_commit=source_commit,
        )
    except FAILURES as failure:
        error(str(failure))
        return 1
    success(f"wrote {output}")
    return 0
