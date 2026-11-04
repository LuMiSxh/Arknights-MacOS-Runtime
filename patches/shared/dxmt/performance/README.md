# DXMT performance patches

Target DXMT <!-- pin:dxmt.commit|code -->`9839e55f98d4aca103957ee4132d6395a325a9ed`<!-- /pin --> (<!-- pin:dxmt.describe|code -->`v0.80-361-g9839e55`<!-- /pin -->, an unreleased post-<!-- pin:dxmt.tag -->0.80<!-- /pin --> canary). The patch is unconditional. It has no runtime flag.

1. `0001-dxmt-skip-release-present-statistics.patch` puts `UpdateStatistics` and the rolling statistics aggregation behind `DXMT_DEBUG`. Release builds skip the per-present `std::format` calls and the aggregation. Frame counters and synchronization stay unchanged.

Gates, removal conditions, and patch IDs are in the [patch registry](../../../docs/patch-registry.md#performance).

## Provenance

- Upstream: <https://github.com/3Shain/dxmt>
- License: LGPL-2.1-or-later, matching the pinned DXMT revision and modified source files.

## Static validation

1. Apply the patch with `git apply` from the DXMT source root.
2. Check that the patch gates only `UpdateStatistics` and `statistics.compute`.
3. Compile DXMT through the build workflow on Apple Silicon.
