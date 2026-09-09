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
| Component/base    | WineCX `7dbc5b5322a6ef3fb04bdc643c64b188fd641149` (Wine 11.16)                        |
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
| Component/base    | DXMT `19e24ee068a44a747e556965730482038c5bb068` (`v0.80-199-g19e24ee`)                |
| Source/author     | Original Arknights macOS Runtime experiment, Arknights macOS Runtime maintainers      |
| License           | LGPL-2.1-or-later, matching the pinned DXMT revision                                  |
| Gate              | `ARKNIGHTS_RUNTIME_DXMT_MAX_FRAME_LATENCY=1..3`, read once on first command queue     |
| Inactive behavior | Missing or invalid input retains upstream maximum `3`                                 |
| Automated gate    | Hash, clean `git apply --check`, and both DXMT architectures compile                  |
| Manual gate       | Controlled FPS/frame-pacing/cursor comparison at values 3, 2, and 1                   |
| Removal           | Drop if DXMT gains an equivalent supported control or evidence rejects the experiment |

## CN

All CN patches use the one exact gate `ARKNIGHTS_RUNTIME_CN_COMPAT=1`; missing, `0`, or any other value keeps
Wine's normal route. They target WineCX `7dbc5b5322a6ef3fb04bdc643c64b188fd641149` and retain Wine's
LGPL-2.1-or-later. Hash verification and clean application are required for every row.

| Patch                                                                                                          | What and why                                                                         | Scope / preflight                                                                                                                                                                                                                                                                                                     | Provenance and verification                                                                                                    |
| -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| [`wine-cn-ntoskrnl-surface`](../patches/wine/cn/ntoskrnl/0001-ntoskrnl-compatibility-surface.patch)            | Kernel exports and process metadata required by the CN client.                       | CN gate; existing stub behavior otherwise.                                                                                                                                                                                                                                                                            | Endfield FineWine port; see [provenance](../patches/wine/cn/provenance.md). Compile and exercise inactive/enabled routes.      |
| [`wine-cn-dispatcher-spoof`](../patches/wine/cn/dispatcher/0001-kernel32-cn-dispatcher-spoof.patch)            | x86-64 dispatcher lookup compatibility.                                              | CN gate and Rosetta x86-64 build only.                                                                                                                                                                                                                                                                                | Endfield FineWine port; compile and dispatcher startup check.                                                                  |
| [`wine-cn-rosetta-workarounds`](../patches/wine/cn/rosetta/0001-macos-rosetta-cn-workarounds.patch)            | Bounded NOP and privileged-instruction handling under Rosetta.                       | CN gate; existing CrossOver CET/XGETBV handling is untouched.                                                                                                                                                                                                                                                         | Endfield FineWine port; compile and inactive/enabled startup check.                                                            |
| [`wine-cn-relative-wait`](../patches/wine/cn/timing/0001-ntdll-cn-qpc-relative-wait.patch)                     | Relative `NtDelayExecution` timing route.                                            | CN gate and negative relative waits only; absolute, zero, and alertable waits are unchanged.                                                                                                                                                                                                                          | Endfield FineWine port; focused wait tests.                                                                                    |
| [`wine-cn-bilibili-cef80-stackbase`](../patches/wine/cn/cef/0001-ntdll-bilibili-cef-80-stackbase.patch)        | CEF 80.1.15 reads Windows `StackBase` directly on macOS.                             | CN gate; runtime preflight is `libcef.dll` basename plus all three expected RVA byte sequences before any write. SHA-256 `183c8db291fc41227b4a2fb91ca982a4e78e46c743874436f4f84d6ab09c3043` identifies the proven binary; it is not rehashed at runtime. | Original runtime change; apply check, x86_64 loader compile, and multi-process Bilibili login.                                 |
| [`wine-bilibili-layered-child`](../patches/wine/cn/windowing/0001-win32u-winemac-bilibili-layered-child.patch) | Keeps Chromium's browser-process layered proxy drawable inside the root Wine window. | CN gate; `PCGamePlatform.exe`, `CMyWebViewDlg` root, `Chrome_WidgetWin_0`, and `Chrome.WindowTranslucent` property. Each matching layered descendant has an in-root view with independent color/shape images, source alpha, `SourceConstantAlpha`, root-client geometry, reparent/hide cleanup, and USER hit testing. | Original runtime change; apply check, focused `win32u`/`winemac` compile, Bilibili captcha, and translucent error-toast check. |

The first four ports derive from `stoicswe/Endfield_FineWine` commit
`e5d4ccad235eefe32d912733e57e4c0bb53a5b58`; exact authorship and history are in
[`patches/wine/cn/provenance.md`](../patches/wine/cn/provenance.md). Remove a patch when the pinned WineCX
source supplies the equivalent behavior or the compatibility route is no longer needed.
