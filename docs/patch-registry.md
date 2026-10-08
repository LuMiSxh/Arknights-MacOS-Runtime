# Patch registry

[`runtime.lock.json`](../runtime.lock.json) holds the machine-readable ordered registry. Before release, each entry must name its upstream source, author, license, gate, inactive behavior, test, and removal condition. The entries document provenance. They do not replace the corresponding-source, notice, and redistribution review that a runtime binary requires.

The ACE, CEF, and CN patches target WineCX `e0aa380780b73e20fabcfe78fd42713b94929a53` and keep Wine's LGPL-2.1-or-later license.

## Audio

- ID: `wine-audio-default-output`
- File: `patches/wine/audio/0001-winecoreaudio-default-output.patch`
- Component/base: WineCX `e0aa380780b73e20fabcfe78fd42713b94929a53` (Wine 11.17)
- Source/author: Wine draft MR 11370, commits `4d143f4c` and `65140f31`, Rhodri Richards
- License: LGPL-2.1-or-later
- Gate: `ARKNIGHTS_RUNTIME_AUDIO_FOLLOW_DEFAULT_OUTPUT=1`, parsed once per process
- Inactive behavior: Normal Wine endpoint enumeration and routing
- Automated gate: Hash and clean `git apply --check`; patched Wine compile
- Manual gate: Active shared render stream follows default device across switch/disconnect/reconnect
- Removal: Drop when the pinned WineCX has equivalent behavior

The MR is a draft. Capture and exclusive streams are unchanged.

## Cursor

- ID: `dxmt-cursor-frame-latency`
- File: `patches/dxmt/cursor/0001-dxmt-command-queue-configurable-frame-latency.patch`
- Component/base: DXMT `7c8dee1c2d73415301ceb7d1fa810861cef4cd67` (`v0.80-244-g7c8dee1`)
- Source/author: Original runtime experiment, runtime maintainers
- License: LGPL-2.1-or-later (DXMT)
- Gate: `ARKNIGHTS_RUNTIME_DXMT_MAX_FRAME_LATENCY=0..3`, read once on first command queue
- Inactive behavior: Missing or invalid input retains upstream maximum `3`
- Automated gate: Hash, clean `git apply --check`, both DXMT architectures compile
- Manual gate: FPS, frame-pacing, and cursor comparison at 3, 2, 1, 0
- Removal: Drop if DXMT gains an equivalent control or evidence rejects the experiment

Value `0` is an Arknights extension. It waits for the completion fence of the current frame after commit, so no completed GPU frame stays queued. It is not DXGI zero-as-default, and it can reduce throughput or smoothness.

## Hardware Cursor

