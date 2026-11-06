# wine-build-new export

This directory is the Arknights patch export for the signed ARM64 runtime built in
`wine-build-new`. That workspace consumes this repository as a submodule at
`patches/wine/arknights-macos-runtime`.

The workspace builds upstream Wine 11.18 with a 72-patch Hadron and Endfield queue. The
patches here are rebased against that queue, not against this repository's WineCX 11.17 tree.
The submodule lives at `third-party/arknights-macos-runtime`; the workspace exposes it at
`patches/wine/arknights-macos-runtime` so the Portfile paths stay short.
See [collaborator runtime](../../docs/arm/wine-build-new.md) for the mapping and the skip list.

## Layout

| Path | Content |
| ---- | ------- |
| `wine/` | Ten Wine patches, applied after the 72-patch queue |
| `lock.json` | Machine-readable list of paths, hashes, and gates |

## What is in the export

| Patch | Gate | Purpose |
| ----- | ---- | ------- |
| `0001-ntdll-carry-eflags-af-df.patch` | none | Keeps AF and DF across ARM64EC context switches. |
| `0002-ntdll-hybrid-thread-entry.patch` | none | Starts a hybrid-module thread on its x64 export. |
| `0003-ntoskrnl-arknights-ace-imports.patch` | none | Adds three kernel imports that ACE resolves. |
| `0004-userenv-appcontainer-apis.patch` | none | Adds the AppContainer names Chromium resolves. |
| `0005-ws2_32-address-list-sort.patch` | none | Implements `SIO_ADDRESS_LIST_SORT` for AsyncDns. |
| `0006-ntdll-bilibili-cef80-stack-base.patch` | master + `_CEF` | Bilibili CEF 80.1.15 stack-base descriptors. |
| `0007-win32u-winemac-bilibili-layered-child.patch` | master + `_CN` | Bilibili layered child window. |
| `0008-winemac-bilibili-join-all-spaces.patch` | master + `_CN` (optional) | Bilibili payment window on every Space. |
| `0009-winemac-native-fullscreen-space.patch` | master + `_FULLSCREEN` (optional) | Puts fullscreen games in a native macOS Space. |
| `0010-ntdll-hide-software-cursor-asset.patch` | master + `_CURSOR` (optional) | Hides the two game software-cursor assets. |

## What is not in the export

- **FEX lookup-cache eager commit.** This repository needs it on FEX 4efc3abc and WineCX
  11.17. The workspace uses FEX 2610 and Wine 11.18. Its recorded x64/i386 FEX probes pass
  with the reserved lookup cache, so the fault path works there.
- **Mono skip.** Mono remains an optional-component limitation in the workspace.
  Arknights does not use .NET. A launcher can set `WINEDLLOVERRIDES=mscoree=d` without a
  runtime patch. This repository keeps the patch for its entitlement-free local lane.
- **Address space, W^X, ID registers, EC bitmap, and FEX JIT patches.** The Hadron queue
  already provides them.
- **Loader name, audio, and DXMT.** Not required for login or ACE. The DXMT patch also
  targets a different DXMT pin. Fullscreen and hardware cursor are optional; they are in
  the export because the client uses them.

## Gates

`LMISXH_AKMOCL=1` is the master switch for the CN patches. Each modifier opts one behavior
in. An absent or invalid modifier leaves that behavior off.

```sh
LMISXH_AKMOCL=1
LMISXH_AKMOCL_CEF=1       # Bilibili CEF 80.1.15 descriptor
LMISXH_AKMOCL_CN=1        # CN window behavior
LMISXH_AKMOCL_FULLSCREEN=1  # Native fullscreen Space
LMISXH_AKMOCL_CURSOR=1      # Hide the software cursor asset
```

The general patches do not read `LMISXH_AKMOCL`. ACE is not separately gated.

## Workspace integration

The workspace adds this repository at `third-party/arknights-macos-runtime`. A relative
symlink at `patches/wine/arknights-macos-runtime` lets the Portfile keep `filespath` at
`patches/wine` and list the patches as:

```text
arknights-macos-runtime/patches/wine-build-new/wine/0001-... \
```

The FEX port no longer needs an entry.

## Validation

- All ten Wine patches apply with `patch -p1 -F0` after the workspace's 72-patch queue.
- No Wine build, prefix, game launch, or ACE run was performed for this export.
- ACE remains unverified. Complete the China update before judging an ACE result.
