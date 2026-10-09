# Releasing

Nothing publishes automatically. Candidate workflows build disposable overlay artifacts. The manually dispatched release workflow builds the runtime (all seven patch families) and creates only a draft.

A build is promotable only after source and patch checks, a clean full build, archive validation, complete corresponding source and licenses, and the manual compatibility checks.

1. Make sure the protected default branch is clean. Dispatch the workflow with one SemVer version, such as `0.5.0`. An optional leading `v` is removed. Do not create a tag first.
2. The workflow checks that the derived tag and GitHub Release do not exist, then builds the pinned inputs from the exact default-branch commit. The `build` job has read-only permissions and uploads the release assets as one workflow artifact. A failed build creates no tag and no release.
3. After the clean-build, `releaseEligible`, checksum, provenance, notice, and corresponding-source gates pass, the `publish` job downloads the assets. It is the only job with write permission. It re-checks the tag and release and attests the assets. It then creates the tag and a draft release at the built SHA, non-latest and unpublished.
4. Inspect and test those exact assets. Never substitute a local rebuild. Publish the unchanged draft only after the source, notice, and manual compatibility review.
5. The runtime archive, corresponding source archive, lock, and capability manifest form one immutable versioned contract. Build the producer manifest into `Libraries/` before the draft. Update consumer pins only after publication.
6. A failed retry cannot reuse a version after a tag or release exists. Corrections receive a new version. Consumers roll back by restoring the previous immutable artifact URL and checksum.

## Verify build provenance

The `publish` job creates a build provenance attestation for every release asset. The attestation links each asset to this repository, the workflow, and the built commit.

1. Download a release asset, for example `Arknights-MacOS-Runtime-v0.7.0.tar.gz`.
2. Install the GitHub CLI.
3. Run `gh attestation verify Arknights-MacOS-Runtime-v0.7.0.tar.gz --repo LuMiSxh/Arknights-MacOS-Runtime`.
4. Trust the asset only if the command succeeds.

The `provenance.json` asset records the versions of the Homebrew packages, Xcode, and macOS SDK of the build host. The build does not pin these tools.
