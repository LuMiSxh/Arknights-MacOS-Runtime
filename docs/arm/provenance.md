# Provenance of the reference ARM64 runtime

This document records the ARM64 runtime that was inspected and the public sources that produce the
same components. The capture is complete; no further data is needed from the installed app.

## Capture context

| Item                          | Value                                        |
| ----------------------------- | -------------------------------------------- |
| Capture date                  | 2026-11-04                                   |
| Host                          | Apple M4, macOS 27.2                         |
| Application support directory | `~/Library/Application Support/Yaagl ZZZ OS` |
| Installed Wine                | Wine 11.18, native ARM64                     |
| Installed DXMT                | ARM64EC build from `dxmt.riverfog7.com`      |

The directory contains the runtime of the Yaagl ZZZ launcher, which is not part of this project. The
capture only identifies the sources and the shape of the runtime.

## Reference Wine release

The launcher stores its selected release in `.storage/wine_tag.neustorage`. The catalog entry has
these values:

| Field                 | Value                                                                               |
| --------------------- | ----------------------------------------------------------------------------------- |
| ID                    | `wine-11-18-arm64-v2`                                                               |
| Name                  | Wine 11.18 ARM64 v2                                                                 |
| Architecture          | `arm64`                                                                             |
| URL                   | `https://web.aws.riverfog7.com/files/wine/releases/wine-11-18-arm64-v2/wine.tar.xz` |
| Size                  | 122178776 bytes                                                                     |
| SHA-256               | `2af994b564d4dac09c1d9d91778b039441d08233ff4e136c8a3b732843d20844`                  |
| Published             | 2026-11-03T06:06:55Z                                                                |
| Minimum macOS         | 26.0                                                                                |
| Backends              | `wined3d`, `dxmt`, `dxvk`                                                           |
| Graphics architecture | `arm64ec`                                                                           |

The installed tree has this shape:

```text
wine/
  bin/                    wine, wineserver
  lib/wine/aarch64-unix/  native arm64 Mach-O modules
  lib/wine/aarch64-windows/ Aarch64 PE modules
  lib/wine/i386-windows/  80386 PE modules for WoW64
  share/wine/
```

The loader is `lib/wine/aarch64-unix/wine.app`, identifier `com.riverfog7.wine`, Team ID
`QNY65H4MK6`, with an embedded provisioning profile.

The launcher rewrites files after extraction: `winemac.so` and the `bin` links have later times than
the archive. The installed tree is not byte-identical to the archive. Do not use it as a build input.

## Reference entitlement

The loader carries `com.apple.developer.cross-architecture-support`. Its `__PAGEZERO` segment has
`vmsize 0x100000000`, and the loader releases it at startup. WineCX needs the release for
`0x7ffe0000`. This project cannot obtain the same profile. Do not copy the reference loader into an
artifact.

## Entitlement availability

The entitlement belongs to the team that owns the provisioning profile. Another team cannot reuse it,
and the signature cannot be transplanted. Apple publishes two variants:

| Entitlement                                                | Account                      |
| ---------------------------------------------------------- | ---------------------------- |
| `com.apple.developer.cross-architecture-support`           | Paid Apple Developer Program |
| `com.apple.developer.cross-architecture-support-unmanaged` | Free developer account       |

Signing:

1. Create an App ID for the Wine loader.
2. Enable the cross-architecture capability on that App ID.
3. Add the provisioning UDID of the Mac to the account.
4. Create a provisioning profile for the App ID.
5. Put the profile in an app bundle with the Wine loader.

The profile names one Mac, so a signed loader is device-bound and cannot be redistributed.
MetalSharp-Wine reports that macOS 27.2 kills a standalone executable that claims the entitlement
without an embedded profile.

A free account cannot reach Certificates, Identifiers & Profiles today. The unmanaged variant is
documented but not reachable. Disabling System Integrity Protection and the entitlement checks at boot
is possible; do not use it for a distributed runtime.

Sources:

- Wine-devel, 2026-08-07, "Wine on ARM64 macOS": both entitlement names and the signing steps.
- `metalsharp/MetalSharp-Wine` README: the bundle requirement and the macOS 27.2 behavior.
- Apple Developer Forums, October 2026: a free Personal Team cannot obtain the entitlement.

## Reference FEX binaries

The installed tree contains two PE modules with FEX code:

| File                                         | Size    | Role                             |
| -------------------------------------------- | ------- | -------------------------------- |
| `lib/wine/aarch64-windows/libarm64ecfex.dll` | 4239360 | x86_64 emulation through ARM64EC |
| `lib/wine/aarch64-windows/libwow64fex.dll`   | 3936256 | i386 emulation through WoW64     |

The runtime also contains the same sizes under the Wine emulator names `xtajit64.dll`
(`libarm64ecfex.dll`) and `xtajit.dll` (`libwow64fex.dll`). The installed `xtajit64.dll` contains FEX
strings, so it is the FEX module and not the Wine stub.

