# Wine patches

These patches apply to the `rosetta-x86_64` target in numeric order.
The ARM64 export keeps the same numbers, names, gates, and gate semantics in
`wine-build-new/patches/`, but its copies may differ in content.
`0001` and `0002` are ARM-only and live only in `wine-build-new/patches/`.

Each patch has one gate variable, `LMISXH_AKMOCL_<NAME>`. There is no master switch.
A default-on gate is on when the variable is unset or exactly `1`. Any other value,
including `0`, `false`, an empty string, or a typo, turns the patch off.
A default-off gate is on only for exactly `1`.

| Number | File | Purpose | Gate variable | Default | Targets |
| ------ | ---- | ------- | ------------- | ------- | ------- |
| 0003 | `0003-ntoskrnl-arknights-ace-imports.patch` | ACE kernel imports and process metadata | `LMISXH_AKMOCL_ACE_IMPORTS` | on | x86, ARM |
| 0004 | `0004-userenv-appcontainer-apis.patch` | AppContainer exports for the Chromium sandbox | `LMISXH_AKMOCL_APPCONTAINER` | on | x86, ARM |
| 0005 | `0005-ws2_32-address-list-sort.patch` | `SIO_ADDRESS_LIST_SORT` for Chromium asynchronous DNS | `LMISXH_AKMOCL_WINSOCK` | on | x86, ARM |
| 0006 | `0006-ntdll-bilibili-cef80-stack-base.patch` | Descriptor-driven CEF 80.1.15 loader patch | `LMISXH_AKMOCL_CEF` | on | x86, ARM |
| 0007 | `0007-win32u-winemac-bilibili-layered-child.patch` | Bilibili layered child window route | `LMISXH_AKMOCL_CN` | off | x86, ARM |
| 0008 | `0008-winemac-bilibili-join-all-spaces.patch` | Bilibili platform window joins all Spaces | `LMISXH_AKMOCL_CN` | off | x86, ARM |
| 0009 | `0009-winemac-native-fullscreen-space.patch` | Native fullscreen Space for the game window | `LMISXH_AKMOCL_FULLSCREEN` | on | x86, ARM |
| 0010 | `0010-ntdll-hide-software-cursor-asset.patch` | Hide the software cursor asset | `LMISXH_AKMOCL_CURSOR` | off | x86, ARM |
| 0011 | `0011-winemac-command-q-quit.patch` | Command-Q for the application menu Quit item | `LMISXH_AKMOCL_MENU` | on | x86, ARM |
| 0012 | `0012-winecoreaudio-default-output.patch` | CoreAudio default-output follow | `LMISXH_AKMOCL_AUDIO` | on | x86 only |
| 0013 | `0013-ntdll-ace-qpc-relative-wait.patch` | ACE QPC relative wait | `LMISXH_AKMOCL_ACE_TIMING` | on | x86 only |
| 0014 | `0014-kernel32-ace-dispatcher-spoof.patch` | x86 dispatcher lookup spoof | `LMISXH_AKMOCL_ACE_DISPATCHER` | on | x86 only |
| 0015 | `0015-macos-rosetta-ace-workarounds.patch` | Rosetta ACE privileged-instruction workarounds | `LMISXH_AKMOCL_ACE_ROSETTA` | on | x86 only |

`0007` and `0008` share the `LMISXH_AKMOCL_CN` gate. `0013` to `0015` are the x86
ACE routes; the ARM export carries its own ACE copies. The ACE routes target the
ACE-protected Hypergryph clients and stay separate from the Bilibili renderer
family.

## Patch notes

### 0003 ACE imports

Carries the non-X11 kernel surface that the ACE client needs: process image name
and primary-token support, thread process and context accessors, current-thread
process and process-ID aliases, and image-name and exit-status accessors.
It also adds the `KeCapturePersistentThreadState` stub, the callable
`SeSetAuditParameter` no-op, physical-memory stubs, and process-object metadata
lifetime handling.
General process accessors ignore the gate.
The ARM copy is reduced to three exports, because Wine 11.18 already provides the
rest.

### 0004 AppContainer

Chromium's sandbox loads these names and checks that they resolve. Wine 11.17
exports `CreateAppContainerProfile` only as a stub.
The patch adds `DeriveAppContainerSidFromAppContainerName`,
`DeleteAppContainerProfile`, `GetAppContainerRegistryLocation`, and
`GetAppContainerFolderPath`. The SID uses SHA-256 of the lowercased container name
folded into an `APP_PACKAGE` SID. The registry and folder locations return
`E_NOTIMPL`.
The `kernelbase` exports `CreateAppContainerToken` and
`GetAppContainerNamedObjectPath` are stubs that return `FALSE` with
`ERROR_CALL_NOT_IMPLEMENTED`. Chromium only requires the names to resolve.
The client can remove the process-local `userenv.dll` shim and the `userenv=n,b`
override once this patch is in the runtime.

### 0005 Winsock address list sort

