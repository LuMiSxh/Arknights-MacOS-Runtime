# ACE compact compatibility provenance

## Source pins

- Wine base: `dappermint/winecx`
- Wine commit: `e1b410a5fdd96a32722a5f2617b5068bd385b7db` (Wine 11.16)
- Candidate reference: [`stoicswe/Endfield_FineWine`](https://github.com/stoicswe/Endfield_FineWine)
- Reference checkout: `e5d4ccad235eefe32d912733e57e4c0bb53a5b58`
- Reference patch families: `stage1-macos` and `stage2-dwproton`

The reference repository records the original dw-proton/Endfield work and its
authors. These files port selected changes to this exact WineCX pin.

## Ported inventory

### `ntoskrnl`

Carries the non-X11 kernel surface required by the ACE client: process session,
creation time, image name, primary token, thread process/context accessors,
current-thread process and process-ID accessors, and unconditional image-name and exit-status
accessors for valid process objects,
guarded bug-check callback registration stubs, the
`KeCapturePersistentThreadState` export stub, the callable
`SeSetAuditParameter` no-op, physical-memory compatibility stubs, and
process-object metadata lifetime handling. The capture function logs its
arguments and returns `STATUS_NOT_IMPLEMENTED` without dereferencing or
writing through any pointer. `SeSetAuditParameter` logs its arguments and
returns `STATUS_SUCCESS` only when `ARKNIGHTS_RUNTIME_ACE_COMPACT=1`; it never
dereferences or writes through its pointer arguments. The original Wine stub
behavior remains active otherwise. The current-thread process accessors are
unconditional aliases of the corresponding current-process functions. The
process image-name and exit-status accessors are unconditional for valid
process objects; their `_In_` process parameters are not NULL-checked.

### `dispatcher`

Carries the x86_64 `KiUserApcDispatcher` / `KiUserCallbackDispatcher`
`GetProcAddress` int3-stub workaround. The route is available only when
`ARKNIGHTS_RUNTIME_ACE_COMPACT=1`; process-name heuristics are intentionally not
used.

### `rosetta`

Ports the macOS-specific Rosetta workarounds needed by the ACE client: bounded
multi-byte NOP decoding and classification of ACE's privileged-instruction
fault when Rosetta reports it through the invalid-opcode trap. Existing
CrossOver CET and XGETBV handling is unchanged.

### `timing`

Carries the relative `NtDelayExecution` QPC path. It is selected only for
negative relative waits and only with the explicit ACE compact gate; absolute,
zero, alertable, and default waits remain unchanged.

Validate the inactive and enabled routes in an isolated prefix through launcher
startup, ACE initialization, gameplay, and clean shutdown.
