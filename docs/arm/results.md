# ARM64 experiment results

This page records what was tried, what worked, and what failed.
It is the evidence behind the decisions in the other ARM64 documents.
Last updated: 2026-11-05.

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
W^X handling lives in the separate `wx-pages` patch; see [ARM64EC unix call and W^X](#arm64ec-unix-call-and-wx).

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

A minimal x86_64 PE loads at `0x140000000`.
The process loads `libarm64ecfex.dll`, patches its hybrid metadata, resolves the
module's imports, and completes FEX `ProcessInit` and `ThreadInit`.
The guest entry call reaches the FEX JIT dispatcher.
FEX compiles the entry block and the probe prints `fex-ok`.

`ThreadInit` only runs when `pThreadInit` resolves.
An installed `ntdll.dll` that predates the current tree resolved it to NULL and
logged `ThreadInit 0` anyway, because the status came from the skipped call.
Reinstall `ntdll.dll` after a rebuild before drawing conclusions from that log.

Wine's `wine.inf` now points `Wow64\amd64` at `libarm64ecfex.dll` and
`Wow64\x86` at `libwow64fex.dll`.
A fresh prefix writes both values.

A fresh prefix with the x86 value also reports a missing 32-bit
`C:\windows\syswow64\rundll32.exe`.
That is expected for a 64-bit-only lane and does not affect the native ARM64
`cmd /c ver` start.

The likely missing pieces are the reference ARM64EC patches:

- `0004`/`0017`: ID registers and `EFlags`.
- `0126`/`0128`: hybrid entry points and executable data views.

The lane does not run the game yet.

## ARM64EC unix call and W^X

`libarm64ecfex.dll` is an ARM64EC module, so its PE build defines `__x86_64__`.
The PE called CodeWeavers' `unix_pe_module_loaded` hook, but the aarch64
`ntdll.so` table has no such entry.
The call read past the table and jumped into string data.
The `arm64ec-unix-call` patch gates the hook on `!defined(__arm64ec__)`.

`NtProtectVirtualMemory(PAGE_READWRITE)` on the module's `.rdata` then failed
with `STATUS_ACCESS_DENIED`.
A 16K host page mixed executable 4K pages with writable ones, so Wine asked
for RWX, which macOS refuses.
The `wx-pages` patch drops `PROT_EXEC` instead, so the page stays writable and
`virtual_handle_fault` can flip it for an execute fault.
Measure the flip from a normal Terminal.

Both fixes are in the native-arm64 patch set.

FEX then asserted in `CPUFeatures::FetchHostFeatures` because
`get_core_id_regs_arm64` was a stub and the processor registry key had zero
`CP 4xxx` values.
The `id-registers` patch synthesizes the values from the `hw.optional.arm.*`
sysctls.
FEX `ProcessInit`, feature detection, the cross-process work list, and
`ThreadInit` now return success.

## 16K host pages and the JIT code buffer

FEX asks for `PAGE_EXECUTE_READWRITE` for its code buffers.
The `wx-pages` patch maps such a Wine request writable-only and lets
`virtual_handle_fault` flip the host page for an execute fault.
The rule remains for mixed PE host pages.

FEX code buffers use the `map-jit` patch instead.
The unix library maps the dispatcher and the shared code buffer with `MAP_JIT`
and keeps them `rwx`.
FEX toggles `pthread_jit_write_protect_np` around code writes.

The fault flip works in a normal Terminal.
The earlier probes ran under the agent shell, which suppresses synchronous
signals; a fixed address and a NULL store both hang there.
A standalone test launched from a normal Terminal prints `FAULT sig=11` for the
same NULL store.
Run every fault-delivery measurement from a normal Terminal, never from the
agent shell.

A standalone test mapped a page with `MAP_JIT`, wrote a `ret` instruction with
`pthread_jit_write_protect_np(0)`, switched to `pthread_jit_write_protect_np(1)`,
and executed it.
`mmap(PROT_READ | PROT_WRITE, MAP_JIT)` followed by
`mprotect(PROT_READ | PROT_WRITE | PROT_EXEC)` also succeeds.

## Lookup cache commit

FEX allocates the lookup cache with `Commit=false`, so Wine leaves it reserved.
The first block lookup then reads an uncommitted page and takes a data abort.
FEX expects to commit that page from its `ResetToConsistentState` callback.
Wine returns `STATUS_ACCESS_VIOLATION` instead and the callback never runs, so
the thread faulted on the same instruction forever.

Passing `Commit=true` for that allocation removes the fault.
The change is one argument in `FEXCore/Source/Interface/Core/LookupCache.cpp`
and is a no-op outside Windows.

With it, FEX compiles the guest block at `0x140000000 + 0x13b0`
(`PreCompile` and `LookupExecutableFileSection` both run).
The probe then prints `fex-ok`; the trace shows `PRECOMPILE`,
`LOOKUP-SEC 0x1400013b0`, and many `CODE-WRITE`/`CODE-FLUSH` pairs.

The dispatcher trace shows the entry address is not truncated.
At `DispatcherLoopTopEnterEC`, `x1` and `x9` are both `0x1400013b0`.
The stack holds the return addresses of `RtlUserThreadStart`,
`BaseThreadInitThunk`, and the kernel32 exit thunk.
The earlier `x9 = 0x400013b0` reading does not reproduce on this path.

The first runs stalled in the scratch `fprintf(stderr, "FEXTRACE CompileBlock ...")`
in `Core.cpp`, before `PreCompile`.
Removing that diagnostic let the block compile.
The tracer is not part of the patch set.

The earlier debugger trace showed this reset chain:

| Trace                                  | Meaning                                                               |
| -------------------------------------- | --------------------------------------------------------------------- |
| `PRECOMPILE`, `LOOKUP-SEC 0x1400013b0` | The entry block is translated.                                        |
| `RESET-AV 0x7ffeabf00004`              | The guest faults on an unmapped address outside the overcommit range. |
| `RESET-OVC 0`                          | The overcommit tracker declines to commit it.                         |
| `RECON 0x7ffeabf00004 -> 0x1400013b0`  | FEX maps the host PC back to the entry RIP.                           |
| `GUEST-EXC c0000005 0x1400013b0`       | The access violation is rethrown to the guest at the entry.           |

The guest has no handler for it, so the thread repeats the fault.
Disabling the dispatcher's opportunistic call-ret pop does not change it.

The earlier debugger run also found a second code buffer at `0x7ffeabf00000`
that was reserved-only.
The `MAP_JIT` allocator maps every code buffer afresh, so the lane no longer
commits that region.

## Window chrome

The x86_64 loader records SDK 27.0, so the game window keeps the current macOS decorations.
The ARM64 loader records SDK 12.0, which would select the legacy decorations.

Prototype: a client dylib interposes `dyld_get_program_sdk_version()` and returns the running OS version.
Injected through `DYLD_INSERT_LIBRARIES`, AppKit calls it during window creation and reads the current version.
The dylib is not shipped.
The x86_64 lane does not need it.

## Summary

| Item                   | State                                                  |
| ---------------------- | ------------------------------------------------------ |
| Native ARM64 Wine boot | Works                                                  |
| Shared user data       | Relocated                                              |
| Mono                   | Skipped                                                |
| x86_64 under FEX       | Prints fex-ok; the first x86_64 program runs under FEX |
| Game                   | Not started                                            |
| ACE                    | Not tested                                             |
| Window chrome          | Legacy on ARM; bridge prototyped                       |
