# DXMT performance patches

Target DXMT `7c8dee1c2d73415301ceb7d1fa810861cef4cd67` (`v0.80-244-g7c8dee1`, an unreleased post-0.80 canary). Both patches are unconditional. They have no runtime flag.

1. `0001-dxmt-initialize-device-before-command-helpers.patch` moves the `device_` member and its initializer before the command helpers in `ArgumentEncodingContext`. `ClearUAV` reads `device_` while the helpers are constructed. Before the fix, it read indeterminate storage. This is a correctness fix, not an FPS claim.
2. `0002-dxmt-skip-release-present-statistics.patch` puts `UpdateStatistics` and the rolling statistics aggregation behind `DXMT_DEBUG`. Release builds skip the per-present `std::format` calls and the aggregation. Frame counters and synchronization stay unchanged.

Gates, removal conditions, and patch IDs are in the [patch registry](../../../docs/patch-registry.md#performance).

## Provenance

- Upstream: <https://github.com/3Shain/dxmt>
- License: LGPL-2.1-or-later, matching the pinned DXMT revision and modified source files.

## Static validation

1. Apply each patch with `git apply` from the DXMT source root, in numeric order.
2. Check that patch 0002 gates only `UpdateStatistics` and `statistics.compute`.
3. Compile DXMT through the build workflow on Apple Silicon.
