# Architecture

Arknights macOS Runtime owns immutable input pins, patch provenance, build orchestration, candidate
validation, and release artifacts.

The initial candidate is deliberately an overlay build: it verifies and extracts the pinned
runtime archive, rebuilds only patched Wine/DXMT components from their exact source commits, and
replaces matching files in a new artifact. This shortens feedback while a release build is being
qualified. It does not qualify as a release build because unchanged base components still
inherit the upstream artifact's provenance and macOS deployment target.

```text
runtime.lock.json -> verified source checkouts -> ordered patch families
                 -> component builds -> verified base copy -> overlay
                 -> structural report -> canary artifact
```

The release artifact contains the Audio, Cursor, Performance, ACE, and CN patch families in one archive. Release
validation still requires a clean build of every component. Both lanes must preserve archive schema
2: top-level `Wine/` and `DXMT/`, the Wine loader and server, macOS driver, WineMetal bridge, and the
x64/x32 DXMT payloads expected by the launcher.

Runtime flags are parsed inside their owning component. `ARKNIGHTS_RUNTIME_AUDIO_FOLLOW_DEFAULT_OUTPUT`,
`ARKNIGHTS_RUNTIME_ACE_COMPACT`, and `ARKNIGHTS_RUNTIME_CN_COMPAT` accept only `0` or `1`;
`ARKNIGHTS_RUNTIME_DXMT_MAX_FRAME_LATENCY` accepts only `1` through `3`. Absent or invalid values preserve
the documented defaults. The ACE gate owns the kernel, dispatcher, Rosetta, and timing routes; the CN gate
owns the Bilibili image and window preflights documented in the [patch registry](patch-registry.md#cn).
`ARKNIGHTS_RUNTIME_PERFORMANCE=1` enables WineMetal's display-profile cache and ColorSync
resource cleanup. Missing, `0`, and invalid values keep the upstream route. WineMetal reads the
flag once when its library loads; display queries only check the cached boolean. Display/profile
notifications invalidate cached chromaticities, with a one-second expiry as a fallback. EDR values
remain live. Existing audio, ACE, CN, synchronization, shader-cache, and frame-latency controls retain
their independent behavior.

The launcher selects these flags from the active client's profile. A profile owns its publisher,
distribution variant, runtime environment overrides, and whether Play must show the ACE warning;
the runtime does not infer compatibility from a publisher name. This keeps a future publisher's ACE
client independent from the Bilibili CN routes while preserving the same component-local defaults.
