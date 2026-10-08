# Releasing

Nothing publishes automatically. Candidate workflows build disposable overlay artifacts. The manually dispatched release workflow builds the runtime (all seven patch families) and creates only a draft.

A build is promotable only after source and patch checks, a clean full build, archive validation, complete corresponding source and licenses, and the manual compatibility checks.

1. Make sure the protected default branch is clean. Dispatch the workflow with one SemVer version, such as `0.5.0`. An optional leading `v` is removed. Do not create a tag first.
2. The workflow checks that the derived tag and GitHub Release do not exist, then builds the pinned inputs from the exact default-branch commit. A failed build creates no tag and no release.
3. After the clean-build, `releaseEligible`, checksum, provenance, notice, and corresponding-source gates pass, the workflow re-checks the tag and release. It then creates the tag and a draft release at the built SHA, non-latest and unpublished.
4. Inspect and test those exact assets. Never substitute a local rebuild. Publish the unchanged draft only after the source, notice, and manual compatibility review.
5. The runtime archive, corresponding source archive, lock, and capability manifest form one immutable versioned contract. Build the producer manifest into `Libraries/` before the draft. Update consumer pins only after publication.
6. A failed retry cannot reuse a version after a tag or release exists. Corrections receive a new version. Consumers roll back by restoring the previous immutable artifact URL and checksum.
