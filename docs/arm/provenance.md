# Provenance of the reference ARM64 runtime

This document records the ARM64 runtime that was inspected on the reference Mac.
It also records the public sources that produce the same components.
The capture is complete. No further data is needed from the installed app.

## Capture context

| Item                          | Value                                        |
| ----------------------------- | -------------------------------------------- |
| Capture date                  | 2026-11-04                                   |
| Host                          | Apple M4, macOS 27.2                         |
| Application support directory | `~/Library/Application Support/Yaagl ZZZ OS` |
| Installed Wine                | Wine 11.18, native ARM64                     |
| Installed DXMT                | ARM64EC build from `dxmt.riverfog7.com`      |

The directory contains the runtime of the Yaagl ZZZ launcher.
The launcher is not part of this project.
This capture only identifies the sources and the shape of the runtime.

## Reference Wine release

The launcher stores its selected release in `.storage/wine_tag.neustorage`.
The catalog entry has these values:

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

The catalog is at `https://web.aws.riverfog7.com/files/wine/catalog.json`.

The installed tree has this shape:

```text
wine/
  bin/
    wine -> ../lib/wine/aarch64-unix/wine.app/Contents/MacOS/wine
    wineserver
  lib/wine/
    aarch64-unix/       # native arm64 Mach-O modules
    aarch64-windows/    # Aarch64 PE modules
    i386-windows/       # 80386 PE modules for WoW64
  share/wine/
```

The loader is an app bundle at `lib/wine/aarch64-unix/wine.app`.
Its identifier is `com.riverfog7.wine`.
The bundle has a Team ID of `QNY65H4MK6` and an embedded provisioning profile.

The launcher rewrites files after it extracts the archive.
The file time of `winemac.so` is 13:07, while the archive files are 06:45 to 06:46.
The `bin` symbolic links are at 14:53.
The installed runtime is therefore not byte-identical to the archive.
Do not use the installed tree as a build input.

## Reference entitlement

The loader signature carries this entitlement:

```xml
<key>com.apple.developer.cross-architecture-support</key>
<true/>
```

The Team ID is `QNY65H4MK6`.
The loaded image has a `__PAGEZERO` segment with `vmsize` `0x100000000`.
The loader releases this segment at startup.
The WineCX ARM64 code requires the release for the shared user data page at `0x7ffe0000`.
See [architecture](architecture.md) for the address space details.

This project cannot obtain the same profile.
Do not copy the reference loader into an artifact.

## Reference FEX binaries

The installed tree contains two PE modules with FEX code:

| File                                         | Size    | Role                             |
| -------------------------------------------- | ------- | -------------------------------- |
| `lib/wine/aarch64-windows/libarm64ecfex.dll` | 4239360 | x86_64 emulation through ARM64EC |
| `lib/wine/aarch64-windows/libwow64fex.dll`   | 3936256 | i386 emulation through WoW64     |

The runtime also contains files with the same sizes under the Wine emulator names:

| Alias          | Source              |
| -------------- | ------------------- |
| `xtajit64.dll` | `libarm64ecfex.dll` |
| `xtajit.dll`   | `libwow64fex.dll`   |

Wine reads these names from `HKLM\Software\Microsoft\Wow64`.
The installed `xtajit64.dll` contains FEX strings, so it is the FEX module and not the Wine stub.

The archive contains the unix side in `lib/wine/aarch64-unix`:

| File               | Role                                       |
| ------------------ | ------------------------------------------ |
| `libarm64ecfex.so` | Wine unixlib bridge for the ARM64EC module |
| `libwow64fex.so`   | Wine unixlib bridge for the WoW64 module   |

Both files are Mach-O arm64 shared libraries.
Both export `___wine_unix_call_funcs`, so Wine loads them as unixlibs.

## Reference DXMT build

The launcher stores the DXMT build in `dxmt-builds/ci/build-41419273500/arm64ec`.
The adjacent `build.json` has these values:

| Field         | Value                                      |
| ------------- | ------------------------------------------ |
| Source        | Upstream CI                                |
| CI reference  | `41419273500`                              |
| Commit        | `647b0020ba5764e5593b12407afd76964fa11e20` |
| Created       | 2026-11-02T09:16:22Z                       |
| Architectures | `arm64ec`, `x86`, `x86_64`                 |

The `arm64ec` directory contains:

```text
d3d10core.dll
d3d11.dll
dxgi.dll
nvapi64.dll
nvngx.dll
winemetal.dll
winemetal.so
```

