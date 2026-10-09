# ACE compact compatibility provenance

## Source pins

- Wine base: `dappermint/winecx`
- Wine commit: `e0aa380780b73e20fabcfe78fd42713b94929a53` (Wine 11.17)
- Candidate reference: [`stoicswe/Endfield_FineWine`](https://github.com/stoicswe/Endfield_FineWine)
- Reference checkout: `e5d4ccad235eefe32d912733e57e4c0bb53a5b58`
- Reference patch families: `stage1-macos` and `stage2-dwproton`

The reference repository records the original dw-proton/Endfield work and authors. These files port selected changes to this WineCX pin.

## Ported inventory

### `ntoskrnl`

Carries the non-X11 kernel surface that the ACE client needs:

- process image name and primary-token support
- thread process/context accessors
- current-thread process and process-ID accessors (unconditional aliases of the current-process functions)
- unconditional image-name and exit-status accessors for valid process objects, without NULL checks on their `_In_` process parameters
- the `KeCapturePersistentThreadState` export stub: logs its arguments, returns `STATUS_NOT_IMPLEMENTED`, never dereferences or writes through a pointer
- the callable `SeSetAuditParameter` no-op: logs its arguments, returns `STATUS_SUCCESS` only when `ARKNIGHTS_RUNTIME_ACE_COMPACT=1`, never dereferences or writes through its pointer arguments; otherwise the original Wine stub stays active
- physical-memory compatibility stubs
- process-object metadata lifetime handling

Wine 11.17 already provides the process session and creation-time accessors and the bug-check callback exports, so the patch omits them.

### `dispatcher`

Carries the x86_64 `KiUserApcDispatcher` / `KiUserCallbackDispatcher` `GetProcAddress` int3-stub workaround. Only `ARKNIGHTS_RUNTIME_ACE_COMPACT=1` enables it. It uses no process-name heuristics.

### `rosetta`

Ports the Rosetta workarounds that the ACE client needs: bounded multi-byte NOP decoding, and classification of the ACE privileged-instruction fault that Rosetta reports as an invalid-opcode trap. CrossOver CET and XGETBV handling is unchanged.

### `timing`

Carries the relative `NtDelayExecution` QPC path. It applies only to negative relative waits and only with the ACE compact gate. Absolute, zero, alertable, and default waits are unchanged.

Validate the inactive and enabled routes in an isolated prefix: launcher startup, ACE initialization, gameplay, clean shutdown.
