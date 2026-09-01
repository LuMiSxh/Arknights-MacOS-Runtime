# Patch registry

The ordered registry is machine-readable in `runtime.lock.json`. Every entry below must name its
upstream source, author, license, gate, inactive behavior, test, and removal condition before release.

## Audio

| Field | Value |
| --- | --- |
| ID | `wine-audio-default-output` |
| File | `patches/wine/audio/0001-winecoreaudio-default-output.patch` |
| Component/base | WineCX `7dbc5b5322a6ef3fb04bdc643c64b188fd641149` (Wine 11.16) |
| Source/author | Wine draft MR 11370, commits `4d143f4c` and `65140f31`, Rhodri Richards |
| License | LGPL-2.1-or-later |
| Gate | `ARKNIGHTS_RUNTIME_AUDIO_FOLLOW_DEFAULT_OUTPUT=1`, parsed once per process |
| Inactive behavior | Normal Wine endpoint enumeration and routing |
| Automated gate | Hash and clean `git apply --check`; patched Wine compile |
| Manual gate | Active shared render stream follows default device across switch/disconnect/reconnect |
| Removal | Drop after equivalent accepted Wine behavior reaches the pinned WineCX source |

The carried MR is a draft. Capture and exclusive streams are deliberately unchanged.

## Cursor

| Field | Value |
| --- | --- |
| ID | `dxmt-cursor-frame-latency` |
| File | `patches/dxmt/cursor/0001-dxmt-command-queue-configurable-frame-latency.patch` |
| Component/base | DXMT `19e24ee068a44a747e556965730482038c5bb068` (`v0.80-199-g19e24ee`) |
| Source/author | Original Arknights MacOS Runtime experiment, Arknights MacOS Runtime maintainers |
| License | LGPL-2.1-or-later, matching the pinned DXMT revision |
| Gate | `ARKNIGHTS_RUNTIME_DXMT_MAX_FRAME_LATENCY=1..3`, read once on first command queue |
| Inactive behavior | Missing or invalid input retains upstream maximum `3` |
| Automated gate | Hash, clean `git apply --check`, and both DXMT architectures compile |
| Manual gate | Controlled FPS/frame-pacing/cursor comparison at values 3, 2, and 1 |
| Removal | Drop if DXMT gains an equivalent supported control or evidence rejects the experiment |

## CN

| ID | File | Scope |
| --- | --- | --- |
| `wine-cn-ntoskrnl-surface` | `patches/wine/cn/ntoskrnl/0001-ntoskrnl-compatibility-surface.patch` | Selected kernel exports and process metadata |
| `wine-cn-dispatcher-spoof` | `patches/wine/cn/dispatcher/0001-kernel32-cn-dispatcher-spoof.patch` | x86-64 dispatcher lookup workaround |
| `wine-cn-rosetta-workarounds` | `patches/wine/cn/rosetta/0001-macos-rosetta-cn-workarounds.patch` | Bounded NOP and privileged-instruction handling |
| `wine-cn-relative-wait` | `patches/wine/cn/timing/0001-ntdll-cn-qpc-relative-wait.patch` | Negative relative-wait experiment |

All target WineCX `7dbc5b5322a6ef3fb04bdc643c64b188fd641149`, retain Wine's
LGPL-2.1-or-later, and derive from `stoicswe/Endfield_FineWine` commit
`e5d4ccad235eefe32d912733e57e4c0bb53a5b58`. Exact authorship and upstream history are recorded in
`patches/wine/cn/provenance.md`.

Behavior-changing routes require the exact, once-per-process gate `ARKNIGHTS_RUNTIME_CN_COMPAT=1`; other values
select Wine's normal route. Export presence is necessarily compile-time-visible even while inactive,
so Global/JP/KR canaries remain mandatory. Removal occurs when accepted Wine/WineCX behavior replaces
the port, or when a real CN failure path shows a patch is unnecessary. This family is compiled,
inactive, and unvalidated—not CN support.
