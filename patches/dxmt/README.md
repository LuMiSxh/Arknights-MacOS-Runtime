# DXMT patches

These patches apply to the `rosetta-x86_64` target.

| Number | File | Purpose | Gate variable | Default | Targets |
| ------ | ---- | ------- | ------------- | ------- | ------- |
| 0001 | `0001-dxmt-skip-release-present-statistics.patch` | Skip release present statistics work | `DXMT_DEBUG` (build gate) | not applicable | x86 only |

## 0001 Release present statistics

Target DXMT <!-- pin:dxmt.commit|code -->`9839e55f98d4aca103957ee4132d6395a325a9ed`<!-- /pin -->
(<!-- pin:dxmt.describe|code -->`v0.80-361-g9839e55`<!-- /pin -->, an unreleased
post-<!-- pin:dxmt.tag -->0.80<!-- /pin --> canary).
The patch is unconditional. It has no runtime flag.

DXMT's HUD is compiled out of release builds, but each present still formats the
statistics strings before the HUD no-op returns. Release builds also aggregate
the rolling statistics window at every present, although only the debug HUD
consumes the aggregates.

The patch puts `UpdateStatistics` and the rolling statistics aggregation behind
`DXMT_DEBUG`. Release builds skip the per-present `std::format` calls and the
aggregation. Frame counters, measurements, advancement, synchronization, latency
waits, and resets stay unchanged.

Gates, removal conditions, and patch IDs are in the
[patch registry](../../docs/patch-registry.md#performance).

## Static validation

1. Apply the patch with `git apply` from the DXMT source root.
2. Check that the patch gates only `UpdateStatistics` and `statistics.compute`.
3. Compile DXMT through the build workflow on Apple Silicon.

See [provenance.md](provenance.md) for the source, author, and license.
