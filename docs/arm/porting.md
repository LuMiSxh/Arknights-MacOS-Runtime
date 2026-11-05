# Entitlement-free port

This page lists the Wine changes that let the ARM64 lane run without the cross-architecture
entitlement. The reference is MetalSharp-Wine; its patch numbers refer to `patches/wine/` at the
capture date.

## Baseline

| Item                  | Value                                      |
| --------------------- | ------------------------------------------ |
| Wine source           | `dappermint/winecx`, branch `arm64-1117`   |
| Wine version          | 11.17                                      |
| Commit                | `c8ef4872c1d53120b80aa92185fc7e295d94d092` |
| Reference fork        | `metalsharp/MetalSharp-Wine`, Wine 11.20   |
| Reference patch count | 129                                        |

The reference targets Wine 11.20. WineCX 11.17 carries CodeWeavers changes, so every port needs a
conflict check, a build, and a run test.

## Ported

| Reference | Subject                                       | Location                              |
| --------- | --------------------------------------------- | ------------------------------------- |
| `0003`    | Address space, shared user data, PE consumers | `patches/arm/wine/address-space/`     |
| `0008`    | Canonical-address loads in the signal handler | Same patch                            |
| `0016`    | Skip occupied regions in the free-area search | Same patch                            |
| `0001`    | Loader SDK 12.0 relink                        | `scripts/arm/build.py`                |
| `0004`    | Wow64 registry values name the FEX modules    | `patches/arm/wine/fex/`               |
| —         | Skip Wine Mono                                | `patches/arm/wine/mono/`              |
| —         | ARM64EC unix-call guard                       | `patches/arm/wine/arm64ec-unix-call/` |
| `0003`    | Keep mixed host pages writable                | `patches/arm/wine/wx-pages/`          |
| `0004`    | Synthesize the ARM64 ID registers             | `patches/arm/wine/id-registers/`      |

The address-space patch also adds the 4 GB floor probe and moves the first TEB block above 4 GB. The
`wx-pages` patch carries the `mprotect_exec` half of the reference W^X handling; WineCX already flips
pages in `virtual_handle_fault`. FEX code buffers use `MAP_JIT` through the
[`map-jit`](../../patches/arm/fex/map-jit/README.md) patch. Measure fault behavior from a normal
Terminal; the agent shell suppresses synchronous signals.

## Remaining

| Reference | Subject                                       | Needed for          |
| --------- | --------------------------------------------- | ------------------- |
| `0017`    | Carry `EFlags` AF and DF through ARM64EC      | Game and ACE        |
| `0126`    | Start an x64 thread from a hybrid module      | Game and ACE        |
| `0128`    | Tell the emulator about executable data views | Self-modifying code |

The x86_64 probe prints `fex-ok`. These patches are candidates for the game and ACE.

Patch `0004` sets these values in `loader/wine.inf.in`:

```text
HKLM,Software\Microsoft\Wow64\amd64,,2,"libarm64ecfex.dll"
HKLM,Software\Microsoft\Wow64\x86,,2,"libwow64fex.dll"
```

Packaging can install the modules as `xtajit` aliases instead. Use one method only.

## Loader

The ARM64 loader needs `-platform_version macos,15.0,12.0` to preserve x18. The recorded SDK selects
the kernel's page-fault behavior. The x86_64 loader keeps the current SDK. The 4 GB `__PAGEZERO` stays
in the reference.

## Not ported

| Group                                       | Reason                            |
| ------------------------------------------- | --------------------------------- |
| `0011`, `0019`, and other 4K page work      | Needs the entitlement.            |
| Steam, Epic, Battle.net, Rockstar patches   | Not used by Arknights.            |
| Mullion, VKD3D-Proton, DXVK, WineMetalGL    | This runtime uses DXMT only.      |
| MetalSharp application and tracing controls | Not part of the runtime contract. |

FEX tuning belongs in the client environment, not in Wine patches:

| Variable                  | Effect                                               |
| ------------------------- | ---------------------------------------------------- |
| `FEX_TSOENABLED`          | `1` keeps the x86 memory order model. `0` is faster. |
| `FEX_X87REDUCEDPRECISION` | `0` gives full 80-bit precision.                     |
| `FEX_DISKCACHE`           | Caches translated code on disk.                      |
| `WINEESYNC`, `WINEMSYNC`  | Select the synchronization mode.                     |

Test ACE with TSO enabled first.

## Validation

| Check                 | Expected result                      |
| --------------------- | ------------------------------------ |
| `codesign -dv` loader | Ad-hoc signature, no entitlement.    |
| `vtool -show-build`   | `minos 15.0`, `sdk 12.0`.            |
| `wine cmd /c ver`     | Exit 0 on a fresh prefix.            |
| 64-bit PE under FEX   | Starts and prints its output. Works. |
| Game                  | Reaches the login screen. Not yet.   |

Add one offline test for each contract that a port can break:

- The shared page address is not `0x7ffe0000` when the low region is unavailable.
- The shared page address stays `0x7ffe0000` when the entitlement is present.
- The 4 GB floor is above the loader's Mach-O reservation.
- The emulator registry values name an existing module.