The `file` command reports the DLL files as PE32+ Aarch64.
DXMT builds them with the `-marm64x` flag, so they are ARM64X hybrids.
`winemetal.so` is a Mach-O arm64 shared library.
`nvapi64.dll` and `nvngx.dll` are not part of the current Arknights runtime interface.

The build files are mirrored on the launcher CDN.
The same files come from the upstream DXMT CI.

## Public sources

| Component             | Repository                                      | Reference                                                              | Notes                                                                 |
| --------------------- | ----------------------------------------------- | ---------------------------------------------------------------------- | --------------------------------------------------------------------- |
| WineCX 11.17 ARM64    | `https://github.com/dappermint/winecx`          | Branch `arm64-1117`, commit `c8ef4872c1d53120b80aa92185fc7e295d94d092` | Same fork and version as the current pin. Carries the ARM64 fixes.    |
| WineCX newer ARM64    | `https://github.com/dappermint/winecx`          | Branch `arm64`, commit `82153729ababab1f0b4036d12c8eb7ab099e8b7f`      | Wine 11.16. Adds application identity and icon controls.              |
| FEX                   | `https://github.com/dappermint/FEX`             | Branch `main`, commit `4efc3abc8aca8a0d3a8aca1f153ef6c4299f4426`       | Adds the macOS unixlib helpers.                                       |
| DXMT                  | `https://github.com/3Shain/dxmt`                | Current pin `9839e55f98d4aca103957ee4132d6395a325a9ed`                 | The pinned commit already contains `build-arm64ec.txt`.               |
| ARM64 build recipe    | `https://github.com/dappermint/winecx-gptk`     | Directory `arm64/`                                                     | Local recipe. It carries FEX and the loader from a base runtime.      |
| Entitlement-free Wine | `https://github.com/metalsharp/MetalSharp-Wine` | Branch `main`                                                          | Wine 11.20 plus 129 patches. Reference for the address space changes. |

### WineCX ARM64 commits

The `arm64-1117` branch contains these ARM64 changes:

| Commit     | Change                                                      |
| ---------- | ----------------------------------------------------------- |
| `6baebec9` | Flip a page between writable and executable on ARM64 macOS. |
| `29a850ed` | Use a plain heap when an executable heap is refused.        |
| `68696f0e` | Build the D3DMetal hooks on ARM64 for DXMT.                 |
| `69f47aea` | Report client surface presents on ARM64.                    |
| `3c86b439` | Give each process its own Metal shader cache.               |

The branch also contains `free_pagezero()`.
That function releases the low 4 GB reservation and needs the entitlement.

### FEX build inputs

The FEX repository provides the Wine bridges:

| Path                                    | Role                                   |
| --------------------------------------- | -------------------------------------- |
| `Source/Windows/ARM64EC/`               | ARM64EC frontend (`libarm64ecfex`)     |
| `Source/Windows/WOW64/`                 | WoW64 frontend (`libwow64fex`)         |
| `Source/Windows/UnixLib/FEXUnixLib.cpp` | Unixlib bridge for both frontends      |
| `Data/nix/WineOnArm/shell.nix`          | ARM64EC cross file and toolchain names |

The FEX build produces the PE modules with llvm-mingw.
The unixlibs are two small compilations of `FEXUnixLib.cpp` with the host compiler.
The exact commands are in `metalsharp/MetalSharp-Wine` at `scripts/build-fex.sh`.

## How to reproduce the capture

These read-only commands produced the facts above.
Run them against the installed application support directory.

```sh
cat .storage/wine_tag.neustorage
cat dxmt-builds/ci/build-41419273500/arm64ec/build.json
plutil -p wine/lib/wine/aarch64-unix/wine.app/Contents/Info.plist
codesign -d --entitlements :- wine/lib/wine/aarch64-unix/wine.app
otool -l wine/lib/wine/aarch64-unix/wine.app/Contents/MacOS/wine
file wine/lib/wine/aarch64-unix/wine.app/Contents/MacOS/wine \
     wine/lib/wine/aarch64-unix/ntdll.so \
     wine/lib/wine/aarch64-windows/ntdll.dll
nm -gU wine/lib/wine/aarch64-unix/libarm64ecfex.so
```

Do not run Wine and do not open the game for this capture.
The capture reads files only.

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

Port only the Wine changes from MetalSharp-Wine.
Keep the original commit message and the source link in each ported patch.
Do not copy the build scripts, the documentation, or the packaging.