Chromium's asynchronous DNS resolver calls `WSAIoctl(SIO_ADDRESS_LIST_SORT)`.
Wine returned `WSAEOPNOTSUPP`, so CEF retried the call and an OAuth page stayed
blank. The patch adds the constant and handles the ioctl in `ws2_32`.
The returned list keeps the supplied order. Chromium only needs a valid list.
The handler bounds `iAddressCount` against the input size and validates every
address before the in-place shortcut. It completes the overlapped call through
`IOCTL_AFD_WINE_COMPLETE_ASYNC`.
The client can remove `--disable-features=AsyncDns` once this patch is in the
runtime.

### 0006 CEF

The generic CEF dispatcher is descriptor-driven. The Bilibili CEF 80.1.15
descriptor is limited to the `libcef.dll` basename, the three proven RVAs, and
all expected bytes. It checks every value before it writes.
Add a regional descriptor only after reverse-engineering evidence identifies its
complete byte contract.

### 0007 Bilibili layered child

Keeps Chromium's layered proxies for login and payment drawable inside the root
Wine window. The route is limited to `PCGamePlatform.exe`, the Chromium
`Chrome_WidgetWin_0` and `Chrome.WindowTranslucent` property contract, and a
`CMyWebViewDlg` anywhere in the parent chain of the candidate.
This supports nested Bilibili dialogs.

### 0008 Bilibili join all Spaces

Makes the Bilibili platform window join all Spaces, so it stays visible over a
game in a native fullscreen Space. In `adjustFullScreenBehavior:` it clears
`FullScreenPrimary` and sets `CanJoinAllSpaces` and `FullScreenAuxiliary`.
It uses the `macdrv_is_bilibili_platform_process()` test from `0007`.

### 0009 Native fullscreen Space

Puts a fullscreen game window into a macOS native fullscreen Space.
A window is a candidate only when the gate is on, it participates in the window
cycle, it is not a utility window, and it has no parent. Its last content rect
must cover a screen, or the screen below the camera housing.
A window with `CanJoinAllSpaces` or `Stationary`, or one that ignores the cycle,
is never a candidate.
The patch enters the Space with a deferred `toggleFullScreen:` call, reposts the
frame at most twice, and leaves the Space when the Wine rect no longer covers the
screen. A user exit blocks automatic re-entry until the rect changes or the
window is ordered out.
Content clicks stay in the Wine view and do not reach the Cocoa frame drag
handler. Layered windows stay auxiliary to the fullscreen game. In a Space the
close button sends the normal Win32 close.
On a Mac with a camera housing, the Space frame sits below the housing while Wine
keeps the full monitor rect. The patch subtracts that height from pointer
positions it sends to Wine and adds it to positions Wine sets, so the pointer
matches the picture. The offset is zero on other Macs.
The feature is off for the whole process when the program is
`PlatformProcess.exe` or `PlatformProcess.original.helper.exe`.
The ARM copy has extra includes and an earlier shader-cache helper, so its
`macdrv_main.c` hunks apply at an offset.

### 0010 Hardware cursor

Returns `STATUS_OBJECT_NAME_NOT_FOUND` for the two exact cursor asset basenames.
The filter runs in shared NT-to-Unix name resolution and covers file creation and
both attribute-query APIs. It does not read, embed, copy, or modify game asset
contents.
The basenames are `a9d41799f1af1868f2db495671227cd4.bin` for the Yostar
Global/Japan/Korea and Taiwan clients, and
`f7bcd64480c4566f25d65d642f5fba95.bin` for the China - Bilibili client.

### 0011 Command-Q

Sets the application menu Quit item to the Command key equivalent only. The
upstream mask was Command+Option. Hide Others and the other menu items keep their
masks.

### 0012 Audio default output

Carries the two-commit Wine draft merge request `!11370`,
`winecoreaudio: Expose virtual endpoints for default devices`.
When enabled, the virtual endpoint of an eligible shared render stream follows
the default output. An explicitly selected endpoint can recover after disconnect
and reconnect. Capture and exclusive streams are unchanged.
The HAL callback reduces CoreAudio notifications to a pthread signal. A Wine
worker thread retargets and stops or starts the AudioUnit. The render callback
lock is never held across a stop or start. Process detach unregisters both HAL
listeners, joins the worker, and restores the previous HAL run loop.
Test both environment modes. Switch the macOS default output during an active
shared render stream. Confirm that the stream continues on the new output, keeps
the application volume, and recovers after a device disconnects and reconnects.

### 0013 ACE timing

Carries the relative `NtDelayExecution` QPC path. It applies only to negative
relative waits. Absolute, zero, alertable, and default waits are unchanged.

### 0014 ACE dispatcher

Carries the x86_64 `KiUserApcDispatcher` and `KiUserCallbackDispatcher`
`GetProcAddress` int3-stub workaround. It uses no process-name heuristics.
The stub is x86 machine code, so the patch is x86-only.

### 0015 ACE Rosetta

Ports the Rosetta workarounds that the ACE client needs: bounded multi-byte NOP
decoding, and classification of the ACE privileged-instruction fault that Rosetta
reports as an invalid-opcode trap. CrossOver CET and XGETBV handling is unchanged.
Patch order for the ACE routes is `0003`, `0013`, `0014`, then `0015`.

Validate the inactive and enabled routes in an isolated prefix: launcher startup,
ACE initialization, gameplay, and clean shutdown.

See [provenance.md](provenance.md) for sources, authors, and licenses.
