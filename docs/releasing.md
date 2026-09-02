# Releasing

No release is published automatically. Candidate workflows validate and build disposable overlay
artifacts; the manually dispatched release workflow builds the runtime, which contains the
Audio, Cursor, and CN patch families, and creates only a draft. A build is promotable only after
source/patch checks, a clean full build, archive validation, complete corresponding source and
licenses, and the documented manual compatibility checks.

1. Ensure the protected default branch is clean and dispatch the workflow with one SemVer version,
   such as `0.5.0` (an optional leading `v` is normalized). Do not create a tag first.
2. Before expensive work, the workflow verifies that the derived tag and GitHub Release do not exist,
   checks out the exact default-branch commit, and builds the pinned inputs. A failed build or
   verification therefore creates neither a tag nor a release.
3. After the clean-build, `releaseEligible`, checksum, provenance, notice, and corresponding-source
   gates pass, the workflow re-checks the tag and release, then creates the tag and a draft release at
   the exact built SHA. It explicitly leaves the release non-latest and unpublished.
4. Inspect and test those exact assets; never substitute a local rebuild. Publish the unchanged draft
   only after the corresponding-source, notice, and manual compatibility review.
5. A failed retry cannot reuse a version after a tag or release exists; corrections receive a new
   version. Consumers roll back by restoring the previous immutable artifact URL and checksum.