- ID: `wine-hardware-cursor-suppression`
- File: `patches/wine/hardware-cursor/0001-ntdll-hide-software-cursor-asset.patch`
- Component/base: WineCX `e0aa380780b73e20fabcfe78fd42713b94929a53` (Wine 11.17)
- Source/author: Original runtime change; motivated by the [reported PC cursor stutter](https://www.reddit.com/r/arknights/comments/1vorlzp/pc_client_fix_for_the_annoying_mouse_stuttering/)
- License: LGPL-2.1-or-later (Wine)
- Gate: Exact `ARKNIGHTS_RUNTIME_HARDWARE_CURSOR=1`, checked during shared file-name resolution
- Inactive behavior: Missing, `0`, or invalid values use Wine's normal path resolution
- Automated gate: Hash, clean `git apply --check`, focused `ntdll.so` build, Wine test-object compilation for exact/case variants and attribute APIs
- Manual gate: Compare the software sprite with the macOS pointer, using the exact asset
- Removal: Drop if the client stops using the asset or Wine gains an equivalent control

The filter matches the case-insensitive final basename `a9d41799f1af1868f2db495671227cd4.bin` (Yostar Global/Japan/Korea and Taiwan) or `f7bcd64480c4566f25d65d642f5fba95.bin` (China — Bilibili). It converts successful lookups and `STATUS_NO_SUCH_FILE` into `STATUS_OBJECT_NAME_NOT_FOUND` and clears the resolved Unix path, so create-if-missing cannot recreate the file. Shared name resolution makes `NtCreateFile`, `NtQueryAttributesFile`, and `NtQueryFullAttributesFile` see the same hidden asset. The patch copies and modifies no game asset.

## Runtime capability manifest

`Libraries/runtime-capabilities.json` is the versioned producer contract that consumers read from the packaged runtime tree. Schema version 1 advertises the DXMT frame-latency range and default, hardware-cursor support, and MetalFX spatial-upscaling support. Release validation checks the manifest against the pinned patch semantics and requires the packaged copy to match the source. MetalFX upscaling is upstream DXMT behavior (`DXMT_METALFX_SPATIAL_SWAPCHAIN=1`), not a patch, so validation requires that switch in the packaged `DXMT/x64/d3d11.dll`. Consumers use conservative defaults without the manifest.

## Performance

- ID: `dxmt-command-context-device-initialization`
- File: `patches/dxmt/performance/0001-dxmt-initialize-device-before-command-helpers.patch`
- Component/base: DXMT `7c8dee1c2d73415301ceb7d1fa810861cef4cd67`
- Source/author: Original runtime correction, runtime maintainers
- License: LGPL-2.1-or-later (DXMT)
- Gate: Unconditional; no runtime query
- Inactive behavior: No alternate route; every performance-stage build initializes the device first
- Automated gate: Hash, clean application, and DXMT compilation
- Manual gate: Game startup and rendering with the performance family applied
- Removal: Drop when the pinned DXMT initializes the device first

`ClearUAV` creates pipelines through its outer context during member construction. The original declaration order initialized that device later, so the code read indeterminate storage. Zero could silently leave ten pipelines missing. A value of `1` reproduced the invalid Objective-C receiver and startup exit status 1. Moving the declaration and initializer fixes the lifetime dependency without a hot-path check. This is a correctness fix, not an FPS claim.

### Release present statistics gate

- ID: `dxmt-skip-release-present-statistics`
- File: `patches/dxmt/performance/0002-dxmt-skip-release-present-statistics.patch`
- Component/base: DXMT `7c8dee1c2d73415301ceb7d1fa810861cef4cd67`
- Source/author: Original runtime optimization, runtime maintainers
- License: LGPL-2.1-or-later (DXMT)
- Gate: `DXMT_DEBUG`; debug builds keep statistics aggregation and HUD updates, release builds skip both
- Inactive behavior: Frame counters, measurements, advancement, latency waits, and resets unchanged
- Automated gate: Hash, clean application, both DXMT architectures, release/debug preprocessor contract
- Manual gate: Startup, rendering, and frametime comparison against the clean-removal control (same scene, settings, runtime)
- Removal: Drop when the pinned DXMT removes the release-dead work or gains an equivalent build option

Both `Present` paths keep `UpdateStatistics` behind `DXMT_DEBUG`, which avoids its per-present `std::format` calls in release builds. `PresentBoundary` gates the rolling statistics aggregation the same way. Release builds keep the frame counters and synchronization.

## ACE

All ACE patches use the exact gate `ARKNIGHTS_RUNTIME_ACE_COMPACT=1`. A missing, `0`, or other value keeps Wine's normal route. Every patch requires hash verification and clean application. All four are Endfield FineWine ports ([provenance](../patches/wine/ace/provenance.md)).

- [`wine-ace-ntoskrnl-surface`](../patches/wine/ace/ntoskrnl/0001-ntoskrnl-compatibility-surface.patch)
  - What: Kernel exports and process metadata for the ACE client: current-thread process, image-name, exit-status, audit-parameter, and persistent-thread-state surfaces.
  - Scope: Compatibility-only routes use the ACE gate. `PsGetProcessImageFileName` and `PsGetProcessExitStatus` stay unconditional for valid process objects and follow their kernel `_In_` contract.
  - Checks: compile both architectures; exercise gated and general routes.
- [`wine-ace-dispatcher-spoof`](../patches/wine/ace/dispatcher/0001-kernel32-ace-dispatcher-spoof.patch)
  - What: x86-64 dispatcher lookup compatibility.
  - Scope: ACE gate and Rosetta x86-64 build only.
  - Checks: compile; dispatcher startup.
- [`wine-ace-rosetta-workarounds`](../patches/wine/ace/rosetta/0001-macos-rosetta-ace-workarounds.patch)
  - What: Bounded NOP and ACE privileged-instruction handling under Rosetta.
  - Scope: ACE gate; existing CrossOver CET/XGETBV handling is untouched.
  - Checks: compile; exercise inactive and enabled routes.
- [`wine-ace-relative-wait`](../patches/wine/ace/timing/0001-ntdll-ace-qpc-relative-wait.patch)
  - What: Relative `NtDelayExecution` timing route.
  - Scope: ACE gate and negative relative waits only; other waits are unchanged.
  - Checks: focused wait tests.

## CEF

The CEF family uses the exact gate `ARKNIGHTS_RUNTIME_CEF_COMPAT=1`. An absent, `0`, or invalid value keeps Wine's normal route. If the CEF variable is absent, `ARKNIGHTS_RUNTIME_CN_COMPAT=1` keeps the legacy Bilibili behavior.

- [`wine-cef-bilibili-stackbase`](../patches/wine/cef/0001-ntdll-cef-compatibility.patch)
  - What: Descriptor-driven CEF loader compatibility; proven Bilibili CEF 80.1.15 descriptor.
  - Scope: Explicit CEF gate; legacy CN fallback only when CEF is absent. Before any write, the descriptor requires the `libcef.dll` basename and all three expected RVA byte sequences.
  - Provenance and checks: Original runtime change; see [provenance](../patches/wine/cef/provenance.md), apply check, and x86_64 loader compile.

Add a regional descriptor only with reverse-engineering evidence for its complete hash/RVA/byte contract.

## CN

The CN family contains only the Bilibili windowing patch. It uses the exact gate `ARKNIGHTS_RUNTIME_CN_COMPAT=1`. A missing, `0`, or other value keeps Wine's normal route.

- [`wine-cn-bilibili-layered-child`](../patches/wine/cn/windowing/0001-win32u-winemac-bilibili-layered-child.patch)
  - What: Keeps Chromium's layered proxies for login and payment drawable inside the root Wine window.
  - Scope: CN gate and `PCGamePlatform.exe`. Login keeps the `CMyWebViewDlg` parent-chain route. Payment also requires an exact `Chrome_WidgetWin_0` `WS_CHILD` non-popup with an immediate `CefBrowserWindow` parent, a non-child `GA_ROOT` of class `CPayDlg_P_` plus a nonempty suffix, and matching HWND/parent/root process IDs. Only parent links count. The driver still requires `Chrome.WindowTranslucent` and a layered surface. Each accepted child gets an in-root view with independent color/shape images, source alpha, `SourceConstantAlpha`, root-client geometry, reparent/hide cleanup, and USER hit testing.
  - Provenance and checks: Original runtime change; hash, apply check, offline classifier/contract tests, `win32u`/`winemac` compile, Bilibili payment-window rendering check.

Remove a patch when the pinned WineCX supplies the behavior or the route is no longer needed.
