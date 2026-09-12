# DXMT cursor-latency patch

This patch targets DXMT commit `4ddb20e54672c0cb56115ce80d6db1beef94ae28`
(`v0.80-213-g4ddb20e`, an unreleased post-0.80 canary revision).
It adds one bounded, opt-in frame-latency override used by the Arknights macOS Runtime
canary:

`ARKNIGHTS_RUNTIME_DXMT_MAX_FRAME_LATENCY=1`, `2`, or `3`

The environment variable is read once, during lazy static initialization when
the first `CommandQueue` is constructed. Missing, empty, malformed, or
out-of-range values use DXMT's upstream default of `3`. No environment lookup
or parsing occurs in `PresentBoundary()` or another frame hot path. The
existing `IDXGIDevice::SetMaximumFrameLatency` API remains unchanged.

This is an experimental cursor-rendering latency control. It does not claim to
fix every cursor symptom, including capture-software duplicate-pointer
reports, and it is not enabled by default.

## Provenance

- Upstream: <https://github.com/3Shain/dxmt>
- Base commit: `4ddb20e54672c0cb56115ce80d6db1beef94ae28`
- License: LGPL-2.1-or-later, matching the pinned DXMT revision and modified source file.

## Static validation

Apply with `git apply` from the DXMT source root. The patch is intentionally
small and only changes `src/dxmt/dxmt_command_queue.cpp`. Validate the
contract by checking that the lookup appears in the command-queue
initialization and not in `PresentBoundary()`, then compile DXMT through the
Arknights macOS Runtime build workflow on Apple Silicon.
