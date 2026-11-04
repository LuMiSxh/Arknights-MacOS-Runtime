# Patch registry

[`runtime.lock.json`](../runtime.lock.json) holds the machine-readable ordered registry. Before release, each entry must name its upstream source, author, license, gate, inactive behavior, test, and removal condition. The entries document provenance. They do not replace the corresponding-source, notice, and redistribution review that a runtime binary requires.

The ACE, CEF, and CN patches target WineCX <!-- pin:wine.commit|code -->`e0aa380780b73e20fabcfe78fd42713b94929a53`<!-- /pin --> and keep Wine's LGPL-2.1-or-later license.

## Audio

- ID: `wine-audio-default-output`
- File: `patches/shared/wine/audio/0001-winecoreaudio-default-output.patch`
- Component/base: WineCX <!-- pin:wine.commit|code -->`e0aa380780b73e20fabcfe78fd42713b94929a53`<!-- /pin --> (Wine <!-- pin:wine.version -->11.17<!-- /pin -->)
- Source/author: Wine draft MR 11370, commits `4d143f4c` and `65140f31`, Rhodri Richards
- License: LGPL-2.1-or-later
- Gate: `ARKNIGHTS_RUNTIME_AUDIO_FOLLOW_DEFAULT_OUTPUT=1`, parsed once per process
- Inactive behavior: Normal Wine endpoint enumeration and routing
- Automated gate: Hash and clean `git apply --check`; patched Wine compile
- Manual gate: Active shared render stream follows default device across switch/disconnect/reconnect
- Removal: Drop when the pinned WineCX has equivalent behavior

The MR is a draft. Capture and exclusive streams are unchanged.

## Hardware Cursor

