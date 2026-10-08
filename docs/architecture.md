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

The release artifact contains the Audio, Cursor, Hardware Cursor, Performance, ACE, CEF, and CN patch
families in one archive. Release validation still requires a clean build of every component. Both
lanes must preserve archive schema 2: top-level `Wine/` and `DXMT/`, the Wine loader and server,
macOS driver, WineMetal bridge, and x64 DXMT payload expected by the launcher.

Since runtime 0.7.0 the clean build is 64-bit only. Wine is configured with `--enable-archs=x86_64`,
so the archive has no `lib/wine/i386-windows` and no `DXMT/x32`. Wine is also configured with
`--without-gstreamer --without-ffmpeg`, so no GStreamer plugins, FFmpeg, or codec libraries are
bundled. The bundled library closure is derived from the Mach-O references of the Wine unix modules
rather than from a fixed list. `Wine/bin/wine64`, `wine`, and `wineloader` are symlinks to
`lib/wine/x86_64-unix/wine`, because an x86_64-only Wine build installs a single loader; `Arknights`
points at `wine64`. `validate_runtime.py --require-64-bit-only` enforces the absence of the removed
payloads for clean builds; overlay candidates inherit them from the pinned base and are exempt.

Runtime flags are parsed inside their owning component. `ARKNIGHTS_RUNTIME_AUDIO_FOLLOW_DEFAULT_OUTPUT`,
`ARKNIGHTS_RUNTIME_HARDWARE_CURSOR`, `ARKNIGHTS_RUNTIME_ACE_COMPACT`, `ARKNIGHTS_RUNTIME_CEF_COMPAT`,
and `ARKNIGHTS_RUNTIME_CN_COMPAT` accept only `0` or `1`;
`ARKNIGHTS_RUNTIME_DXMT_MAX_FRAME_LATENCY` accepts only `0` through `3`. Absent or invalid values preserve
the documented defaults. The ACE gate owns the kernel, dispatcher, Rosetta, and timing routes; the CEF gate
owns descriptor-driven CEF loader preflights, with the CN gate as a legacy fallback only when CEF is absent;
the CN gate also owns the Bilibili window preflights documented in the [patch registry](patch-registry.md#cn).
The hardware-cursor gate hides the exact Yostar/TW or Bilibili CN cursor asset basename during shared
Wine path resolution, so open and attribute queries observe the same result and create-if-missing
calls cannot recreate either asset.
The performance family contains the unconditional DXMT command-context initialization correction and
a `DXMT_DEBUG`-gated release hot-path reduction for presentation statistics. These changes preserve
debug HUD output and release frame counters; neither changes rendering policy. The launcher selects the remaining flags from the active
client's profile. A profile owns its publisher,
distribution variant, runtime environment overrides, and whether Play must show the ACE warning;
the runtime does not infer compatibility from a publisher name. This keeps a future publisher's ACE
client independent from the Bilibili CN routes while preserving the same component-local defaults.
