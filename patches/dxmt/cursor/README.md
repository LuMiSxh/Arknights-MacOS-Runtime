# DXMT cursor-latency patch

Targets DXMT `e94c312f5c054263acf261cfa109edf13e757587` (`v0.80-262-ge94c312`, an unreleased post-0.80 canary). Adds one opt-in frame-latency override: `ARKNIGHTS_RUNTIME_DXMT_MAX_FRAME_LATENCY=0`, `1`, `2`, or `3`.

- DXMT reads the variable once, during lazy static initialization when the first `CommandQueue` is constructed. No frame hot path, including `PresentBoundary()`, looks up or parses the environment.
- A missing, empty, malformed, or out-of-range value uses the upstream default `3`.
- Value `0` is an Arknights extension: it commits the current frame and waits for its completion fence before `PresentBoundary()` returns, so no completed GPU frame stays queued. It differs from DXGI zero, which resets a device-level latency to its default.

The patch is an experimental, default-off control. It does not claim to fix every cursor symptom, including capture-software duplicate-pointer reports.

## Provenance

- Upstream: <https://github.com/3Shain/dxmt>
- License: LGPL-2.1-or-later, matching the pinned DXMT revision and modified source file.

## Static validation

The patch changes only `src/dxmt/dxmt_command_queue.cpp`. Apply it with `git apply` from the DXMT source root. Check that the lookup is in the command-queue initialization and not in `PresentBoundary()`. Then compile DXMT through the build workflow on Apple Silicon.
