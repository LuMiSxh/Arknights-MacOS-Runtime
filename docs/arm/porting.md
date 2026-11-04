# Entitlement-free port

This document lists the changes that make WineCX ARM64 run without the cross-architecture entitlement.
The reference is MetalSharp-Wine.
Its patch numbers refer to `patches/wine/` in that repository at the capture date.

## Baseline

| Item                  | Value                                      |
| --------------------- | ------------------------------------------ |
| Wine source           | `dappermint/winecx`, branch `arm64-1117`   |
| Wine version          | 11.17                                      |
| Commit                | `c8ef4872c1d53120b80aa92185fc7e295d94d092` |
| Reference fork        | `metalsharp/MetalSharp-Wine`, Wine 11.20   |
| Reference patch count | 129                                        |

The reference patches are written against Wine 11.20.
WineCX has CodeWeavers changes that upstream Wine does not have.
Every port needs a conflict check, a build, and a run test.

## Order of work

The unmodified WineCX ARM64 build needs the entitlement before it can start any program.
Do not start the lane with a run test of the unmodified build.

1. Port the address space patches.
2. Build with an ad-hoc signature.
3. Run a 64-bit program without the entitlement.
4. Add the remaining compatibility patches.
5. Run the game canary.

## Address space patches

These patches remove the entitlement dependency.

| MetalSharp patch | Subject                                                          | Files in the reference                                                                                | Priority    |
| ---------------- | ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ----------- |
| 0003             | Run on ARM64 macOS without low 4 GB remapping and with 16K pages | `ntdll/unix/virtual.c`, `ntdll/unix/signal_arm64.c`, `ntdll/thread.c`, `ntdll/loader.c`, PE consumers | Required    |
| 0005             | Probe for the low 4 GB before mapping the shared user data       | `ntdll/unix/virtual.c`                                                                                | Required    |
| 0008             | Emulate `LDAPUR` loads from the canonical shared address         | `ntdll/unix/signal_arm64.c`                                                                           | Required    |
| 0016             | Skip occupied regions when searching for free memory             | `ntdll/unix/virtual.c`                                                                                | Required    |
| 0018             | Use the low 4 GB when the process has the entitlement            | `ntdll/unix/virtual.c`                                                                                | Recommended |
| 0117             | Keep 4 GB to 8 GB free for 64-bit images                         | `loader/main.c`, `ntdll/unix/virtual.c`                                                               | Conditional |
| 0118             | Revert patch 0117                                                | Same                                                                                                  | Conditional |

Patch 0003 also publishes the shared page address to the PE side.
The PE consumers are `kernel32`, `kernelbase`, and `win32u`.
The unix side gains `ntdll_get_user_shared_data()`, and `ddk/wdm.h` declares the new address.

Patch 0117 is only needed for very large images without relocations.
Test the game first. Port it only if the loader reports a conflicting address.

## Memory protection patches

Evaluate the existing WineCX write and execute flip before these ports.
The WineCX commit `6baebec9` already flips a page on the CodeWeavers fault path.
The MetalSharp-Wine patches cover the complete case.

| MetalSharp patch | Subject                                                                  | Priority                                               |
| ---------------- | ------------------------------------------------------------------------ | ------------------------------------------------------ |
| 0006             | Do not request host execute permission for emulated x86 images           | Required if the host refuses `PROT_EXEC` on data pages |
| 0007             | Emulate stores into a write and execute host page from code in that page | Required for self-modifying code                       |
| 0010             | Restore execute permission in `NtFlushInstructionCache`                  | Required for JIT code                                  |
| 0013             | Keep write protection of executable pages exact within a 16K host page   | Required                                               |
| 0015             | Do not apply write exceptions to ARM64EC allocations                     | Recommended                                            |

## ARM64EC and FEX patches

| MetalSharp patch | Subject                                                         | Priority                         |
| ---------------- | --------------------------------------------------------------- | -------------------------------- |
| 0004             | Synthesize ARM64 ID registers, default Wow64 to the FEX modules | Required for the ID registers    |
| 0017             | Carry `EFlags` AF and DF through ARM64EC contexts               | Required                         |
| 0126             | Start an x64 thread from a hybrid module on its x64 export      | Required for hybrid entry points |
| 0128             | Tell the emulator about executable data views                   | Required for self-modifying code |

