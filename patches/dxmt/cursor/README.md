# DXMT cursor-latency patch

This patch targets DXMT commit `7c8dee1c2d73415301ceb7d1fa810861cef4cd67`
(`v0.80-244-g7c8dee1`, an unreleased post-0.80 canary revision).
It adds one bounded, opt-in frame-latency override used by the Arknights macOS Runtime
canary:

`ARKNIGHTS_RUNTIME_DXMT_MAX_FRAME_LATENCY=0`, `1`, `2`, or `3`

The environment variable is read once, during lazy static initialization when
the first `CommandQueue` is constructed. Missing, empty, malformed, or
out-of-range values use DXMT's upstream default of `3`. No environment lookup
or parsing occurs in `PresentBoundary()` or another frame hot path. The
existing `IDXGIDevice::SetMaximumFrameLatency` API remains unchanged.

Value `0` is an Arknights-specific extension. It commits the current frame and
waits for that frame's completion fence before `PresentBoundary()` returns.
This allows no completed GPU frame to remain queued, but can reduce throughput
or make frame pacing less smooth. It is not the DXGI API meaning of zero, which
normally resets a device-level latency value to its default.

This is an experimental cursor-rendering latency control. It does not claim to
fix every cursor symptom, including capture-software duplicate-pointer
reports, and it is not enabled by default.

## Provenance

- Upstream: <https://github.com/3Shain/dxmt>
- Base commit: `7c8dee1c2d73415301ceb7d1fa810861cef4cd67`
- License: LGPL-2.1-or-later, matching the pinned DXMT revision and modified source file.

## Static validation

Apply with `git apply` from the DXMT source root. The patch is intentionally
small and only changes `src/dxmt/dxmt_command_queue.cpp`. Validate the
contract by checking that the lookup appears in the command-queue
initialization and not in `PresentBoundary()`, then compile DXMT through the
Arknights macOS Runtime build workflow on Apple Silicon.
