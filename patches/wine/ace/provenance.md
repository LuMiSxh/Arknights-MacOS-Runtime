# ACE compact compatibility provenance

## Source pins

- Wine base: `dappermint/winecx`
- Wine commit: <!-- pin:wine.commit|code -->`5ee1af65283cf7baf162cbab545a696d29206970`<!-- /pin --> (Wine <!-- pin:wine.version -->11.19<!-- /pin -->)
- Candidate reference: [`stoicswe/Endfield_FineWine`](https://github.com/stoicswe/Endfield_FineWine)
- Reference checkout: `e5d4ccad235eefe32d912733e57e4c0bb53a5b58`
- Reference patch families: `stage1-macos` and `stage2-dwproton`

The reference repository records the original dw-proton/Endfield work and authors. These files port selected changes to this WineCX pin.

## Ported inventory

### `ntoskrnl`

Carries the non-X11 kernel surface that the ACE client needs:

- current-thread process and process-ID accessors (unconditional aliases of the current-process functions)
- unconditional exit-status accessor for valid process objects, without NULL checks on its `_In_` process parameter
- the `arknights_runtime_ace_compact_enabled()` gate helper in `ntoskrnl_private.h`
- the callable `SeSetAuditParameter` no-op: logs its arguments, returns `STATUS_SUCCESS` only when `ARKNIGHTS_RUNTIME_ACE_COMPACT=1`, never dereferences or writes through its pointer arguments; otherwise the original Wine stub stays active
- the gated `SeLocateProcessImageName` override: queries `ProcessImageFileNameWin32` and runs only with the gate
- process-object metadata lifetime handling

Wine <!-- pin:wine.version -->11.19<!-- /pin --> already provides the process session and creation-time accessors, the bug-check callback exports, `PsGetProcessImageFileName`, `PsReferencePrimaryToken`, `PsGetContextThread`, `PsGetThreadProcess`, `MmGetPhysicalMemoryRanges`, `MmGetVirtualForPhysical`, `KeCapturePersistentThreadState`, and the real `SeLocateProcessImageName`. The patch omits these functions. The only exception is the gated `SeLocateProcessImageName` override. With the gate off, all of them follow upstream.

### `dispatcher`

Carries the x86_64 `KiUserApcDispatcher` / `KiUserCallbackDispatcher` `GetProcAddress` int3-stub workaround. Only `ARKNIGHTS_RUNTIME_ACE_COMPACT=1` enables it. It uses no process-name heuristics.

### `rosetta`

Ports the Rosetta workarounds that the ACE client needs: bounded multi-byte NOP decoding, and classification of the ACE privileged-instruction fault that Rosetta reports as an invalid-opcode trap. CrossOver CET and XGETBV handling is unchanged.

### `timing`

Carries the relative `NtDelayExecution` QPC path. It applies only to negative relative waits and only with the ACE compact gate. Absolute, zero, alertable, and default waits are unchanged.

Validate the inactive and enabled routes in an isolated prefix: launcher startup, ACE initialization, gameplay, clean shutdown.
