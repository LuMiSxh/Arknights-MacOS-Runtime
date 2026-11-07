# Collaborator runtime (wine-build-new)

The signed ARM64 runtime is built in a separate MacPorts workspace. That workspace pins
upstream Wine 11.18, FEX 2610, Hadron, and the Endfield ACE baseline. It is being prepared
with the Apple entitlements that this repository cannot get.

This page records the patch export for that workspace. The canonical Arknights patches stay
in this repository. The workspace receives a rebased copy and a Portfile entry.

## Workspace

| Item             | Value                                                              |
| ---------------- | ------------------------------------------------------------------ |
| Workspace        | `wine-build-new`                                                   |
| Wine             | upstream 11.18, commit `7b3fff76fa5178f6ce0141b2c776afa2a822f101`  |
| FEX              | commit `14c92681f4d62cf84d901460e0358de09c8847a7`                  |
| Hadron           | commit `6f401bcfcf4c1cbf7fbd724974fc8d3562262b1c`                  |
| Endfield         | commit `568afd1a32e25e40170eb7484f6790d1e1d370fd`                  |
| Workspace branch | `arknights-arm64`                                                  |
| Submodule branch | `main`                                                             |
| Submodule path   | `third-party/arknights-macos-runtime`                              |
| Patch alias      | `patches/wine/arknights-macos-runtime/` with one symlink per patch |
| Wine export      | `wine-build-new/patches/`                                          |

The workspace applies 72 Wine patches before the Arknights export. The export patches are
rebased against that queue, not against this repository's WineCX 11.17 tree.

The workspace mounts this repository at `third-party/arknights-macos-runtime` and links
each patch file individually into `patches/wine/arknights-macos-runtime/`. The Portfile
references them as `arknights-macos-runtime/0001-...` through `0010-...`.

## Export set

| Export                                             | Source in this repository                     | Runtime gate                  | Need                  |
| -------------------------------------------------- | --------------------------------------------- | ----------------------------- | --------------------- |
| `0001-ntdll-carry-eflags-af-df.patch`              | `patches/arm/wine/ace-context/`               | opt-out `_EFLAGS`             | keep until ACE run    |
| `0002-ntdll-hybrid-thread-entry.patch`             | `patches/arm/wine/ace-thread-entry/`          | opt-out `_HYBRID_THREAD`      | keep until ACE run    |
| `0003-ntoskrnl-arknights-ace-imports.patch`        | `patches/shared/wine/ace/ntoskrnl/` (reduced) | opt-out `_ACE_IMPORTS`        | keep until ACE run    |
| `0004-userenv-appcontainer-apis.patch`             | `patches/shared/wine/appcontainer/`           | opt-out `_APPCONTAINER`       | required for CEF      |
| `0005-ws2_32-address-list-sort.patch`              | `patches/shared/wine/winsock/`                | opt-out `_WINSOCK`            | required for CEF      |
| `0006-ntdll-bilibili-cef80-stack-base.patch`       | `patches/shared/wine/cef/` (rebased)          | opt-out `_CEF`                | required for Bilibili |
| `0007-win32u-winemac-bilibili-layered-child.patch` | `patches/shared/wine/cn/windowing/` (rebased) | master + `_CN`                | required for Bilibili |
| `0008-winemac-bilibili-join-all-spaces.patch`      | `patches/shared/wine/cn/windowing/`           | master + `_CN` (optional)     | required for Bilibili |
| `0009-winemac-native-fullscreen-space.patch`       | `patches/shared/wine/fullscreen/` (rebased)   | opt-out `_FULLSCREEN`         | ours, user-visible    |
| `0010-ntdll-hide-software-cursor-asset.patch`      | `patches/shared/wine/hardware-cursor/`        | master + `_CURSOR` (optional) | ours, user-visible    |

The workspace applies all ten patches at build time. The variables select behavior at
runtime; they do not select patches. `0001` to `0006` and `0009` are on by default and each
has an opt-out. `0007`, `0008`, and `0010` stay opt-in behind `LMISXH_AKMOCL` and a
modifier. `0008` uses the process check that `0007` adds, so the two are always applied
together.

