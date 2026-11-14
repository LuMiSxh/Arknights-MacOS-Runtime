#!/usr/bin/env -S uv run --locked --no-dev
# SPDX-License-Identifier: MPL-2.0

"""Build one runtime lane and write its release outputs.

`candidate` builds the lane for testing. `release` builds the gated artifact. Both write the
same files to the output directory. The toolchain stays the caller's job: Nix for
rosetta-x86_64, and llvm-mingw through `LLVM_MINGW_ROOT` for native-arm64.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_common import Builder, BuildError
from scripts.lib.artifact import ArtifactError
from scripts.lib.console import error, success
from scripts.release.licenses import LicenseError
from scripts.release.provenance import ProvenanceInputError
from scripts.release.verify import (
    ReleaseValidationError,
    normalize_version,
)
from scripts.runtime import BUILD_ROOT, LockError
from scripts.targets import arm64, x86_64
from scripts.targets.arm64_assemble import AssemblyError
from scripts.targets.arm64_external import FetchError

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


if __name__ == "__main__":
    raise SystemExit(main())