Patch 0004 changes `loader/wine.inf.in` in two places:

```text
HKLM,Software\Microsoft\Wow64\amd64,,2,"libarm64ecfex.dll"
HKLM,Software\Microsoft\Wow64\x86,,2,"libwow64fex.dll"
```

Packaging can install the FEX modules under the `xtajit` names instead.
Use one method only. Do not ship both a registry change and duplicate files.

## Loader patch

MetalSharp-Wine patch 0001 has three parts:

| Part                              | Purpose                                     |
| --------------------------------- | ------------------------------------------- |
| `-platform_version` build version | Preserve `x18` across kernel transitions.   |
| 4 GB `__PAGEZERO`                 | Give the release code a segment to find.    |
| CGL OpenGL                        | Build without X11 or EGL development files. |

Port the platform version and the pagezero part.
Check whether the CGL OpenGL part is needed for the WineCX build.
WineCX already configures the loader without X11.

## Patches to leave out

| Patch group                                               | Reason                                      |
| --------------------------------------------------------- | ------------------------------------------- |
| 0011, 0019 and other 4K page work                         | Needs the entitlement.                      |
| 0020 and later compatibility patches                      | They serve other games and other launchers. |
| Steam, Epic, Battle.net, Rockstar patches                 | Not used by Arknights.                      |
| Mullion, VKD3D-Proton, DXVK, WineMetalGL routing          | This runtime uses DXMT only.                |
| MetalSharp application, environment, and tracing controls | Not part of the runtime contract.           |

The FEX defaults in patch 0063 and patches 0066 to 0068, 0073, and 0078 are useful as reference.
Prefer environment variables in the client over Wine patches:

| Variable                  | Effect                                               |
| ------------------------- | ---------------------------------------------------- |
| `FEX_TSOENABLED`          | `1` keeps the x86 memory order model. `0` is faster. |
| `FEX_X87REDUCEDPRECISION` | `0` gives full 80-bit precision.                     |
| `FEX_DISKCACHE`           | Caches translated code on disk.                      |
| `WINEESYNC`, `WINEMSYNC`  | Select the synchronization mode.                     |

Test ACE with TSO enabled first.
ACE checks timing and may reject an emulator that reorders memory operations.

## Port requirements

Each ported patch must keep:

- The original author.
- The original commit message.
- The source link to the MetalSharp-Wine commit.
- The license note.

Add a header line that names the source and the purpose.
Do not copy MetalSharp build scripts, packaging, or documentation.

The Wine changes are LGPL-2.1-or-later.
The MetalSharp repository's own material is AGPL-3.0.
Keep the two separate.

## Validation

| Check                        | Expected result                          |
| ---------------------------- | ---------------------------------------- |
| `codesign -dv` on the loader | Ad-hoc signature, no entitlement.        |
| `wine --version`             | Prints the WineCX version.               |
| `wine cmd /c ver`            | Starts a 64-bit program.                 |
| Wine log                     | No `cannot release the pagezero`.        |
| Wine log                     | No `failed to map the shared user data`. |
| Wine log                     | No unhandled `SIGSEGV` at `0x7ffe0000`.  |
| Game                         | Reaches the login screen.                |
| Game                         | Passes the ACE check.                    |
| Game                         | Renders with DXMT.                       |

Add one offline test for each contract that a port can break:

- The shared page address is not `0x7ffe0000` when the low region is unavailable.
- The shared page address stays `0x7ffe0000` when the entitlement is present.
- A 4K page inside a 16K host page keeps its own write protection.
- The emulator registry values name an existing module.

## Evaluation before the port

The port is not the fastest way to answer whether ARM64 is viable.
MetalSharp-Wine publishes an unsigned ARM64 archive that runs without the entitlement.
Use it to test ACE, rendering, and frame time in a throwaway prefix.
Do not ship that archive and do not add it to the runtime.

The result decides the order of work:

| Result                                  | Action                                                   |
| --------------------------------------- | -------------------------------------------------------- |
| ACE passes and frame time is acceptable | Continue the port.                                       |
| ACE fails                               | Stop. The ARM64 lane cannot serve the protected clients. |
| Rendering fails only in DXMT            | Evaluate a newer DXMT commit.                            |
| Frame time is poor                      | Tune FEX and DXMT before the port.                       |