`0003` is reduced. Wine 11.18 already has `PsGetProcessImageFileName`,
`PsReferencePrimaryToken`, `PsGetProcessExitStatus`, `ObRegisterCallbacks`,
`SeLocateProcessImageName`, and the process and thread notify routines. The Endfield queue
adds other ACE imports. The export adds only `PsGetCurrentThreadProcess`,
`PsGetCurrentThreadProcessId`, and `SeSetAuditParameter`.

`0006`, `0007`, and `0008` do not apply to the Wine 11.18 tree unchanged. They were ported
to its loader and winemac code. The behavior is the same.

## Audit

The export was audited against the workspace queue and the pinned upstream trees.

| Question                                      | Result                                                                                                                                                                                                                                              |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FEX lookup-cache eager commit                 | Not needed. `patches/fex/local/0009` adds `LookupCache::CommitL1Window()` and calls it in the constructor, after a cache clear, and when the dynamic L1 window grows. Our patch rewrites the same constructor and does not apply.                   |
| Mono skip                                     | Not needed. The workspace ships no Wine Mono, the entitlement removes the low-4 GB constraint, and `WINEDLLOVERRIDES=mscoree=d` covers a fresh prefix. Arknights does not use .NET.                                                                 |
| ACE imports (`0003`)                          | Kept until an ACE run. Wine 11.18 lacks the exports, but no Arknights ACE import dump was available.                                                                                                                                                |
| Hybrid thread entry (`0002`)                  | Kept until an ACE run. The reference fix is an EA overlay case, not ACE.                                                                                                                                                                            |
| AF/DF context (`0001`)                        | Kept until an ACE run. FEX rebuilds emulated flags, but native ARM64EC context handling still drops them.                                                                                                                                           |
| AppContainer (`0004`)                         | Kept. It replaces a per-game `userenv.dll` shim and covers all clients.                                                                                                                                                                             |
| AsyncDns (`0005`)                             | Kept. It replaces a per-game `--disable-features=AsyncDns` workaround.                                                                                                                                                                              |
| Bilibili CEF and windowing (`0006` to `0008`) | Kept. There is no client-side equivalent for the CEF descriptor or layered surfaces. `0006` is on by default with `_CEF=0` as the opt-out; `0007` and `0008` stay opt-in. `0008` is a six-line Space fix that the old client bridge also performed. |
| Fullscreen (`0009`)                           | Kept. A Windows DLL cannot change the `NSWindow` collection behavior or the fullscreen handshake. It is on by default with `_FULLSCREEN=0` as the opt-out.                                                                                          |
| Hardware cursor (`0010`)                      | Kept. A proxy DLL only covers wrapped APIs. Deleting the assets is undone by Repair.                                                                                                                                                                |

ACE remains unverified. Drop `0001` to `0003` only after an ACE run on the signed runtime
shows they are unnecessary. The China update must complete first.

## Work the workspace already has

Do not send the matching Arknights patches. The Hadron and Endfield queues already provide
the same behavior.

| Work                                                                       | Provided by                                                                               |
| -------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| 4 GB `__PAGEZERO`, top-down allocations, cross-architecture loader         | Hadron wine `0001`, `0008`, `0040`; `local/0003`                                          |
| Executable and writable host-page flips                                    | Hadron wine `0002`, `0006`, `0034`, `0035`, `0036`                                        |
| ARM64 ID registers                                                         | Hadron wine `0020`                                                                        |
| ARM64EC code bitmap, `RtlIsEcCode` bounds                                  | Hadron wine `0011`, `0041`                                                                |
| Per-thread W^X JIT, `MAP_JIT`, unaligned back-patching, EC-code allocation | Hadron FEX `0001` to `0005`                                                               |
| Wow64 registry values                                                      | The `fex-wine` port installs `xtajit.dll` and `xtajit64.dll`                              |
| ACE timing, dispatcher spoof, object callbacks, notify routines            | Endfield `misc/0009` to `0011`, `ace-core/0003` to `0015`, `adapted/0001`, `0012`, `0017` |

