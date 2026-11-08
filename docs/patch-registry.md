# Patch registry

[`runtime.lock.json`](../runtime.lock.json) holds the machine-readable ordered registry. Before release, each entry must name its upstream source, author, license, gate, inactive behavior, test, and removal condition. The entries document provenance. They do not replace the corresponding-source, notice, and redistribution review that a runtime binary requires.

The ACE, CEF, and CN patches target WineCX <!-- pin:wine.commit|code -->`a54b8240683e92bf4c15cb1ba6bf92a9539bd768`<!-- /pin --> and keep Wine's LGPL-2.1-or-later license. The native ARM64 lane is built externally in [wine-build-new](https://github.com/riverfog7/wine-build-new), so its patches are in [`wine-build-new/`](../wine-build-new/) and not in this registry.

## Audio

- ID: `wine-audio-default-output`
- File: `patches/wine/0012-winecoreaudio-default-output.patch`
- Component/base: WineCX <!-- pin:wine.commit|code -->`a54b8240683e92bf4c15cb1ba6bf92a9539bd768`<!-- /pin --> (Wine <!-- pin:wine.version -->11.17<!-- /pin -->)
- Source/author: Wine draft MR 11370, commits `4d143f4c` and `65140f31`, Rhodri Richards
- License: LGPL-2.1-or-later
- Gate: `LMISXH_AKMOCL_AUDIO` (default on: unset or exactly `1`), parsed once per process
- Inactive behavior: Normal Wine endpoint enumeration and routing
- Automated gate: Hash and clean `git apply --check`; patched Wine compile
- Manual gate: Active shared render stream follows default device across switch/disconnect/reconnect
- Removal: Drop when the pinned WineCX has equivalent behavior

The MR is a draft. Capture and exclusive streams are unchanged.

## Hardware Cursor

