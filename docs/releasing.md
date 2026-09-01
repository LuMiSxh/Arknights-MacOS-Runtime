# Releasing

No release is automatic. A candidate is promotable only after source/patch checks, a clean full build,
archive validation, complete corresponding source and licenses, and the documented manual game canary.

1. After a reviewed release workflow exists, build from a clean protected `main` commit through it.
2. Create a draft SemVer release with immutable runtime, checksum, provenance, SBOM, notices, recipe,
   and corresponding-source assets.
3. Test those exact assets; never substitute a local rebuild.
4. Publish the unchanged draft, then pin its exact URL and checksum in Arknights Client.
5. Roll back by releasing a higher launcher patch that pins the previous immutable Arknights MacOS Runtime version.

Never replace a tag or asset. A correction receives a new version.
