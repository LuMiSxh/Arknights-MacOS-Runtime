# ARM64 experiment results

This page records what was tried, what worked, and what failed.
It is the evidence behind the decisions in the other ARM64 documents.
Last updated: 2026-11-04.

## Entitlement

| Attempt                                       | Result                                                                                             |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Ad-hoc loader with the cross-arch entitlement | AMFI kills the process. The entitlement needs a provisioning profile for the same team and App ID. |
| Signed MetalSharp loader                      | Boots, but the profile is device-bound and cannot be redistributed. It never maps below 4 GB.      |
| Notarization or a paid account                | Does not grant the entitlement. The profile still names one Mac.                                   |

Decision: no entitlement. Port the address-space changes instead.

## Reference runtime

MetalSharp-Wine 5.0 boots a scratch prefix on macOS 27.2.
It never maps the low 4 GB.
It is Wine 5.0 and does not provide the current WineCX or DXMT behavior.

## Shared user data

| Attempt                                               | Result                                                               |
| ----------------------------------------------------- | -------------------------------------------------------------------- |
| Map `KUSER_SHARED_DATA` at `0x7ffe0000`               | Fails with `c0000017`; macOS keeps the low 4 GB as pagezero.         |
| Deallocate the loader `__PAGEZERO`                    | Fails without the entitlement.                                       |
| Relocate the page and emulate canonical-address loads | Works. Native ARM64 `wine cmd /c ver` reaches the Wine message loop. |

The port covers reference patches `0003`, `0008`, and `0016`.
The write and execute hunks are not ported; WineCX 11.17 already flips those pages.

## x18

macOS clears x18 on syscalls and on fresh page-fault returns.
The kernel preserves x18 only when the main executable records an SDK of 12.0 or older.
The loader is linked with `-platform_version macos,15.0,12.0`.
`vtool` shows `minos 15.0 / sdk 12.0`.
This is an ARM64-only requirement; the x86_64 loader stays on the current SDK (`27.0`).

## The 4 GB floor

macOS reserves the main executable's Mach-O region just above 4 GB.
`mach_vm_map` rejects the whole range, including unmapped holes, with `KERN_INVALID_ADDRESS`.
Wine's first thread data and some stacks used `limit_4g` as a floor, so they failed.
The patch probes upward from 4 GB and stores the first mappable address.
`wine cmd /c ver` then runs.

The loader's Mach-O mapping is not visible to `mach_vm_region`, so a region-skip alone is not enough.
The probe uses `anon_mmap_tryfixed()` and keeps the first successful page.

## Mono

Wine's `mscoree` registration installs Wine Mono on every new prefix.
The support package runs 32-bit and ARM64EC helpers.
The 32-bit helpers need the low 4 GB and fail without the entitlement.
Wine retries the install and can open a download dialog.

The ARM64 lane now skips the install in `install_wine_mono()`.
`wine cmd /c ver` on a fresh prefix exits 0 without `WINEDLLOVERRIDES`.
Arknights does not use .NET.

## x86_64 under FEX

A minimal x86_64 PE loads at `0x140000000` and then stops before entry.
There is no output after the `Loaded ... native` line.

Wine's `wine.inf` now points `Wow64\amd64` at `libarm64ecfex.dll` and
`Wow64\x86` at `libwow64fex.dll`.
A fresh prefix writes both values.
The PE still stops at the same point, so the wiring is necessary but not sufficient.

A fresh prefix with the x86 value also reports a missing 32-bit
`C:\windows\syswow64\rundll32.exe`.
That is expected for a 64-bit-only lane and does not affect the native ARM64
`cmd /c ver` start.

This is the current boundary.
The likely missing pieces are the reference ARM64EC patches:

- `0004`/`0017`: ID registers and `EFlags`.
- `0126`/`0128`: hybrid entry points and executable data views.

The lane does not run the game yet.

## Window chrome

The x86_64 loader records SDK 27.0, so the game window keeps the current macOS decorations.
The ARM64 loader records SDK 12.0, which would select the legacy decorations.

Prototype: a client dylib interposes `dyld_get_program_sdk_version()` and returns the running OS version.
Injected through `DYLD_INSERT_LIBRARIES`, AppKit calls it during window creation and reads the current version.
The dylib is not shipped.
The x86_64 lane does not need it.

## Summary

| Item                   | State                            |
| ---------------------- | -------------------------------- |
| Native ARM64 Wine boot | Works                            |
| Shared user data       | Relocated                        |
| Mono                   | Skipped                          |
| x86_64 under FEX       | Hangs before entry               |
| Game                   | Not started                      |
| ACE                    | Not tested                       |
| Window chrome          | Legacy on ARM; bridge prototyped |
