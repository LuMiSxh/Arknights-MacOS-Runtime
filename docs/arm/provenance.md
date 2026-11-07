# Provenance of the ARM64 runtime

This document records the shipped ARM64 runtime, its build repository, and the reference capture that
established the component set.

## Shipped Wine artifact

The ARM64 release uses the external Wine artifact that [`runtime.lock.json`](../../runtime.lock.json)
pins.

| Field         | Value                                                                  |
| ------------- | ---------------------------------------------------------------------- |
| Release       | `wine-11-18-arm64-v5`                                                  |
| SHA-256       | `059e9a88e008493ea6bd3fb93334298b6f7f730b554f5a9048a0834eeea9880a`     |
| Wine source   | Upstream Wine 11.18, commit `7b3fff76fa5178f6ce0141b2c776afa2a822f101` |
| Minimum macOS | 26.0                                                                   |
| Builder       | [wine-build-new](https://github.com/riverfog7/wine-build-new)          |

The artifact layout is:

```text
wine/                       # lowercase
  bin/wine -> wine.app/...
  bin/wineserver
  lib/wine/aarch64-unix/
  lib/wine/aarch64-windows/
  lib/wine/i386-windows/
  share/licenses/           # Wine ARM64EC, FEX, Mesa
```

The archive has no DXMT, no `winemetal.so`, no `wine64`, no `Arknights` link, and no
`WINEPRELOADERAPPNAME`. `scripts/arm64/assemble.py` adds `Wine/bin/wine64`, `Wine/bin/Arknights`,
the DXMT payload, and the WineMetal modules outside the signed `wine.app`.

## Signing

The `wine.app` loader is Developer ID signed by team `QNY65H4MK6`, identifier
`com.riverfog7.wine`, with `com.apple.developer.cross-architecture-support` and a distribution
profile. Adding files outside the bundle does not invalidate that signature. The wrapper keeps the
loader byte-identical. Do not re-sign, relink, or replace the loader. Ad-hoc sign only wrapper-added
unsigned files; the release workflow signs the locally built `winemetal.so`.

## DXMT

The release workflow builds DXMT from `sources.dxmt` at commit
`647b0020ba5764e5593b12407afd76964fa11e20` with `MACOSX_DEPLOYMENT_TARGET=26.0`. It also builds a
minimal Wine tree from `sources.wine` for the import libraries. That build tree is a build
dependency and is never shipped. The macOS driver `winemac.so` comes from the external tree. The old
external `dxmt-experimental-v1` artifact is not used.

## Credit

The signed ARM64 Wine runtime is built in the
[wine-build-new](https://github.com/riverfog7/wine-build-new) workspace. The Arknights patch export
is in the same repository. Credit only the repository root.

## Reference capture

The component set comes from a read-only capture of the Yaagl ZZZ launcher on 2026-11-04. The
capture identifies the sources and the shape of a working runtime. It is not a build input.

| Item                          | Value                                        |
| ----------------------------- | -------------------------------------------- |
| Capture date                  | 2026-11-04                                   |
| Host                          | Apple M4, macOS 27.2                         |
| Application support directory | `~/Library/Application Support/Yaagl ZZZ OS` |
| Installed Wine                | Wine 11.18, native ARM64                     |
| Installed DXMT                | ARM64EC build from the upstream DXMT CI      |

### Reference Wine release

The launcher stores its selected release in `.storage/wine_tag.neustorage`. The captured release has
these values:

| Field                 | Value                     |
| --------------------- | ------------------------- |
| ID                    | `wine-11-18-arm64-v2`     |
| Architecture          | `arm64`                   |
| Size                  | 122178776 bytes           |
| Minimum macOS         | 26.0                      |
| Backends              | `wined3d`, `dxmt`, `dxvk` |
| Graphics architecture | `arm64ec`                 |

The installed tree has this shape:

```text
wine/
  bin/                    wine, wineserver
  lib/wine/aarch64-unix/  native arm64 Mach-O modules
  lib/wine/aarch64-windows/ Aarch64 PE modules
  lib/wine/i386-windows/  80386 PE modules for WoW64
  share/wine/
```

The launcher rewrites files after extraction: `winemac.so` and the `bin` links have later times than
the archive. The installed tree is not byte-identical to the archive. Do not use it as a build input.

### Reference entitlement

The reference loader carries `com.apple.developer.cross-architecture-support`. Its `__PAGEZERO`
segment has `vmsize 0x100000000`, and the loader releases it at startup. The entitlement belongs to
the team that owns the provisioning profile. Another team cannot reuse it, and the signature cannot
be transplanted. Do not copy the reference loader into an artifact.

### Reference FEX binaries

The reference tree contains two PE modules with FEX code:

| File                                         | Role                             |
| -------------------------------------------- | -------------------------------- |
| `lib/wine/aarch64-windows/libarm64ecfex.dll` | x86_64 emulation through ARM64EC |
| `lib/wine/aarch64-windows/libwow64fex.dll`   | i386 emulation through WoW64     |

The unix side is `libarm64ecfex.so` and `libwow64fex.so` in `lib/wine/aarch64-unix`. Both are Mach-O
arm64 shared libraries and both export `___wine_unix_call_funcs`, so Wine loads them as unixlibs.

## Reference sources

| Component             | Repository                                      | Reference                                         | Notes                                       |
| --------------------- | ----------------------------------------------- | ------------------------------------------------- | ------------------------------------------- |
| Upstream Wine 11.18   | `https://gitlab.winehq.org/wine/wine`           | Commit `7b3fff76fa5178f6ce0141b2c776afa2a822f101` | Shipped Wine payload.                       |
| FEX 2610              | `https://github.com/FEX-Emu/FEX`                | Commit `14c92681f4d62cf84d901460e0358de09c8847a7` | Pinned in the ARM64 target.                 |
| DXMT                  | `https://github.com/3Shain/dxmt`                | Commit `647b0020ba5764e5593b12407afd76964fa11e20` | Built in the release workflow.              |
| Patch export          | `https://github.com/riverfog7/wine-build-new`   | Directory `patches/`                              | ARM64 changes that the external build uses. |
| Entitlement-free Wine | `https://github.com/metalsharp/MetalSharp-Wine` | Branch `main`                                     | Reference for the address-space work.       |

## How to reproduce the capture

These read-only commands produced the facts above. Run them against the installed application support
directory and do not run Wine or open the game.

```sh
cat .storage/wine_tag.neustorage
plutil -p wine/lib/wine/aarch64-unix/wine.app/Contents/Info.plist
codesign -d --entitlements :- wine/lib/wine/aarch64-unix/wine.app
otool -l wine/lib/wine/aarch64-unix/wine.app/Contents/MacOS/wine
nm -gU wine/lib/wine/aarch64-unix/libarm64ecfex.so
```

## Limits

| Limit                              | Effect                                                              |
| ---------------------------------- | ------------------------------------------------------------------- |
| No public signed loader            | This repository cannot reproduce or redistribute the reference app. |
| The installed reference is patched | The reference tree is not a clean build.                            |
| The signed loader is external      | This repository pins the released artifact and never re-signs it.   |

## Licenses

| Component                                  | License                                    |
| ------------------------------------------ | ------------------------------------------ |
| Wine and WineCX                            | LGPL-2.1-or-later                          |
| FEX                                        | MIT                                        |
| DXMT at the current pin                    | LGPL-2.1-or-later                          |
| MetalSharp Wine changes                    | LGPL-2.1-or-later, as stated by its README |
| MetalSharp build scripts and documentation | AGPL-3.0                                   |

Port only the Wine changes from MetalSharp-Wine and keep the original commit message and source link in
each patch. Do not copy the build scripts, documentation, or packaging.
