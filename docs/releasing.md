# Releasing

Nothing publishes automatically. Candidate workflows build disposable artifacts. The manually dispatched release workflows build the runtime and create only a draft.

A build is promotable only after source and patch checks, a clean build, archive validation, complete corresponding source and licenses, and the manual compatibility checks.

Before a release, move the upstream pins with `just update-pins`. See [updating pins](updating-pins.md).

## Lanes

| Lane               | Target           | Runner     | Tag                      |
| ------------------ | ---------------- | ---------- | ------------------------ |
| x86_64 (Rosetta 2) | `rosetta-x86_64` | `xcode-27` | `vX.Y.Z+x86` or `vX.Y.Z` |
| ARM64              | `native-arm64`   | `macos-26` | `vX.Y.Z+arm`             |

The client pins the release archive URL and SHA-256 in its `runtime.json`. There is no runtime update feed, no latest-release lookup, and no feed signing key. A runtime update needs a new client version.

## x86_64 release

1. Make sure the protected default branch is clean. Dispatch **Draft Release** with one SemVer version, such as `0.5.0+x86`. An optional leading `v` is removed. Do not create a tag first.
   Build metadata names the architecture: `+x86` for the Rosetta lane. A version without metadata counts as `x86` for older releases. One version and architecture pair is one tag, so `v0.5.0+x86` and `v0.5.0+arm` are distinct releases. SemVer forbids `_` in build metadata, so use `+x86`, not `+x86_64`.
2. The workflow checks that the derived tag and GitHub Release do not exist, then builds the pinned inputs from the exact default-branch commit. The `build` job has read-only permissions and uploads the release assets as one workflow artifact. A failed build creates no tag and no release.
3. After the clean-build, `releaseEligible`, checksum, provenance, notice, and corresponding-source gates pass, the `publish` job downloads the assets. It is the only job with write permission. It re-checks the tag and release and attests the assets. It then creates the tag and a draft release at the built SHA, non-latest and unpublished.
4. Inspect and test those exact assets. Never substitute a local rebuild. Publish the unchanged draft only after the source, notice, and manual compatibility review.
5. The runtime archive, corresponding source archive, and lock form one immutable versioned contract. The lock carries the runtime features for the lane. Update consumer pins only after publication.
6. A failed retry cannot reuse a version after a tag or release exists. Corrections receive a new version. Consumers roll back by restoring the previous immutable artifact URL and checksum.

## ARM64 release

The ARM64 lane ships an external Wine tree and builds DXMT in the workflow. The catalog URL is the only secret. Store it as the repository secret `ARM64_RUNTIME_CATALOG_URL`. The `release-arm64` environment scopes the release job; restrict it to `main`, `release/*`, and `version-*`.

`toolchain.llvmMingw` in `runtime.lock.json` pins the llvm-mingw release URL and SHA-256. The repository variables `LLVM_MINGW_URL` and `LLVM_MINGW_SHA256` apply only when the lock has no pin. They are public build inputs, not secrets.

1. Dispatch **Draft ARM64 Release** with a version such as `0.9.0`. The workflow appends `+arm`. Optionally enter a catalog release id; leave it empty to use the newest ARM64 release.
2. The workflow selects the release id and takes the SHA-256 from the catalog, fetches the artifact, verifies it, and extracts it. The lock pin is the last verified baseline. The catalog and archive URLs never appear in output, assets, or provenance.
3. `scripts/arm64/build_dxmt.py` builds DXMT from `sources.dxmt` for ARM64EC with `MACOSX_DEPLOYMENT_TARGET=26.0`. It also builds a minimal Wine tree for the import libraries. That Wine build is a build dependency and is never shipped.
4. `scripts/arm64/assemble.py` repacks the client tree as `Libraries/Wine`, `Libraries/DXMT`, `Licenses/`, and `NOTICE.md`. The signed `wine.app` keeps its Developer ID signature.
5. `scripts/validate_runtime.py --target native-arm64` validates the tree. A Mach-O whose `minos` is above 26.0 prints a warning instead of failing, because the external Wine tree is built upstream. Check the warnings before you publish.
6. The publish job re-checks the tag and release, attests the archives, and creates the tag and a draft release at the built SHA. The release is normal, not a prerelease.
7. The release assets are the runtime archive, its checksum, the corresponding source archive, its checksum, `provenance.json`, and `NOTICE.md`. The source archive contains `wine-build-new`, `runtime.lock.json`, and `docs/arm/README.md`.
8. Inspect and test those exact assets. Publish the unchanged draft only after the source, notice, and manual compatibility review.

The release notes and `provenance.json` credit `https://github.com/riverfog7/wine-build-new`. The release notes name the selected catalog release. `provenance.json` records its id and SHA-256 under `externalArtifact`. The ARM runtime archive and corresponding source archive form one immutable versioned contract. The client pins the archive URL and SHA-256.

## Verify build provenance

The `publish` job creates a build provenance attestation for every release asset. The attestation links each asset to this repository, the workflow, and the built commit.

1. Download a release asset, for example `Arknights-MacOS-Runtime-v0.7.0+x86.tar.gz`.
2. Install the GitHub CLI.
3. Run `gh attestation verify Arknights-MacOS-Runtime-v0.7.0+x86.tar.gz --repo LuMiSxh/Arknights-MacOS-Runtime`.
4. Trust the asset only if the command succeeds.

The x86_64 `provenance.json` asset records the versions of the Homebrew packages, Xcode, and macOS SDK of the build host. The build does not pin these tools. The ARM64 `provenance.json` asset records the external Wine revision, the archive hashes, and the repository credit.
