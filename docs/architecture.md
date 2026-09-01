# Architecture

Arknights MacOS Runtime owns immutable input pins, patch provenance, build orchestration, candidate validation, and
release artifacts. Arknights Client owns runtime selection, checksum verification, typed user settings,
prefix isolation, rollback, localization, and the final game canary.

The first private candidate is deliberately an overlay build: it verifies and extracts the pinned
runtime archive, rebuilds only patched Wine/DXMT components from their exact source commits, and
replaces matching files in a new artifact. This shortens feedback for audio, cursor, and dormant CN
experiments. It does not qualify as a release build because unchanged base components still inherit
the upstream artifact's provenance and macOS deployment target.

```text
runtime.lock.json -> verified source checkouts -> ordered patch families
                 -> component builds -> verified base copy -> overlay
                 -> structural report -> private canary artifact
```

Release promotion later replaces the overlay lane with a clean build of every component. Both lanes
must preserve archive schema 2: top-level `Wine/` and `DXMT/`, the Wine loader and server, macOS
driver, WineMetal bridge, and the x64/x32 DXMT payloads expected by the launcher.

Runtime flags are parsed inside their owning component. `ARKNIGHTS_RUNTIME_AUDIO_FOLLOW_DEFAULT_OUTPUT` and
`ARKNIGHTS_RUNTIME_CN_COMPAT` accept only `0` or `1`; `ARKNIGHTS_RUNTIME_DXMT_MAX_FRAME_LATENCY` accepts only `1` through
`3`. No master switch exists.