- ID: `wine-hardware-cursor-suppression`
- File: `patches/wine/0010-ntdll-hide-software-cursor-asset.patch`
- Component/base: WineCX <!-- pin:wine.commit|code -->`a54b8240683e92bf4c15cb1ba6bf92a9539bd768`<!-- /pin --> (Wine <!-- pin:wine.version -->11.17<!-- /pin -->)
- Source/author: Original runtime change; motivated by the [reported PC cursor stutter](https://www.reddit.com/r/arknights/comments/1vorlzp/pc_client_fix_for_the_annoying_mouse_stuttering/)
- License: LGPL-2.1-or-later (Wine)
- Gate: `LMISXH_AKMOCL_CURSOR` (default off: only exactly `1` enables it), checked during shared file-name resolution
- Inactive behavior: Missing, `0`, or invalid values use Wine's normal path resolution
- Automated gate: Hash, clean `git apply --check`, focused `ntdll.so` build, Wine test-object compilation for exact/case variants and attribute APIs
- Manual gate: Compare the software sprite with the macOS pointer, using the exact asset
- Removal: Drop if the client stops using the asset or Wine gains an equivalent control

The filter matches the case-insensitive final basename `a9d41799f1af1868f2db495671227cd4.bin` (Yostar Global/Japan/Korea and Taiwan) or `f7bcd64480c4566f25d65d642f5fba95.bin` (China — Bilibili). It converts successful lookups and `STATUS_NO_SUCH_FILE` into `STATUS_OBJECT_NAME_NOT_FOUND` and clears the resolved Unix path, so create-if-missing cannot recreate the file. Shared name resolution makes `NtCreateFile`, `NtQueryAttributesFile`, and `NtQueryFullAttributesFile` see the same hidden asset. The patch copies and modifies no game asset.

## Runtime features

`runtime.lock.json` carries a small `features` object instead of a separate manifest. It records `hardwareCursor`, `metalFXSpatialUpscaling`, and `nativeFullscreenSpace` for each target. The embedded `RUNTIME.json.features` is the source of the behavior flags; the client treats a missing feature as `false`. `aceCompat` and `nativeArm64` are removed: `nativeArm64` duplicates the lane, and `aceCompat` is About-only with no launch policy.

## Performance

### Release present statistics gate

- ID: `dxmt-skip-release-present-statistics`
- File: `patches/dxmt/0001-dxmt-skip-release-present-statistics.patch`
- Component/base: DXMT <!-- pin:dxmt.commit|code -->`9839e55f98d4aca103957ee4132d6395a325a9ed`<!-- /pin -->
- Source/author: Original runtime optimization, runtime maintainers
- License: LGPL-2.1-or-later (DXMT)
- Gate: `DXMT_DEBUG`; debug builds keep statistics aggregation and HUD updates, release builds skip both
- Inactive behavior: Frame counters, measurements, advancement, latency waits, and resets unchanged
- Automated gate: Hash, clean application, both DXMT architectures, release/debug preprocessor contract
- Manual gate: Startup, rendering, and frametime comparison against the clean-removal control (same scene, settings, runtime)
- Removal: Drop when the pinned DXMT removes the release-dead work or gains an equivalent build option

Both `Present` paths keep `UpdateStatistics` behind `DXMT_DEBUG`, which avoids its per-present `std::format` calls in release builds. `PresentBoundary` gates the rolling statistics aggregation the same way. Release builds keep the frame counters and synchronization.

The display query leak patch is not carried. The pin moved to DXMT 0.80-361, which contains the fix. The pinned commit is <!-- pin:dxmt.commit|code -->`9839e55f98d4aca103957ee4132d6395a325a9ed`<!-- /pin -->.

## ACE

Each ACE patch has one default-on gate, `LMISXH_AKMOCL_<NAME>`: unset or exactly `1` keeps the route on, and any other value keeps Wine's normal route. There is no master switch. Every patch requires hash verification and clean application. All four are Endfield FineWine ports ([provenance](../patches/wine/provenance.md)).

- [`wine-ace-ntoskrnl-surface`](../patches/wine/0003-ntoskrnl-arknights-ace-imports.patch)
    - What: Kernel exports and process metadata for the ACE client: current-thread process, image-name, exit-status, audit-parameter, and persistent-thread-state surfaces.
    - Scope: `LMISXH_AKMOCL_ACE_IMPORTS`. Compatibility-only routes use the ACE gate. `PsGetProcessImageFileName` and `PsGetProcessExitStatus` stay unconditional for valid process objects and follow their kernel `_In_` contract.
    - Checks: compile both architectures; exercise gated and general routes.
- [`wine-ace-dispatcher-spoof`](../patches/wine/0014-kernel32-ace-dispatcher-spoof.patch)
    - What: x86-64 dispatcher lookup compatibility.
    - Scope: `LMISXH_AKMOCL_ACE_DISPATCHER`. ACE gate and Rosetta x86-64 build only.
    - Checks: compile; dispatcher startup.
- [`wine-ace-rosetta-workarounds`](../patches/wine/0015-macos-rosetta-ace-workarounds.patch)
    - What: Bounded NOP and ACE privileged-instruction handling under Rosetta.
    - Scope: `LMISXH_AKMOCL_ACE_ROSETTA`. ACE gate; existing CrossOver CET/XGETBV handling is untouched.
    - Checks: compile; exercise inactive and enabled routes.
- [`wine-ace-relative-wait`](../patches/wine/0013-ntdll-ace-qpc-relative-wait.patch)
    - What: Relative `NtDelayExecution` timing route.
    - Scope: `LMISXH_AKMOCL_ACE_TIMING`. ACE gate and negative relative waits only; other waits are unchanged.
    - Checks: focused wait tests.

## CEF

The CEF patch has one default-on gate, `LMISXH_AKMOCL_CEF`: unset or exactly `1` applies the descriptor, and any other value keeps Wine's normal route.

- [`wine-cef-bilibili-stackbase`](../patches/wine/0006-ntdll-bilibili-cef80-stack-base.patch)
    - What: Descriptor-driven CEF loader compatibility; proven Bilibili CEF 80.1.15 descriptor.
    - Scope: Default-on `LMISXH_AKMOCL_CEF` gate. Before any write, the descriptor requires the `libcef.dll` basename and all three expected RVA byte sequences.
    - Provenance and checks: Original runtime change; see [provenance](../patches/wine/provenance.md), apply check, and x86_64 loader compile.

Add a regional descriptor only with reverse-engineering evidence for its complete hash/RVA/byte contract.

## Winsock

- ID: `wine-winsock-address-list-sort`
- File: `patches/wine/0005-ws2_32-address-list-sort.patch`
- Component/base: WineCX <!-- pin:wine.commit|code -->`a54b8240683e92bf4c15cb1ba6bf92a9539bd768`<!-- /pin --> (Wine <!-- pin:wine.version -->11.17<!-- /pin -->)
- Source/author: Original change for this repository.
- License: LGPL-2.1-or-later (Wine)
- Gate: None. Applies to the `rosetta-x86_64` target.
- Inactive behavior: Not applicable; the ioctl exists in the target.
- Automated gate: Hash, clean `git apply --check`, and an x86_64 build.
- Manual gate: Chromium asynchronous DNS uses the runtime resolver without `--disable-features=AsyncDns`.
- Removal: Drop when WineCX implements `SIO_ADDRESS_LIST_SORT`.

Chromium's asynchronous DNS resolver calls `WSAIoctl(SIO_ADDRESS_LIST_SORT)` to order IPv6 destinations. Wine returned `WSAEOPNOTSUPP`, so CEF retried the call and an OAuth page stayed blank. The patch adds the constant and handles the ioctl. The returned list keeps the supplied order. Windows applies RFC 6724 destination ordering, which needs the source addresses. Chromium only needs a valid list. The handler bounds `iAddressCount` against the input size before the address-array arithmetic. It validates every address before the in-place shortcut. It forwards the completed overlapped call through `IOCTL_AFD_WINE_COMPLETE_ASYNC` with `afd_complete_async_params`.

## AppContainer

- ID: `wine-userenv-appcontainer`
- File: `patches/wine/0004-userenv-appcontainer-apis.patch`
- Component/base: WineCX <!-- pin:wine.commit|code -->`a54b8240683e92bf4c15cb1ba6bf92a9539bd768`<!-- /pin --> (Wine <!-- pin:wine.version -->11.17<!-- /pin -->)
- Source/author: Original change for this repository, derived from the client's scoped `UserenvCompat.c`.
- License: LGPL-2.1-or-later (Wine)
- Gate: None. Applies to the `rosetta-x86_64` target.
- Inactive behavior: Not applicable; the exports exist in the target.
- Automated gate: Hash, clean `git apply --check`, and an x86_64 build.
- Manual gate: Chromium's sandbox loads the AppContainer functions without a process-local `userenv.dll`.
- Removal: Drop when WineCX implements the remaining AppContainer surface.

Chromium's sandbox loads these functions by name and checks that they resolve. Wine 11.17 exports `CreateAppContainerProfile` only as a stub. The patch adds `DeriveAppContainerSidFromAppContainerName`, `DeleteAppContainerProfile`, `GetAppContainerRegistryLocation`, and `GetAppContainerFolderPath`. The SID uses SHA-256 of the lowercased container name folded into an `APP_PACKAGE` SID; the registry and folder locations return `E_NOTIMPL`, which the sandbox does not require.

The patch also exports `CreateAppContainerToken` and `GetAppContainerNamedObjectPath` from `kernelbase.dll` as stubs. Chromium resolves both names before it creates a renderer. Without the exports, the `GetProcAddress` check aborts the browser with `app_container_base.cc:54 Check failed: fn`. The stubs return `FALSE` with `ERROR_CALL_NOT_IMPLEMENTED`; the sandbox falls back instead of aborting.

## CN

The CN patches share one default-off gate, `LMISXH_AKMOCL_CN`: only exactly `1` enables them. Any other value keeps Wine's normal route.

- [`wine-cn-bilibili-layered-child`](../patches/wine/0007-win32u-winemac-bilibili-layered-child.patch)
    - What: Keeps Chromium's layered proxies for login and payment drawable inside the root Wine window.
    - Scope: CN gate and `PCGamePlatform.exe`. Login keeps the `CMyWebViewDlg` parent-chain route. Payment also requires an exact `Chrome_WidgetWin_0` `WS_CHILD` non-popup with an immediate `CefBrowserWindow` parent, a non-child `GA_ROOT` of class `CPayDlg_P_` plus a nonempty suffix, and matching HWND/parent/root process IDs. Only parent links count. The driver still requires `Chrome.WindowTranslucent` and a layered surface. Each accepted child gets an in-root view with independent color/shape images, source alpha, `SourceConstantAlpha`, root-client geometry, reparent/hide cleanup, and USER hit testing.
    - Provenance and checks: Original runtime change; hash, apply check, offline classifier/contract tests, `win32u`/`winemac` compile, Bilibili payment-window rendering check.

- [`wine-cn-bilibili-join-all-spaces`](../patches/wine/0008-winemac-bilibili-join-all-spaces.patch)
    - What: Makes the Bilibili platform window join all Spaces, so it stays visible over a game in a native fullscreen Space.
    - Scope: CN gate and `PCGamePlatform.exe` (the `macdrv_is_bilibili_platform_process()` test of the first CN patch). In `adjustFullScreenBehavior:` it clears `FullScreenPrimary` and sets `CanJoinAllSpaces` and `FullScreenAuxiliary`.
    - Provenance and checks: Original runtime change; hash, apply check after the first CN patch, `winemac` compile.

Remove a patch when the pinned WineCX supplies the behavior or the route is no longer needed.

## Menu

- ID: `wine-menu-command-q-quit`
- File: `patches/wine/0011-winemac-command-q-quit.patch`
- Component/base: WineCX <!-- pin:wine.commit|code -->`a54b8240683e92bf4c15cb1ba6bf92a9539bd768`<!-- /pin --> (Wine <!-- pin:wine.version -->11.17<!-- /pin -->)
- Source/author: Original runtime change, runtime maintainers
- License: LGPL-2.1-or-later (Wine)
- Gate: `LMISXH_AKMOCL_MENU` (default on: unset or exactly `1`)
- Inactive behavior: Missing, `0`, or invalid values keep Wine's Option-Command-Q key equivalent for Quit.
- Automated gate: Hash, clean `git apply --check` in lock order, `winemac.so` compile in the single x86_64 build
- Manual gate: The app menu shows Command-Q for Quit. Option-Command-Q does not quit. Option-Command-H still hides other applications.
- Removal: Drop when the client no longer needs Command-Q to quit, or when Wine offers an equivalent setting

The patch changes one line in `dlls/winemac.drv/cocoa_app.m`. It sets the Quit item to the Command modifier only. Hide Others (Option-Command-H) and the other menu items keep their masks.

## Fullscreen

- ID: `wine-fullscreen-native-space`
- File: `patches/wine/0009-winemac-native-fullscreen-space.patch`
- Component/base: WineCX <!-- pin:wine.commit|code -->`a54b8240683e92bf4c15cb1ba6bf92a9539bd768`<!-- /pin --> (Wine <!-- pin:wine.version -->11.17<!-- /pin -->)
- Source/author: Original runtime change, runtime maintainers
- License: LGPL-2.1-or-later (Wine)
- Gate: `LMISXH_AKMOCL_FULLSCREEN` (default on: unset or exactly `1`), read once in `setup_options`
- Inactive behavior: Missing, `0`, or invalid values keep the screen-sized window at `NSStatusWindowLevel + 1`
- Automated gate: Hash, clean `git apply --check` alone and after the `cn` family on both Wine branches, `cocoa_app.m` syntax check
- Manual gate: A borderless fullscreen game window enters its own Space. Leaving the Space by the user stays left. A Wine resize below screen size leaves the Space. The cursor clip still holds after each change.
- Removal: Drop when the client no longer needs a native Space, or when WineCX offers an equivalent control

A window is a candidate only when the gate is on, it participates in the window cycle, it is not a utility window, and it has no parent. Its last content rect from Wine must cover a screen, or the screen below the camera housing. A window with `CanJoinAllSpaces` or `Stationary` set, or one that ignores the cycle, is never a candidate. A window that prevents app activation or has no foreground cannot enter a Space. A window already in a Space stays there while another process's modal dialog disables it. This keeps helper windows, such as the platform notice window, out of the feature. The `cn` patch `wine-cn-bilibili-join-all-spaces` also sets these bits for the Bilibili platform process.

The patch enters the Space with a deferred `toggleFullScreen:` call. It never changes the window frame inside a Space. It reposts the actual frame to Wine at most twice for one requested rect. When the rect from Wine no longer covers the screen, the patch leaves the Space. A user exit blocks automatic re-entry until the rect changes or the window is ordered out. The patch logs decisions in the `macdrv` debug channel. In a Space the close button is enabled and sends the normal Win32 close.

The patch turns the feature off for the whole process when the program is `PlatformProcess.exe` or `PlatformProcess.original.helper.exe`, because the notice helper inherits the gate. This check does not depend on `LMISXH_AKMOCL_CN`.
