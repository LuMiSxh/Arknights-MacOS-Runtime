# DXMT performance patches

Target DXMT `e94c312f5c054263acf261cfa109edf13e757587` (`v0.80-262-ge94c312`, an unreleased post-0.80 canary). The patch is unconditional. It has no runtime flag.

1. `0001-dxmt-skip-release-present-statistics.patch` puts `UpdateStatistics` and the rolling statistics aggregation behind `DXMT_DEBUG`. Release builds skip the per-present `std::format` calls and the aggregation. Frame counters and synchronization stay unchanged.

Gates, removal conditions, and patch IDs are in the [patch registry](../../../docs/patch-registry.md#performance).

## Provenance

- Upstream: <https://github.com/3Shain/dxmt>
- License: LGPL-2.1-or-later, matching the pinned DXMT revision and modified source files.

## Static validation

1. Apply the patch with `git apply` from the DXMT source root.
2. Check that the patch gates only `UpdateStatistics` and `statistics.compute`.
3. Compile DXMT through the build workflow on Apple Silicon.
