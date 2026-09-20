# Patch registry

The ordered registry is machine-readable in [`runtime.lock.json`](../runtime.lock.json). Every entry
below must name its upstream source, author, license, gate, inactive behavior, test, and removal
condition before release. The entries document patch provenance; they do not replace the complete
corresponding-source, notice, and redistribution review required for a runtime binary.

## Audio

| Field             | Value                                                                                 |
| ----------------- | ------------------------------------------------------------------------------------- |
| ID                | `wine-audio-default-output`                                                           |
| File              | `patches/wine/audio/0001-winecoreaudio-default-output.patch`                          |
| Component/base    | WineCX `e1b410a5fdd96a32722a5f2617b5068bd385b7db` (Wine 11.16)                        |
| Source/author     | Wine draft MR 11370, commits `4d143f4c` and `65140f31`, Rhodri Richards               |
| License           | LGPL-2.1-or-later                                                                     |
| Gate              | `ARKNIGHTS_RUNTIME_AUDIO_FOLLOW_DEFAULT_OUTPUT=1`, parsed once per process            |
| Inactive behavior | Normal Wine endpoint enumeration and routing                                          |
| Automated gate    | Hash and clean `git apply --check`; patched Wine compile                              |
| Manual gate       | Active shared render stream follows default device across switch/disconnect/reconnect |
| Removal           | Drop after equivalent accepted Wine behavior reaches the pinned WineCX source         |

The carried MR is a draft. Capture and exclusive streams are deliberately unchanged.

## Cursor

| Field             | Value                                                                                 |
| ----------------- | ------------------------------------------------------------------------------------- |
| ID                | `dxmt-cursor-frame-latency`                                                           |
| File              | `patches/dxmt/cursor/0001-dxmt-command-queue-configurable-frame-latency.patch`        |
| Component/base    | DXMT `4ddb20e54672c0cb56115ce80d6db1beef94ae28` (`v0.80-213-g4ddb20e`)                |
| Source/author     | Original Arknights macOS Runtime experiment, Arknights macOS Runtime maintainers      |
| License           | LGPL-2.1-or-later, matching the pinned DXMT revision                                  |
| Gate              | `ARKNIGHTS_RUNTIME_DXMT_MAX_FRAME_LATENCY=1..3`, read once on first command queue     |
| Inactive behavior | Missing or invalid input retains upstream maximum `3`                                 |
| Automated gate    | Hash, clean `git apply --check`, and both DXMT architectures compile                  |
| Manual gate       | Controlled FPS/frame-pacing/cursor comparison at values 3, 2, and 1                   |
| Removal           | Drop if DXMT gains an equivalent supported control or evidence rejects the experiment |

## Performance

| Field             | Value                                                                                                     |
| ----------------- | --------------------------------------------------------------------------------------------------------- |
| ID                | `dxmt-command-context-device-initialization`                                                              |
| File              | `patches/dxmt/performance/0001-dxmt-initialize-device-before-command-helpers.patch`                       |
| Component/base    | DXMT `4ddb20e54672c0cb56115ce80d6db1beef94ae28`                                                           |
| Source/author     | Original Arknights macOS Runtime correction, Arknights macOS Runtime maintainers                          |
| License           | LGPL-2.1-or-later, matching the pinned DXMT revision                                                      |
| Gate              | Unconditional initialization-correctness prerequisite in the performance build; no runtime query          |
| Inactive behavior | No alternate route; the device is initialized before helper construction in every performance-stage build |
| Automated gate    | Hash, clean application, and DXMT compilation                                                             |
| Manual gate       | Game startup and rendering with the performance family applied                                            |
| Removal           | Drop when the pinned upstream revision initializes the device before its consumers                        |

`ClearUAV` creates pipelines through its outer context during member construction. The original
declaration order initialized that context's device later, reading indeterminate storage. Zero
could silently leave ten missing pipelines; a value of `1` reproduced the invalid Objective-C
receiver and startup exit status 1. Moving the declaration and initializer fixes this lifetime
dependency without a hot-path check. This is a correctness fix, not an FPS claim.

### Release present statistics gate

| Field             | Value                                                                                                                                                   |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ID                | `dxmt-skip-release-present-statistics`                                                                                                                    |
| File              | `patches/dxmt/performance/0002-dxmt-skip-release-present-statistics.patch`                                                                               |
| Component/base    | DXMT `4ddb20e54672c0cb56115ce80d6db1beef94ae28`                                                                                                         |
| Source/author     | Original Arknights macOS Runtime optimization, Arknights macOS Runtime maintainers                                                                      |
| License           | LGPL-2.1-or-later, matching DXMT                                                                                                                         |
| Gate              | `DXMT_DEBUG`; debug builds retain present statistics aggregation and HUD updates, release builds skip both release-dead paths                           |
| Inactive behavior | Per-frame counters, measurements, frame advancement, latency waits, and frame resets remain unchanged                                                   |
| Automated gate    | Hash, clean application, both DXMT architectures, and release/debug preprocessor contract                                                               |
| Manual gate       | Controlled startup/rendering and frametime comparison with the same scene, settings, and runtime as the clean-removal control                           |
| Removal           | Drop when the pinned DXMT revision removes the release-dead statistics work or provides an equivalent supported build configuration                      |

