# Architecture

The initial candidate is an overlay build. It verifies and extracts the pinned runtime archive, rebuilds only the patched Wine and DXMT components from their exact source commits, and replaces the matching files in a new artifact. It is not a release build: unchanged base components keep the upstream provenance and deployment target.

```text
runtime.lock.json -> verified source checkouts -> ordered patch families
                 -> component builds -> verified base copy -> overlay
                 -> structural report -> canary artifact
```

The release artifact contains the patched x86_64 components. Release validation requires a clean build of every component. Both lanes keep archive schema 2: top-level `Wine/` and `DXMT/`, the Wine loader and server, the macOS driver, the WineMetal bridge, and the DXMT payload.

## 64-bit-only clean build

Since runtime 0.7.0:

- Wine uses `--enable-archs=x86_64`: no `lib/wine/i386-windows`, no `DXMT/x32`.
- Wine uses `--without-gstreamer --without-ffmpeg`: no GStreamer plugins, FFmpeg, or codec libraries.
- The build derives the bundled library closure from the Mach-O references of the Wine unix modules.
- `Wine/bin/wine64`, `wine`, and `wineloader` are symlinks to `lib/wine/x86_64-unix/wine`, the single loader. `Arknights` points at `wine64`.
- `validate_runtime.py --require-64-bit-only` rejects the removed payloads in clean builds. Overlay candidates inherit them and are exempt.

## Runtime flags

Each patch parses only its own gate. Accepted values and defaults are in the [Wine patch table](../patches/wine/README.md). A default-on gate is on when its variable is unset or exactly `1`; any other value turns it off. A default-off gate is on only for exactly `1`.

- ACE gate: Kernel, dispatcher, Rosetta, and timing routes.
- CEF gate: Descriptor-driven CEF loader preflights.
- CN gate: Bilibili window preflights ([patch registry](patch-registry.md#cn)).
- Fullscreen gate: Native fullscreen Space for a screen-sized game window ([patch registry](patch-registry.md#fullscreen)).
- Hardware Cursor gate: Hides the exact Yostar/TW or Bilibili CN cursor asset basename in shared Wine path resolution, so open, attribute, and create-if-missing calls agree.

The performance family has a `DXMT_DEBUG`-gated reduction of release presentation statistics. It keeps the debug HUD output and release frame counters. It does not change rendering policy.

The launcher selects the remaining flags from the profile of the active client. A profile owns the publisher, distribution variant, runtime environment overrides, and the ACE warning on Play. The runtime never infers compatibility from a publisher name, so a future ACE client stays independent from the Bilibili CN routes.

## Native ARM64 target

`runtime.lock.json` declares a second target, `native-arm64`. It runs a native ARM64 Wine runtime without Rosetta, with FEX for x86_64 programs and DXMT ARM64EC for Direct3D 10 and 11. The target is external: the Wine payload is built in [wine-build-new](https://github.com/riverfog7/wine-build-new), and this repository builds DXMT, repacks the tree, and validates it. The lane requires macOS 26.0 or newer. `rosetta-x86_64` stays the default. See [the ARM64 documentation](arm/README.md).