The unix side is `libarm64ecfex.so` and `libwow64fex.so` in `lib/wine/aarch64-unix`. Both are Mach-O
arm64 shared libraries and both export `___wine_unix_call_funcs`, so Wine loads them as unixlibs.

## Reference DXMT build

The launcher stores the DXMT build in `dxmt-builds/ci/build-41419273500/arm64ec`. Its `build.json` has
these values:

| Field         | Value                                      |
| ------------- | ------------------------------------------ |
| Source        | Upstream CI                                |
| CI reference  | `41419273500`                              |
| Commit        | `647b0020ba5764e5593b12407afd76964fa11e20` |
| Created       | 2026-11-02T09:16:22Z                       |
| Architectures | `arm64ec`, `x86`, `x86_64`                 |

The directory contains `d3d10core.dll`, `d3d11.dll`, `dxgi.dll`, `nvapi64.dll`, `nvngx.dll`,
`winemetal.dll`, and `winemetal.so`. The DLLs are ARM64X; `winemetal.so` is Mach-O arm64. `nvapi64.dll`
and `nvngx.dll` are not part of the current Arknights runtime interface. The build files are mirrored
on the launcher CDN and come from the upstream DXMT CI.

## Public sources

| Component             | Repository                                      | Reference                                                              | Notes                                                              |
| --------------------- | ----------------------------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------ |
| WineCX 11.17 ARM64    | `https://github.com/dappermint/winecx`          | Branch `arm64-1117`, commit `c8ef4872c1d53120b80aa92185fc7e295d94d092` | Same fork and version as the current pin.                          |
| WineCX newer ARM64    | `https://github.com/dappermint/winecx`          | Branch `arm64`, commit `82153729ababab1f0b4036d12c8eb7ab099e8b7f`      | Wine 11.16. Adds application identity and icon controls.           |
| FEX                   | `https://github.com/dappermint/FEX`             | Branch `main`, commit `4efc3abc8aca8a0d3a8aca1f153ef6c4299f4426`       | Adds the macOS unixlib helpers.                                    |
| DXMT                  | `https://github.com/3Shain/dxmt`                | Current pin `9839e55f98d4aca103957ee4132d6395a325a9ed`                 | Already contains `build-arm64ec.txt`.                              |
| ARM64 build recipe    | `https://github.com/dappermint/winecx-gptk`     | Directory `arm64/`                                                     | Local recipe with FEX and the loader from a base runtime.          |
| Entitlement-free Wine | `https://github.com/metalsharp/MetalSharp-Wine` | Branch `main`                                                          | Wine 11.20 plus 129 patches. Reference for the address space work. |

WineCX `arm64-1117` includes the writable/executable page flip, the executable-heap fallback, the
D3DMetal hooks on ARM64, client-surface presents, a per-process Metal shader cache, and
`free_pagezero()`. The last function needs the entitlement.

FEX builds the PE modules with llvm-mingw and the unixlibs from `FEXUnixLib.cpp`. The exact commands
are in `metalsharp/MetalSharp-Wine` at `scripts/build-fex.sh`.

## How to reproduce the capture

These read-only commands produced the facts above. Run them against the installed application support
directory and do not run Wine or open the game.

```sh
cat .storage/wine_tag.neustorage
cat dxmt-builds/ci/build-41419273500/arm64ec/build.json
plutil -p wine/lib/wine/aarch64-unix/wine.app/Contents/Info.plist
codesign -d --entitlements :- wine/lib/wine/aarch64-unix/wine.app
otool -l wine/lib/wine/aarch64-unix/wine.app/Contents/MacOS/wine
nm -gU wine/lib/wine/aarch64-unix/libarm64ecfex.so
```

## Gaps and limits

| Gap                                              | Effect                                                               |
| ------------------------------------------------ | -------------------------------------------------------------------- |
| No public `arm64-1118` branch                    | The exact 11.18 build in the reference runtime has no public source. |
| The reference loader is re-signed                | This project cannot reproduce or redistribute it.                    |
| The installed `winemac.so` has a later file time | The reference tree is not a clean build.                             |
| No public CI for the ARM64 WineCX build          | The pipeline must build it from source.                              |
| The FEX build is not wired into this repository  | The pipeline must add the PE and unixlib steps.                      |

## Licenses

| Component                                  | License                                    |
| ------------------------------------------ | ------------------------------------------ |
| Wine and WineCX                            | LGPL-2.1-or-later                          |
| FEX                                        | MIT                                        |
| DXMT at the current pin                    | LGPL-2.1-or-later                          |
| MetalSharp Wine changes                    | LGPL-2.1-or-later, as stated by its README |
| MetalSharp build scripts and documentation | AGPL-3.0                                   |
| Reference Wine loader                      | Proprietary, re-signed by its distributor  |

Port only the Wine changes from MetalSharp-Wine and keep the original commit message and source link in
each patch. Do not copy the build scripts, documentation, or packaging.