Both `Present` paths keep `UpdateStatistics` behind `DXMT_DEBUG`, which also avoids its per-present
`std::format` calls in release builds. `PresentBoundary` keeps the rolling statistics aggregation on
the same gate. Debug builds preserve the existing HUD output and aggregation; release builds retain
the underlying frame counters and synchronization behavior.

## ACE

All ACE patches use the one exact gate `ARKNIGHTS_RUNTIME_ACE_COMPACT=1`; missing, `0`, or any other value
keeps Wine's normal route. They target WineCX `e1b410a5fdd96a32722a5f2617b5068bd385b7db` and retain Wine's
LGPL-2.1-or-later. Hash verification and clean application are required for every row.

| Patch                                                                                                  | What and why                                                       | Scope / preflight                                                     | Provenance and verification                                                                                    |
| ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------ | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| [`wine-ace-ntoskrnl-surface`](../patches/wine/ace/ntoskrnl/0001-ntoskrnl-compatibility-surface.patch)  | Kernel exports and process metadata required by the ACE client, including the persistent-thread-state capture stub. | ACE gate; existing stub behavior otherwise.                           | Endfield FineWine port; see [provenance](../patches/wine/ace/provenance.md). Compile and exercise both routes. |
| [`wine-ace-dispatcher-spoof`](../patches/wine/ace/dispatcher/0001-kernel32-ace-dispatcher-spoof.patch) | x86-64 dispatcher lookup compatibility.                            | ACE gate and Rosetta x86-64 build only.                               | Endfield FineWine port; compile and dispatcher startup check.                                                  |
| [`wine-ace-rosetta-workarounds`](../patches/wine/ace/rosetta/0001-macos-rosetta-ace-workarounds.patch) | Bounded NOP and ACE privileged-instruction handling under Rosetta. | ACE gate; existing CrossOver CET/XGETBV handling is untouched.        | Endfield FineWine port; compile and exercise inactive/enabled routes.                                          |
| [`wine-ace-relative-wait`](../patches/wine/ace/timing/0001-ntdll-ace-qpc-relative-wait.patch)          | Relative `NtDelayExecution` timing route.                          | ACE gate and negative relative waits only; other waits are unchanged. | Endfield FineWine port; focused wait tests.                                                                    |

## CN

The Bilibili patches use the one exact gate `ARKNIGHTS_RUNTIME_CN_COMPAT=1`; missing, `0`, or any other
value keeps Wine's normal route. They target WineCX `e1b410a5fdd96a32722a5f2617b5068bd385b7db` and retain
Wine's LGPL-2.1-or-later.

| Patch                                                                                                             | What and why                                                                         | Scope / preflight                                                                                                                                                                                                                                                                                                     | Provenance and verification                                                                                                    |
| ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| [`wine-cn-bilibili-cef80-stackbase`](../patches/wine/cn/cef/0001-ntdll-bilibili-cef-80-stackbase.patch)           | CEF 80.1.15 reads Windows `StackBase` directly on macOS.                             | CN gate; runtime preflight is `libcef.dll` basename plus all three expected RVA byte sequences before any write. SHA-256 `183c8db291fc41227b4a2fb91ca982a4e78e46c743874436f4f84d6ab09c3043` identifies the proven binary; it is not rehashed at runtime.                                                              | Original runtime change; apply check, x86_64 loader compile, and multi-process Bilibili login.                                 |
| [`wine-cn-bilibili-layered-child`](../patches/wine/cn/windowing/0001-win32u-winemac-bilibili-layered-child.patch) | Keeps Chromium's browser-process layered proxy drawable inside the root Wine window. | CN gate; `PCGamePlatform.exe`, `CMyWebViewDlg` root, `Chrome_WidgetWin_0`, and `Chrome.WindowTranslucent` property. Each matching layered descendant has an in-root view with independent color/shape images, source alpha, `SourceConstantAlpha`, root-client geometry, reparent/hide cleanup, and USER hit testing. | Original runtime change; apply check, focused `win32u`/`winemac` compile, Bilibili captcha, and translucent error-toast check. |

Remove a patch when the pinned WineCX source supplies the equivalent behavior or the corresponding
compatibility route is no longer needed.
