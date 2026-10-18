# ACE compact compatibility provenance

## Source pins

- Wine base: `dappermint/winecx`
- Wine commit: <!-- pin:wine.commit|code -->`b1417d2773a0dfc15cc78b78e1257ee965bcca89`<!-- /pin --> (Wine <!-- pin:wine.version -->11.19<!-- /pin -->)
- Candidate reference: [`stoicswe/Endfield_FineWine`](https://github.com/stoicswe/Endfield_FineWine)
- Reference checkout: `e5d4ccad235eefe32d912733e57e4c0bb53a5b58`
- Reference patch families: `stage1-macos` and `stage2-dwproton`

The reference repository records the original dw-proton/Endfield work and authors. These files port selected changes to this WineCX pin.

## Ported inventory

### `ntoskrnl`

The patch adds only kernel exports that the pinned Wine commit does not implement:

- `PsGetProcessExitStatus`: returns the exit status of a process object. Upstream keeps this export as a stub. It has no NULL check on its `_In_` process parameter.
- `SeSetAuditParameter`: a gated no-op. It logs its arguments. With `ARKNIGHTS_RUNTIME_ACE_COMPACT=1`, it returns `STATUS_SUCCESS`. Otherwise it returns `STATUS_NOT_IMPLEMENTED`. It never reads or writes through its pointer arguments.
- `PsGetCurrentThreadProcess` and `PsGetCurrentThreadProcessId`: unconditional aliases of the current-process functions.

The gate helper `arknights_runtime_ace_compact_enabled()` serves only `SeSetAuditParameter`. The patch does not change any existing upstream function.

Wine <!-- pin:wine.version -->11.19<!-- /pin --> already provides the other exports that the ACE client needs: the process session and creation-time accessors, the bug-check callback exports, `PsGetProcessImageFileName`, `PsGetThreadProcess`, `KeCapturePersistentThreadState`, and `MmGetVirtualForPhysical`. The last two are only partial. `KeCapturePersistentThreadState` is a stub that returns `STATUS_NOT_IMPLEMENTED`. `MmGetVirtualForPhysical` is a semi-stub that returns its input address unchanged. The patch changes neither one. With the gate off, the ntoskrnl behavior matches upstream Wine at the pinned commit.

### `dispatcher`

Carries the x86_64 `KiUserApcDispatcher` / `KiUserCallbackDispatcher` `GetProcAddress` int3-stub workaround. Only `ARKNIGHTS_RUNTIME_ACE_COMPACT=1` enables it. It uses no process-name heuristics.

### `rosetta`

Ports the Rosetta workarounds that the ACE client needs: bounded multi-byte NOP decoding, and classification of the ACE privileged-instruction fault that Rosetta reports as an invalid-opcode trap. CrossOver CET and XGETBV handling is unchanged.

### `timing`

Carries the relative `NtDelayExecution` QPC path. It applies only to negative relative waits and only with the ACE compact gate. Absolute, zero, alertable, and default waits are unchanged.

Validate the inactive and enabled routes in an isolated prefix: launcher startup, ACE initialization, gameplay, clean shutdown.
