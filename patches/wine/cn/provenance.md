# Provenance and patch inventory

## Source pins

- Wine base: `dappermint/winecx`
- Wine commit: `7dbc5b5322a6ef3fb04bdc643c64b188fd641149` (Wine 11.16)
- Candidate reference: [`stoicswe/Endfield_FineWine`](https://github.com/stoicswe/Endfield_FineWine)
- Reference checkout: `e5d4ccad235eefe32d912733e57e4c0bb53a5b58`
- Reference patch families: `stage1-macos` and `stage2-dwproton`

The reference repository records the original dw-proton/Endfield work and
its authors. These files port selected changes to this exact WineCX pin.

## Ported inventory

### `ntoskrnl`

Carries the non-X11 kernel surface from the reference dw-proton series that is
not already implemented in the pinned WineCX tree:

- process session, creation time, image name, primary token, and thread
  process/context accessors;
- guarded bug-check callback registration stubs;
- physical-memory range and physical-to-virtual compatibility stubs;
- process-object metadata lifetime handling and `SeLocateProcessImageName`.

All added entry points retain the old stub result unless
`ARKNIGHTS_RUNTIME_CN_COMPAT=1`. The process metadata query path bounds the reported
image-name allocation and releases temporary or failed allocations.

### `dispatcher`

Carries the x86_64 `KiUserApcDispatcher` / `KiUserCallbackDispatcher`
`GetProcAddress` int3-stub workaround from the reference dw-proton series.
The original process-name heuristic is intentionally removed. The route is
available only when `ARKNIGHTS_RUNTIME_CN_COMPAT=1`.

### `rosetta`

Ports the macOS-specific Rosetta workarounds from the reference stage-1
patch:

- decode and skip a genuine `0F 1F /0` multi-byte NOP when Rosetta reports it
  as an illegal instruction;
- classify an ACE privileged-instruction fault as
  `EXCEPTION_PRIV_INSTRUCTION` when Rosetta reports it through the invalid
  opcode trap.

The NOP decoder validates the ModRM opcode and every displacement boundary.
Existing CrossOver CET (`0F 1E`) and XGETBV handling is not changed.

### `timing`

Carries the dw-proton relative `NtDelayExecution` QPC path. It is selected
only for negative relative waits and only with the explicit CN gate; absolute
waits, zero waits, alertable waits, and the default path remain unchanged.

## Intentionally omitted candidates

- Historical `wintrust` `winex11`/`winewayland` signature bypass: X11-only and
  not relevant to the macOS driver.
- Process-name-based gates such as `Endfield.exe`: not a safe boundary for a
  shared runtime.
- Any Wine export hiding, registry spoofing, or native-arm64 `int3` emulation:
  none is established as necessary by the available evidence.

Validate the inactive and enabled routes in an isolated prefix through launcher
startup, login, ACE initialization, gameplay, and clean shutdown.
