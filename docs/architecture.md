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

The release artifact contains the Audio, Cursor, Performance, ACE, CEF, and CN patch families in one archive. Release
validation still requires a clean build of every component. Both lanes must preserve archive schema
2: top-level `Wine/` and `DXMT/`, the Wine loader and server, macOS driver, WineMetal bridge, and the
x64/x32 DXMT payloads expected by the launcher.

Runtime flags are parsed inside their owning component. `ARKNIGHTS_RUNTIME_AUDIO_FOLLOW_DEFAULT_OUTPUT`,
`ARKNIGHTS_RUNTIME_ACE_COMPACT`, `ARKNIGHTS_RUNTIME_CEF_COMPAT`, and `ARKNIGHTS_RUNTIME_CN_COMPAT` accept only `0` or `1`;
`ARKNIGHTS_RUNTIME_DXMT_MAX_FRAME_LATENCY` accepts only `1` through `3`. Absent or invalid values preserve
the documented defaults. The ACE gate owns the kernel, dispatcher, Rosetta, and timing routes; the CEF gate
owns descriptor-driven CEF loader preflights, with the CN gate as a legacy fallback only when CEF is absent;
the CN gate also owns the Bilibili window preflights documented in the [patch registry](patch-registry.md#cn).
The performance family contains the unconditional DXMT command-context initialization correction and
a `DXMT_DEBUG`-gated release hot-path reduction for presentation statistics. These changes preserve
debug HUD output and release frame counters; neither changes rendering policy. The launcher selects the remaining flags from the active
client's profile. A profile owns its publisher,
distribution variant, runtime environment overrides, and whether Play must show the ACE warning;
the runtime does not infer compatibility from a publisher name. This keeps a future publisher's ACE
client independent from the Bilibili CN routes while preserving the same component-local defaults.