The Arknights `address-space`, `wx-pages`, `id-registers`, `ec-code-bitmap`,
`arm64ec-unix-call`, FEX `map-jit`, FEX `code-write-window`, FEX `ec-code-marking`, FEX
`lookup-cache-commit`, and `mono` patches are not part of the export.

- `address-space` and `wx-pages` are workarounds for a runtime without the cross-architecture
  entitlement. The workspace is signed with that entitlement and uses Hadron's W^X model.
- `arm64ec-unix-call` fixes a CodeWeavers WineCX table. The workspace uses upstream Wine.
- Hadron FEX `0005` replaces `map-jit` and `code-write-window`. It allocates JIT buffers with
  `MEM_EXTENDED_PARAMETER_WINE_UNIX_JIT`.
- The same allocation path sets `MEM_EXTENDED_PARAMETER_EC_CODE`. Wine 11.18 marks the code
  bitmap itself, so `ec-code-marking` is unnecessary.
- The workspace FEX `local/0009` replaces `lookup-cache-commit` and is narrower: it commits
  the active L1 window instead of the whole cache.
- Mono remains an optional-component limitation in the workspace. The workspace ships no
  Wine Mono. Set `WINEDLLOVERRIDES=mscoree=d` if a download dialog appears.

## Entitlements

The workspace profile currently grants `com.apple.developer.cross-architecture-support`.
It does not yet grant `com.apple.private.custom-x18-abi`. The collaborator is obtaining the
second entitlement.

The cross-architecture entitlement removes the shared-user-data relocation and the mixed-page
workaround. The custom-x18 entitlement removes the SDK-12 loader relink. Confirm both in the
final profile before judging the window chrome. See [entitlements](entitlements.md).

## Gates and opt-outs

`0001` to `0006` and `0009` are on by default. Each reads one opt-out variable. An unset
variable or `1` keeps the behavior; any other value turns it off.

```sh
LMISXH_AKMOCL_EFLAGS=0          # Do not carry AF and DF
LMISXH_AKMOCL_HYBRID_THREAD=0   # Do not fix up hybrid-module thread entries
LMISXH_AKMOCL_ACE_IMPORTS=0     # Do not export the ACE kernel imports
LMISXH_AKMOCL_APPCONTAINER=0    # Do not implement the AppContainer names
LMISXH_AKMOCL_WINSOCK=0         # Do not implement SIO_ADDRESS_LIST_SORT
LMISXH_AKMOCL_CEF=0             # Do not apply the Bilibili CEF descriptor
LMISXH_AKMOCL_FULLSCREEN=0      # Do not use a native fullscreen Space
```

`0007`, `0008`, and `0010` stay opt-in. They need `LMISXH_AKMOCL=1` and their modifier:

```sh
LMISXH_AKMOCL=1
LMISXH_AKMOCL_CN=1      # Bilibili window behavior (0007 and 0008)
LMISXH_AKMOCL_CURSOR=1  # Hide the software cursor asset (0010)
```

The Global client does not need `_CN`. It does not load the Bilibili CEF build. The Global
CEF build is not covered by `0006`.

## Yaagl

Yaagl has no generic patch-gate layer. It selects a Wine distribution per game and sets
environment variables in each client's `program-launch-game.ts`. It already uses this for
`WINEDLLOVERRIDES`, `WINEMSYNC`, `WINEESYNC`, and `WINE_ENABLE_TIMEOUT_FIX`.

Upstream Yaagl has no Arknights client, so this change adds nothing to Yaagl. A future
Arknights client sets the opt-outs it needs; the CN and cursor patches still need
`LMISXH_AKMOCL` and their modifier.

## Validation

- All 82 Wine patches apply to a pristine Wine 11.18 tree with `patch -p1 -F0`.
- No Wine build, prefix creation, game launch, or ACE run was performed for the export.
- ACE remains untested. Complete the China update before judging an ACE result.

## Updating the export

1. Change the canonical patch in `patches/arm` or `patches/shared`.
2. Rebase it onto the workspace queue in a Wine 11.18 checkout.
3. Run the full queue. Every patch must apply with `-F0`.
4. Replace the file under `wine-build-new/patches/` in this repository.
5. Update the gate or provenance here when the contract changes.
