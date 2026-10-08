# Architecture

The initial candidate is an overlay build. It verifies and extracts the pinned runtime archive, rebuilds only the patched Wine and DXMT components from their exact source commits, and replaces the matching files in a new artifact. It is not a release build: unchanged base components keep the upstream provenance and deployment target.

```text
runtime.lock.json -> verified source checkouts -> ordered patch families
                 -> component builds -> verified base copy -> overlay
                 -> structural report -> canary artifact
```

The release artifact contains all seven patch families. Release validation requires a clean build of every component. Both lanes keep archive schema 2: top-level `Wine/` and `DXMT/`, the Wine loader and server, the macOS driver, the WineMetal bridge, and the x64 DXMT payload.

## 64-bit-only clean build

Since runtime 0.7.0:

- Wine uses `--enable-archs=x86_64`: no `lib/wine/i386-windows`, no `DXMT/x32`.
- Wine uses `--without-gstreamer --without-ffmpeg`: no GStreamer plugins, FFmpeg, or codec libraries.
- The build derives the bundled library closure from the Mach-O references of the Wine unix modules.
- `Wine/bin/wine64`, `wine`, and `wineloader` are symlinks to `lib/wine/x86_64-unix/wine`, the single loader. `Arknights` points at `wine64`.
- `validate_runtime.py --require-64-bit-only` rejects the removed payloads in clean builds. Overlay candidates inherit them and are exempt.

## Runtime flags

Each owning component parses its own flags. Accepted values and defaults are in the [README](../README.md#patch-families-and-runtime-controls). An absent or invalid value keeps the default.

- ACE gate: Kernel, dispatcher, Rosetta, and timing routes.
- CEF gate: Descriptor-driven CEF loader preflights.
- CN gate: Bilibili window preflights ([patch registry](patch-registry.md#cn)); legacy CEF fallback only when CEF is absent.
- Hardware Cursor gate: Hides the exact Yostar/TW or Bilibili CN cursor asset basename in shared Wine path resolution, so open, attribute, and create-if-missing calls agree.

The performance family has an unconditional DXMT command-context initialization correction and a `DXMT_DEBUG`-gated reduction of release presentation statistics. Both keep the debug HUD output and release frame counters. Neither changes rendering policy.

The launcher selects the remaining flags from the profile of the active client. A profile owns the publisher, distribution variant, runtime environment overrides, and the ACE warning on Play. The runtime never infers compatibility from a publisher name, so a future ACE client stays independent from the Bilibili CN routes.
