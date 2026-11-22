# Releasing

Nothing publishes automatically. One workflow, **Runtime Build**, builds the runtime. You dispatch it by hand. The `candidate` channel builds disposable artifacts. The `release` channel builds both lanes and creates only a draft.

A build is promotable only after source and patch checks, a clean build, archive validation, complete corresponding source and licenses, and the manual compatibility checks.

Before a release, move the upstream pins with `just update-pins`. See [updating pins](updating-pins.md).

## Lanes

| Lane               | Target           | Runner     | Tag                      |
| ------------------ | ---------------- | ---------- | ------------------------ |
| x86_64 (Rosetta 2) | `rosetta-x86_64` | `xcode-27` | `vX.Y.Z`                 |
| ARM64              | `native-arm64`   | `macos-26` | `vX.Y.Z`                 |

The client pins the release archive URL and SHA-256 in its `runtime.json`. There is no runtime update feed, no latest-release lookup, and no feed signing key. A runtime update needs a new client version.

## Workflow inputs

| Input              | Value                                                                       |
| ------------------ | --------------------------------------------------------------------------- |
| `version`          | Bare SemVer, such as `1.0.0-rc1`. Do not add `+x86`, `+arm`, or a leading `v`. |
| `channel`          | `candidate` (default) or `release`.                                         |
| `target`           | `both` (default), `rosetta-x86_64`, or `native-arm64`.                      |
| `arm64_release_id` | Optional catalog release id for the ARM64 lane. Empty selects the newest.    |

The workflow has these jobs:

| Job           | Runs when                      | Purpose                                                                                       |
| ------------- | ------------------------------ | --------------------------------------------------------------------------------------------- |
| `prepare`     | Always                         | Validates the inputs and selects the lanes. A release also checks that the tag and release do not exist. |
| `build-x86_64` | `target` is `both` or `rosetta-x86_64` | Builds the x86_64 lane on `xcode-27`.                                                  |
| `build-arm64` | `target` is `both` or `native-arm64`   | Builds the ARM64 lane on `macos-26` in the `release-arm64` environment.                |
| `combine`     | `release` channel              | Verifies the lane outputs and writes one `provenance.json` and one `THIRD-PARTY-NOTICES.txt`. |
| `publish`     | `release` channel              | Attests the assets, creates the tag, and creates the draft release.                           |

Every lane job has read-only permissions and uploads its output as the artifact `runtime-<target>`. The artifact keeps for 3 days. The `release-arm64` environment and its secret reach only the ARM64 lane job.

## Candidate

1. Dispatch **Runtime Build** with `channel` set to `candidate`. Enter a prerelease version, such as `1.0.0-rc1`.
2. Set `target` to one lane to build only that lane. Set it to `both` to build both lanes.
3. Download the artifact `runtime-<target>` from the workflow run.

A candidate creates no tag and no release. The x86_64 lane runs from any branch.

## Release

1. Make sure the protected default branch is clean. Dispatch **Runtime Build** from the default branch. Set `channel` to `release` and `target` to `both`. A release of one lane is not possible. Do not create a tag first.
   Both lanes share one tag, `v1.0.0`. The asset names carry the architecture.
2. The `prepare` job checks that the tag and GitHub Release do not exist. Each lane job builds the pinned inputs from the dispatched commit. A failed build creates no tag and no release.
3. After the clean-build, `releaseEligible`, checksum, provenance, notice, and corresponding-source gates pass, the `combine` job writes the release assets. The `publish` job downloads them. It is the only job with write permission. It re-checks the tag and release and attests the assets. It then creates the tag and one draft release at the built SHA, non-latest and unpublished.
4. Inspect and test those exact assets. Never substitute a local rebuild. Publish the unchanged draft only after the source, notice, and manual compatibility review.
5. The runtime archive, corresponding source archive, and lock form one immutable versioned contract. The lock carries the runtime features for each lane. Update consumer pins only after publication.
6. A failed retry cannot reuse a version after a tag or release exists. Corrections receive a new version. Consumers roll back by restoring the previous immutable artifact URL and checksum.

## ARM64 lane

The ARM64 lane ships an external Wine tree and builds DXMT in the workflow. The catalog URL is the only secret. Store it as the repository secret `ARM64_RUNTIME_CATALOG_URL`. The `release-arm64` environment scopes the ARM64 lane job; restrict it to `main`, `release/*`, and `version-*`. Candidates of this lane also use that environment, so dispatch them from an allowed branch.

`toolchain.llvmMingw` in `runtime.lock.json` pins the llvm-mingw release URL and SHA-256. The repository variables `LLVM_MINGW_URL` and `LLVM_MINGW_SHA256` apply only when the lock has no pin. They are public build inputs, not secrets.

1. Dispatch **Runtime Build** as described above. Optionally enter `arm64_release_id`. Leave it empty to use the newest ARM64 release.
2. The workflow selects the release id and takes the SHA-256 from the catalog, fetches the artifact, verifies it, and extracts it. The lock pin is the last verified baseline. The catalog and archive URLs never appear in output, assets, or provenance.
3. `scripts/targets/arm64_dxmt.py` builds DXMT from `sources.dxmt` for ARM64EC with `MACOSX_DEPLOYMENT_TARGET=26.0`. It needs the fetched Wine artifact, so the lane fetches Wine first.
4. `scripts/targets/arm64_assemble.py` repacks the client tree as `Libraries/Wine`, `Libraries/DXMT`, `Licenses/`, and `NOTICE.md`. The signed loader bundle is renamed to `Arknights.app`. It keeps its Developer ID signature.
5. `scripts/build.py release --target native-arm64 --version 0.9.0` validates the tree and runs the release gates. The gate requires `inheritedMachOAboveTarget` to be `0`. Check the validation report before you publish.
6. The release is normal, not a prerelease. Its notes name the selected catalog release.
7. The release assets are, for each lane, the runtime archive and its `.sha256`, and the corresponding source archive and its `.sha256`. The release also has `provenance.json` and `THIRD-PARTY-NOTICES.txt`. The ARM64 source archive contains `wine-build-new`, `runtime.lock.json`, and `docs/arm/README.md`.
8. Inspect and test those exact assets. Publish the unchanged draft only after the source, notice, and manual compatibility review.

The release notes and `provenance.json` credit `https://github.com/riverfog7/wine-build-new`. The release notes name the selected catalog release. `provenance.json` records its id, SHA-256, and size under the `native-arm64` entry's `wine.artifact` field. The ARM runtime archive and corresponding source archive form one immutable versioned contract. The client pins the archive URL and SHA-256.

## Verify build provenance

The `publish` job creates a build provenance attestation for every release asset. The attestation links each asset to this repository, the workflow, and the built commit.

1. Download a release asset, for example `Arknights-MacOS-Runtime-v0.7.0-x86_64.tar.gz`.
2. Install the GitHub CLI.
3. Run `gh attestation verify Arknights-MacOS-Runtime-v0.7.0-x86_64.tar.gz --repo LuMiSxh/Arknights-MacOS-Runtime`.
4. Trust the asset only if the command succeeds.

The `provenance.json` asset merges one fragment per lane. Each fragment records the build commit, the resolved runtime lock, the validation report, the Wine and DXMT repository and commit, the archive hashes, and the build toolchain. The toolchain lists the Homebrew packages, Xcode, and macOS SDK of the build host. The build does not pin these tools.