- ID: `wine-hardware-cursor-suppression`
- File: `patches/shared/wine/hardware-cursor/0001-ntdll-hide-software-cursor-asset.patch`
- Component/base: WineCX <!-- pin:wine.commit|code -->`e0aa380780b73e20fabcfe78fd42713b94929a53`<!-- /pin --> (Wine <!-- pin:wine.version -->11.17<!-- /pin -->)
- Source/author: Original runtime change; motivated by the [reported PC cursor stutter](https://www.reddit.com/r/arknights/comments/1vorlzp/pc_client_fix_for_the_annoying_mouse_stuttering/)
- License: LGPL-2.1-or-later (Wine)
- Gate: Exact `ARKNIGHTS_RUNTIME_HARDWARE_CURSOR=1`, checked during shared file-name resolution
- Inactive behavior: Missing, `0`, or invalid values use Wine's normal path resolution
- Automated gate: Hash, clean `git apply --check`, focused `ntdll.so` build, Wine test-object compilation for exact/case variants and attribute APIs
- Manual gate: Compare the software sprite with the macOS pointer, using the exact asset
- Removal: Drop if the client stops using the asset or Wine gains an equivalent control

The filter matches the case-insensitive final basename `a9d41799f1af1868f2db495671227cd4.bin` (Yostar Global/Japan/Korea and Taiwan) or `f7bcd64480c4566f25d65d642f5fba95.bin` (China — Bilibili). It converts successful lookups and `STATUS_NO_SUCH_FILE` into `STATUS_OBJECT_NAME_NOT_FOUND` and clears the resolved Unix path, so create-if-missing cannot recreate the file. Shared name resolution makes `NtCreateFile`, `NtQueryAttributesFile`, and `NtQueryFullAttributesFile` see the same hidden asset. The patch copies and modifies no game asset.

## Runtime capability manifest

`Libraries/runtime-capabilities.json` is the versioned producer contract that consumers read from the packaged runtime tree. Schema version 2 advertises hardware-cursor support and MetalFX spatial-upscaling support. The optional `nativeFullscreenSpace` boolean advertises the fullscreen patch. The optional `aceCompat` boolean advertises the full ACE patch set for the lane, and `nativeArm64` identifies a runtime that runs without Rosetta. The native-arm64 archive ships `runtime-capabilities-arm64.json`, which differs from the x86_64 manifest. Release validation checks the manifest against the pinned patch semantics and requires the packaged copy to match the source. Consumers treat missing optional keys as false and use conservative defaults without the manifest.

## Performance

### Release present statistics gate

- ID: `dxmt-skip-release-present-statistics`
- File: `patches/shared/dxmt/performance/0001-dxmt-skip-release-present-statistics.patch`
- Component/base: DXMT <!-- pin:dxmt.commit|code -->`9839e55f98d4aca103957ee4132d6395a325a9ed`<!-- /pin -->
- Source/author: Original runtime optimization, runtime maintainers
- License: LGPL-2.1-or-later (DXMT)
- Gate: `DXMT_DEBUG`; debug builds keep statistics aggregation and HUD updates, release builds skip both
- Inactive behavior: Frame counters, measurements, advancement, latency waits, and resets unchanged
- Automated gate: Hash, clean application, both DXMT architectures, release/debug preprocessor contract
- Manual gate: Startup, rendering, and frametime comparison against the clean-removal control (same scene, settings, runtime)
- Removal: Drop when the pinned DXMT removes the release-dead work or gains an equivalent build option

Both `Present` paths keep `UpdateStatistics` behind `DXMT_DEBUG`, which avoids its per-present `std::format` calls in release builds. `PresentBoundary` gates the rolling statistics aggregation the same way. Release builds keep the frame counters and synchronization.

## ACE

All ACE patches use the exact gate `ARKNIGHTS_RUNTIME_ACE_COMPACT=1`. A missing, `0`, or other value keeps Wine's normal route. Every patch requires hash verification and clean application. All four are Endfield FineWine ports ([provenance](../patches/shared/wine/ace/provenance.md)).

- [`wine-ace-ntoskrnl-surface`](../patches/shared/wine/ace/ntoskrnl/0001-ntoskrnl-compatibility-surface.patch)
    - What: Kernel exports and process metadata for the ACE client: current-thread process, image-name, exit-status, audit-parameter, and persistent-thread-state surfaces.
    - Scope: Compatibility-only routes use the ACE gate. `PsGetProcessImageFileName` and `PsGetProcessExitStatus` stay unconditional for valid process objects and follow their kernel `_In_` contract.
    - Checks: compile both architectures; exercise gated and general routes.
- [`wine-ace-dispatcher-spoof`](../patches/x86/wine/ace/dispatcher/0001-kernel32-ace-dispatcher-spoof.patch)
    - What: x86-64 dispatcher lookup compatibility.
    - Scope: ACE gate and Rosetta x86-64 build only.
    - Checks: compile; dispatcher startup.
- [`wine-ace-rosetta-workarounds`](../patches/x86/wine/ace/rosetta/0001-macos-rosetta-ace-workarounds.patch)
    - What: Bounded NOP and ACE privileged-instruction handling under Rosetta.
    - Scope: ACE gate; existing CrossOver CET/XGETBV handling is untouched.
    - Checks: compile; exercise inactive and enabled routes.
- [`wine-ace-relative-wait`](../patches/shared/wine/ace/timing/0001-ntdll-ace-qpc-relative-wait.patch)
    - What: Relative `NtDelayExecution` timing route.
    - Scope: ACE gate and negative relative waits only; other waits are unchanged.
    - Checks: focused wait tests.

## CEF

The CEF family uses the exact gate `ARKNIGHTS_RUNTIME_CEF_COMPAT=1`. An absent, `0`, or invalid value keeps Wine's normal route. If the CEF variable is absent, `ARKNIGHTS_RUNTIME_CN_COMPAT=1` keeps the legacy Bilibili behavior.

- [`wine-cef-bilibili-stackbase`](../patches/shared/wine/cef/0001-ntdll-cef-compatibility.patch)
    - What: Descriptor-driven CEF loader compatibility; proven Bilibili CEF 80.1.15 descriptor.
    - Scope: Explicit CEF gate; legacy CN fallback only when CEF is absent. Before any write, the descriptor requires the `libcef.dll` basename and all three expected RVA byte sequences.
    - Provenance and checks: Original runtime change; see [provenance](../patches/shared/wine/cef/provenance.md), apply check, and x86_64 loader compile.

Add a regional descriptor only with reverse-engineering evidence for its complete hash/RVA/byte contract.

## Winsock

- ID: `wine-winsock-address-list-sort`
- File: `patches/shared/wine/winsock/0001-ws2_32-implement-address-list-sort.patch`
- Component/base: WineCX `c8ef4872c1d53120b80aa92185fc7e295d94d092` (Wine 11.17, branch `arm64-1117`)
- Source/author: Original change for this repository.
- License: LGPL-2.1-or-later (Wine)
- Gate: None. Applies to both targets.
- Inactive behavior: Not applicable; the ioctl exists in both lanes.
- Automated gate: Hash, clean `git apply --check`, and builds for both targets.
- Manual gate: Chromium asynchronous DNS uses the runtime resolver without `--disable-features=AsyncDns`.
- Removal: Drop when WineCX implements `SIO_ADDRESS_LIST_SORT`.

Chromium's asynchronous DNS resolver calls `WSAIoctl(SIO_ADDRESS_LIST_SORT)` to order IPv6 destinations. Wine returned `WSAEOPNOTSUPP`, so CEF retried the call and an OAuth page stayed blank. The patch adds the constant and handles the ioctl. The returned list keeps the supplied order; Windows applies RFC 6724 destination ordering, which needs the source addresses, and Chromium only needs a valid list.

## AppContainer

- ID: `wine-userenv-appcontainer`
- File: `patches/shared/wine/appcontainer/0001-userenv-implement-appcontainer-apis.patch`
- Component/base: WineCX `c8ef4872c1d53120b80aa92185fc7e295d94d092` (Wine 11.17, branch `arm64-1117`)
- Source/author: Original change for this repository, derived from the client's scoped `UserenvCompat.c`.
- License: LGPL-2.1-or-later (Wine)
- Gate: None. Applies to both targets.
- Inactive behavior: Not applicable; the exports exist in both lanes.
- Automated gate: Hash, clean `git apply --check`, and builds for both targets.
- Manual gate: Chromium's sandbox loads the AppContainer functions without a process-local `userenv.dll`.
- Removal: Drop when WineCX implements the remaining AppContainer `userenv.dll` surface.

Chromium's sandbox loads these functions by name and checks that they resolve. Wine 11.17 exports `CreateAppContainerProfile` only as a stub. The patch adds `DeriveAppContainerSidFromAppContainerName`, `DeleteAppContainerProfile`, `GetAppContainerRegistryLocation`, and `GetAppContainerFolderPath`. The SID uses SHA-256 of the lowercased container name folded into an `APP_PACKAGE` SID; the registry and folder locations return `E_NOTIMPL`, which the sandbox does not require.

## CN

The CN family contains only the Bilibili windowing patches. They use the exact gate `ARKNIGHTS_RUNTIME_CN_COMPAT=1`. A missing, `0`, or other value keeps Wine's normal route.

- [`wine-cn-bilibili-layered-child`](../patches/shared/wine/cn/windowing/0001-win32u-winemac-bilibili-layered-child.patch)
    - What: Keeps Chromium's layered proxies for login and payment drawable inside the root Wine window.
    - Scope: CN gate and `PCGamePlatform.exe`. Login keeps the `CMyWebViewDlg` parent-chain route. Payment also requires an exact `Chrome_WidgetWin_0` `WS_CHILD` non-popup with an immediate `CefBrowserWindow` parent, a non-child `GA_ROOT` of class `CPayDlg_P_` plus a nonempty suffix, and matching HWND/parent/root process IDs. Only parent links count. The driver still requires `Chrome.WindowTranslucent` and a layered surface. Each accepted child gets an in-root view with independent color/shape images, source alpha, `SourceConstantAlpha`, root-client geometry, reparent/hide cleanup, and USER hit testing.
    - Provenance and checks: Original runtime change; hash, apply check, offline classifier/contract tests, `win32u`/`winemac` compile, Bilibili payment-window rendering check.

- [`wine-cn-bilibili-join-all-spaces`](../patches/shared/wine/cn/windowing/0002-winemac-bilibili-join-all-spaces.patch)
    - What: Makes the Bilibili platform window join all Spaces, so it stays visible over a game in a native fullscreen Space.
    - Scope: CN gate and `PCGamePlatform.exe` (the `macdrv_is_bilibili_platform_process()` test of the first CN patch). In `adjustFullScreenBehavior:` it clears `FullScreenPrimary` and sets `CanJoinAllSpaces` and `FullScreenAuxiliary`.
    - Provenance and checks: Original runtime change; hash, apply check after the first CN patch, `winemac` compile.

Remove a patch when the pinned WineCX supplies the behavior or the route is no longer needed.

## Menu

- ID: `wine-menu-command-q-quit`
- File: `patches/shared/wine/menu/0001-winemac-command-q-quit.patch`
- Component/base: WineCX <!-- pin:wine.commit|code -->`e0aa380780b73e20fabcfe78fd42713b94929a53`<!-- /pin --> (Wine <!-- pin:wine.version -->11.17<!-- /pin -->)
- Source/author: Original runtime change, runtime maintainers
- License: LGPL-2.1-or-later (Wine)
- Gate: None. The patch is always active in the `combined` stage. It has no `ARKNIGHTS_RUNTIME_` variable, because the client needs the standard Command-Q key equivalent in every build.
- Inactive behavior: None. No inactive route exists. Builds without the patch keep Wine's Option-Command-Q key equivalent for Quit.
- Automated gate: Hash, clean `git apply --check` in lock order, `winemac.so` compile in the `combined` build
- Manual gate: The app menu shows Command-Q for Quit. Option-Command-Q does not quit. Option-Command-H still hides other applications.
- Removal: Drop when the client no longer needs Command-Q to quit, or when Wine offers an equivalent setting

The patch changes one line in `dlls/winemac.drv/cocoa_app.m`. It sets the Quit item to the Command modifier only. Hide Others (Option-Command-H) and the other menu items keep their masks.

## Fullscreen

- ID: `wine-fullscreen-native-space`
- File: `patches/shared/wine/fullscreen/0001-winemac-native-fullscreen-space.patch`
- Component/base: WineCX <!-- pin:wine.commit|code -->`e0aa380780b73e20fabcfe78fd42713b94929a53`<!-- /pin --> (Wine <!-- pin:wine.version -->11.17<!-- /pin -->)
- Source/author: Original runtime change, runtime maintainers
- License: LGPL-2.1-or-later (Wine)
- Gate: Exact `ARKNIGHTS_RUNTIME_NATIVE_FULLSCREEN_SPACE=1`, read once in `setup_options`
- Inactive behavior: Missing, `0`, or invalid values keep the screen-sized window at `NSStatusWindowLevel + 1`
- Automated gate: Hash, clean `git apply --check` alone and after the `cn` family on both Wine branches, `cocoa_app.m` syntax check
- Manual gate: A borderless fullscreen game window enters its own Space. Leaving the Space by the user stays left. A Wine resize below screen size leaves the Space. The cursor clip still holds after each change.
- Removal: Drop when the client no longer needs a native Space, or when WineCX offers an equivalent control

A window is a candidate only when the gate is on, it participates in the window cycle, it is not a utility window, it has no parent, and the last content rect from Wine covers a screen (or the screen below the camera housing). A window that has `CanJoinAllSpaces` or `Stationary` set or ignores the cycle is never a candidate. A window that prevents app activation or has no foreground cannot enter a Space, but a window already in a Space stays there while another process's modal dialog disables it. This keeps helper windows, such as the platform notice window, out of the feature. The `cn` patch `wine-cn-bilibili-join-all-spaces` also sets these bits for the Bilibili platform process.

The patch enters the Space with a deferred `toggleFullScreen:` call. It never changes the window frame inside a Space. It reposts the actual frame to Wine at most twice for one requested rect. When the rect from Wine no longer covers the screen, the patch leaves the Space. A user exit blocks automatic re-entry until the rect changes or the window is ordered out. The patch logs decisions in the `macdrv` debug channel. In a Space the close button is enabled and sends the normal Win32 close.

The patch turns the feature off for the whole process when the program is `PlatformProcess.exe` or `PlatformProcess.original.helper.exe`, because the notice helper inherits the gate. This check does not depend on `ARKNIGHTS_RUNTIME_CN_COMPAT`.

## Address space

- ID: `wine-arm64-address-space`
- File: `patches/arm/wine/address-space/0001-ntdll-relocate-the-shared-user-data.patch`
- Component/base: WineCX `c8ef4872c1d53120b80aa92185fc7e295d94d092` (Wine 11.17, branch `arm64-1117`)
- Source/author: Port of [`metalsharp/MetalSharp-Wine`](https://github.com/metalsharp/MetalSharp-Wine) patches `0003`, `0008`, and `0016`, Avery Felts. See [provenance](../patches/arm/wine/address-space/provenance.md).
- License: LGPL-2.1-or-later (Wine)
- Gate: Target only. The `native-arm64` target has no runtime flag, because the loader cannot start without the relocation.
- Inactive behavior: The `rosetta-x86_64` target never receives the patch, and keeps `KUSER_SHARED_DATA` at `0x7ffe0000`.
- Automated gate: Hash, clean `git apply --check` after the shared families, ARM64 build, and `wine cmd /c ver` without the cross-architecture entitlement
- Manual gate: A 64-bit Windows program starts under FEX, and the game reaches the login screen.
- Removal: Drop when macOS makes the low 4 GB mappable for an ad-hoc signed arm64 loader, or when a distributable signing identity carries the cross-architecture entitlement.

macOS keeps the low 4 GB of an arm64 process as a hard pagezero. `KUSER_SHARED_DATA` and the first TEB block belong inside that range. The patch exports the page address to the PE side, moves the page to `MM_SHARED_USER_DATA_VA + 4 GB` when the canonical mapping fails, lets the first 64-bit TEB block take an address above 4 GB, and emulates ARM64 loads that fault on the canonical address.

macOS also reserves the main executable's Mach-O region just above 4 GB. The patch probes upward from 4 GB for the first page that `mach_vm_map` accepts, then uses that address as the floor for thread data, stacks, and image fallbacks. A fixed `limit_4g` floor fails because the reservation covers unmapped holes too.

The write and execute page handling of the reference patch is split out. WineCX 11.17 already flips pages in `virtual_handle_fault`, and [`wine-arm64-wx-pages`](#write-and-execute-pages) adds the `mprotect_exec` half.

## FEX

- ID: `wine-arm64-fex-modules`
- File: `patches/arm/wine/fex/0001-wine.inf-use-fex-modules.patch`
- Component/base: WineCX `c8ef4872c1d53120b80aa92185fc7e295d94d092` (Wine 11.17, branch `arm64-1117`)
- Source/author: Registry part of [`metalsharp/MetalSharp-Wine`](https://github.com/metalsharp/MetalSharp-Wine) patch `0004`, Avery Felts. See [provenance](../patches/arm/wine/fex/provenance.md).
- License: LGPL-2.1-or-later (Wine)
- Gate: Target only. The `native-arm64` target always uses the FEX modules.
- Inactive behavior: The `rosetta-x86_64` target keeps `xtajit64.dll` and `xtajit.dll`.
- Automated gate: Hash, clean `git apply --check`, ARM64 build, and a fresh prefix whose `Wow64` values name existing modules.
- Manual gate: A minimal x86_64 PE starts under FEX.
- Removal: Drop when WineCX ships ARM64 Wow64 values that name the FEX modules.

Wine's `wine.inf` points `Wow64\amd64` at `xtajit64.dll` and `Wow64\x86` at `xtajit.dll`. The ARM64 build ships `libarm64ecfex.dll` and `libwow64fex.dll` instead. Without the wiring, an x86_64 image loads but never starts.

## FEX lookup cache

- ID: `fex-arm64ec-lookup-cache-commit`
- File: `patches/arm/fex/lookup-cache-commit/0001-lookup-cache-commit-eagerly.patch`
- Component/base: FEX `4efc3abc8aca8a0d3a8aca1f153ef6c4299f4426` (fork `dappermint/FEX`)
- Source/author: Original change for this repository.
- License: MIT (FEX)
- Gate: Target only. The `native-arm64` target always commits the lookup cache eagerly.
- Inactive behavior: Other hosts ignore the commit flag in `FEXCore::Allocator::VirtualAlloc`.
- Automated gate: Hash, clean `git apply --check`, ARM64 build, and an x86_64 PE that compiles its first block.
- Manual gate: The x86_64 PE reaches its entry point.
- Removal: Drop when FEX commits the lookup cache on Windows, or when Wine runs the `ResetToConsistentState` callback for reserved pages.

FEX reserves the lookup cache with `Commit=false` and commits faulting pages from its `ResetToConsistentState` callback. Wine returns `STATUS_ACCESS_VIOLATION` instead and never calls the callback, so the first block lookup faulted on the same instruction forever. The patch commits the region up front.

## Mono

- ID: `wine-arm64-skip-mono`
- File: `patches/arm/wine/mono/0001-mscoree-skip-mono-on-native-arm64.patch`
- Component/base: WineCX `c8ef4872c1d53120b80aa92185fc7e295d94d092` (Wine 11.17, branch `arm64-1117`)
- Source/author: Original change for this repository.
- License: LGPL-2.1-or-later (Wine)
- Gate: Target only. The `native-arm64` target always skips the Wine Mono install.
- Inactive behavior: The `rosetta-x86_64` target keeps the stock `install_wine_mono()` path.
- Automated gate: Hash, clean `git apply --check`, and a fresh ARM64 prefix that does not spawn `msiexec` or the Mono helpers.
- Manual gate: `wine cmd /c ver` on a fresh prefix exits 0 without `WINEDLLOVERRIDES`.
- Removal: Drop when the ARM64 lane can install Wine Mono without the entitlement, or when the runtime ships a 64-bit-only .NET replacement.

Wine Mono's support package runs 32-bit and ARM64EC helper executables. The 32-bit helpers need memory below 4 GB, which macOS refuses without the cross-architecture entitlement. Wine retries the install on every prefix creation and opens a download dialog when the package is not cached. Arknights does not use .NET, so the ARM64 lane skips the install.

## ARM64EC unix calls

- ID: `wine-arm64-unix-call`
- File: `patches/arm/wine/arm64ec-unix-call/0001-ntdll-fix-the-arm64ec-unix-call-table.patch`
- Component/base: WineCX `c8ef4872c1d53120b80aa92185fc7e295d94d092` (Wine 11.17, branch `arm64-1117`)
- Source/author: Original change for this repository.
- License: LGPL-2.1-or-later (Wine)
- Gate: Target only. The `native-arm64` target always applies the guard.
- Inactive behavior: The `rosetta-x86_64` target keeps the CodeWeavers `unix_pe_module_loaded` hook.
- Automated gate: Hash, clean `git apply --check`, ARM64 build, and an x86_64 PE that loads `libarm64ecfex.dll`.
- Manual gate: The x86_64 PE reaches its entry point.
- Removal: Drop when WineCX guards the hook with `__arm64ec__` or moves it into the ARM64EC table.

ARM64EC compiles with `__x86_64__` defined. The PE side called `unix_pe_module_loaded`, but the aarch64 `ntdll.so` table has no such entry. The call read past the table and jumped into unrelated data. The guard keeps the hook on x86_64 and excludes it from ARM64EC.

## Mixed host pages

- ID: `wine-arm64-wx-pages`
- File: `patches/arm/wine/wx-pages/0001-ntdll-keep-mixed-host-pages-writable.patch`
- Component/base: WineCX `c8ef4872c1d53120b80aa92185fc7e295d94d092` (Wine 11.17, branch `arm64-1117`)
- Source/author: Port of the `mprotect_exec` hunk in [`metalsharp/MetalSharp-Wine`](https://github.com/metalsharp/MetalSharp-Wine) patch `0003`, Avery Felts. See [provenance](../patches/arm/wine/wx-pages/provenance.md).
- License: LGPL-2.1-or-later (Wine)
- Gate: Target only. The `native-arm64` target always applies the change.
- Inactive behavior: Other hosts keep the existing `mprotect` request.
- Automated gate: Hash, clean `git apply --check`, ARM64 build, and an ARM64EC image whose hybrid metadata is written at load time.
- Manual gate: The x86_64 PE starts under FEX.
- Removal: Drop when WineCX handles mixed host pages on arm64 macOS.

macOS refuses RWX without `MAP_JIT`. A 16K host page can mix executable 4K pages with writable ones, so `NtProtectVirtualMemory(PAGE_READWRITE)` on an image section failed with `STATUS_ACCESS_DENIED`. Write faults on the mixed page were not delivered to the signal handler, so the patch drops `PROT_EXEC` instead of `PROT_WRITE`. The page stays writable, and `virtual_handle_fault` flips it for an execute fault. On macOS 27.2 the execute fault is also not delivered to the process, so this patch is necessary but not sufficient for JIT code. See [`docs/arm/results.md`](arm/results.md#16k-host-pages-and-the-jit-code-buffer).

## ARM64 ID registers

- ID: `wine-arm64-id-registers`
- File: `patches/arm/wine/id-registers/0001-ntdll-synthesize-arm64-id-registers.patch`
- Component/base: WineCX `c8ef4872c1d53120b80aa92185fc7e295d94d092` (Wine 11.17, branch `arm64-1117`)
- Source/author: Port of the ID-register hunk in [`metalsharp/MetalSharp-Wine`](https://github.com/metalsharp/MetalSharp-Wine) patch `0004`, Avery Felts. See [provenance](../patches/arm/wine/id-registers/provenance.md).
- License: LGPL-2.1-or-later (Wine)
- Gate: Target only. The `native-arm64` target always applies the implementation.
- Inactive behavior: Linux keeps the `AT_HWCAP_CPUID` path; other hosts keep the stub.
- Automated gate: Hash, clean `git apply --check`, ARM64 build, and a prefix whose `CentralProcessor\0` values include `CP 4030`.
- Manual gate: FEX `ProcessInit` returns success and starts an x86_64 program.
- Removal: Drop when WineCX carries the macOS ID-register implementation.

macOS does not let EL0 read the ID registers. `get_core_id_regs_arm64` was a stub, so FEX read zero features from the processor registry key and hit its `FetchHostFeatures` assert. The patch builds the values from the `hw.optional.arm.*` sysctls and the cache line size.
