# Collaborator runtime (wine-build-new)

The signed ARM64 runtime is built in a separate MacPorts workspace. That workspace pins
upstream Wine 11.18, FEX 2610, Hadron, and the Endfield ACE baseline. It is being prepared
with the Apple entitlements that this repository cannot get.

This page records the patch export for that workspace. The canonical Arknights patches stay
in this repository. The workspace receives a rebased copy and a Portfile entry.

## Workspace

| Item          | Value                                                             |
| ------------- | ----------------------------------------------------------------- |
| Workspace     | `wine-build-new`                                                  |
| Wine          | upstream 11.18, commit `7b3fff76fa5178f6ce0141b2c776afa2a822f101` |
| FEX           | commit `14c92681f4d62cf84d901460e0358de09c8847a7`                 |
| Hadron        | commit `6f401bcfcf4c1cbf7fbd724974fc8d3562262b1c`                 |
| Endfield      | commit `568afd1a32e25e40170eb7484f6790d1e1d370fd`                 |
| Export branch | `arknights-arm64`                                                 |
| Submodule path | `patches/wine/arknights-macos-runtime`                           |
| Wine export   | `patches/vendor/wine-build-new/wine/arknights/`                   |
| FEX export    | `patches/vendor/wine-build-new/fex/arknights/`                    |

The workspace applies 72 Wine patches before the Arknights export. The export patches are
rebased against that queue, not against this repository's WineCX 11.17 tree.

The workspace mounts this repository at `patches/wine/arknights-macos-runtime`. Its Portfiles
reference the export as `arknights-macos-runtime/patches/vendor/wine-build-new/...`. The FEX
port reaches the same checkout through a relative symlink at `patches/fex/arknights-macos-runtime`.

## Export set

| Export                                             | Source in this repository                     | Gate                             |
| -------------------------------------------------- | --------------------------------------------- | -------------------------------- |
| `0001-mscoree-skip-mono-on-native-arm64.patch`     | `patches/arm/wine/mono/`                      | master + `_MONO`   |
| `0002-ntdll-carry-eflags-af-df.patch`              | `patches/arm/wine/ace-context/`               | none (general)     |
| `0003-ntdll-hybrid-thread-entry.patch`             | `patches/arm/wine/ace-thread-entry/`          | none (general)     |
| `0004-ntoskrnl-arknights-ace-imports.patch`        | `patches/shared/wine/ace/ntoskrnl/` (reduced) | none (general)     |
| `0005-userenv-appcontainer-apis.patch`             | `patches/shared/wine/appcontainer/`           | none (general)     |
| `0006-ws2_32-address-list-sort.patch`              | `patches/shared/wine/winsock/`                | none (general)     |
| `0007-ntdll-bilibili-cef80-stack-base.patch`       | `patches/shared/wine/cef/` (rebased)          | master + `_CEF`    |
| `0008-win32u-winemac-bilibili-layered-child.patch` | `patches/shared/wine/cn/windowing/` (rebased) | master + `_CN`     |
| `0009-winemac-bilibili-join-all-spaces.patch`      | `patches/shared/wine/cn/windowing/`           | master + `_CN`     |
| FEX `0001-lookup-cache-commit-eagerly.patch`       | `patches/arm/fex/lookup-cache-commit/`        | none (general)     |

`0004` is reduced. The workspace already has `PsGetProcessImageFileName`,
`PsReferencePrimaryToken`, `PsGetProcessExitStatus`, `ObRegisterCallbacks`,
`SeLocateProcessImageName`, and the process and thread notify routines. The export adds only
`PsGetCurrentThreadProcess`, `PsGetCurrentThreadProcessId`, and `SeSetAuditParameter`.

`0007`, `0008`, and `0009` do not apply to the Wine 11.18 tree unchanged. They were ported
to its loader and winemac code. The behavior is the same.

## Work the workspace already has

Do not send the matching Arknights patches. The Hadron and Endfield queues already provide
the same behavior.

| Work                                                                       | Provided by                                                                               |
| -------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| 4 GB `__PAGEZERO`, top-down allocations, cross-architecture loader         | Hadron wine `0001`, `0003`, `0005`, `0008`, `0040`                                        |
| Executable and writable host-page flips                                    | Hadron wine `0002`, `0006`, `0034`, `0035`, `0036`                                        |
| ARM64 ID registers                                                         | Hadron wine `0020`                                                                        |
| ARM64EC code bitmap, `RtlIsEcCode` bounds                                  | Hadron wine `0011`, `0041`                                                                |
| Per-thread W^X JIT, `MAP_JIT`, unaligned back-patching, EC-code allocation | Hadron FEX `0001` to `0005`                                                               |
| Wow64 registry values                                                      | The `fex-wine` port installs `xtajit.dll` and `xtajit64.dll`                              |
| ACE timing, dispatcher spoof, object callbacks, notify routines            | Endfield `misc/0009` to `0011`, `ace-core/0003` to `0015`, `adapted/0001`, `0012`, `0017` |

The Arknights `address-space`, `wx-pages`, `id-registers`, `ec-code-bitmap`,
`arm64ec-unix-call`, FEX `map-jit`, FEX `code-write-window`, and FEX `ec-code-marking`
patches are not part of the export.

- `address-space` and `wx-pages` are workarounds for a runtime without the cross-architecture
  entitlement. The workspace is signed with that entitlement and uses Hadron's W^X model.
- `arm64ec-unix-call` fixes a CodeWeavers WineCX table. The workspace uses upstream Wine.
- Hadron FEX `0005` replaces `map-jit` and `code-write-window`. It allocates JIT buffers with
  `MEM_EXTENDED_PARAMETER_WINE_UNIX_JIT`.
- The same allocation path sets `MEM_EXTENDED_PARAMETER_EC_CODE`. Wine 11.18 marks the code
  bitmap itself, so `ec-code-marking` is unnecessary.

## Entitlements

The workspace profile currently grants `com.apple.developer.cross-architecture-support`.
It does not yet grant `com.apple.private.custom-x18-abi`. The collaborator is obtaining the
second entitlement.

The cross-architecture entitlement removes the shared-user-data relocation and the mixed-page
workaround. The custom-x18 entitlement removes the SDK-12 loader relink. Confirm both in the
final profile before judging the window chrome. See [entitlements](entitlements.md).

## Gates

`LMISXH_AKMOCL=1` is the master switch for the Arknights-specific patches. Each modifier
opts one behavior in. An absent or invalid modifier leaves that behavior off.

```sh
LMISXH_AKMOCL=1
LMISXH_AKMOCL_MONO=1      # Skip Wine Mono
LMISXH_AKMOCL_CEF=1       # Bilibili CEF 80.1.15 descriptor
LMISXH_AKMOCL_CN=1        # CN window behavior
```

The general patches do not read `LMISXH_AKMOCL`. They are safe for any user of the runtime:
AppContainer, Winsock, AF/DF context, hybrid thread entry, the three kernel imports, and the
FEX lookup-cache commit. ACE is therefore not separately gated.

The Global client does not need `_CEF` or `_CN`. It does not load the Bilibili CEF build.
The Global CEF build is not covered by `0007`.

## Yaagl

Yaagl has no generic patch-gate layer. It selects a Wine distribution per game and sets
environment variables in each client's `program-launch-game.ts`. It already uses this for
`WINEDLLOVERRIDES`, `WINEMSYNC`, `WINEESYNC`, and `WINE_ENABLE_TIMEOUT_FIX`.

Upstream Yaagl has no Arknights client. An Arknights client must set the master switch and the
modifiers it needs. General patches must not depend on that client.

## Validation

- All 81 Wine patches apply to a pristine Wine 11.18 tree with `patch -p1 -F0`.
- The resulting tree is byte-identical to the branch the export was generated from.
- The FEX patch applies after Hadron FEX `0001` to `0005`.
- No Wine build, prefix creation, game launch, or ACE run was performed for the export.
- ACE remains untested. Complete the China update before judging an ACE result.

## Updating the export

1. Change the canonical patch in `patches/arm` or `patches/shared`.
2. Rebase it onto the workspace queue in a Wine 11.18 checkout.
3. Run the full queue. Every patch must apply with `-F0`.
4. Replace the file under `patches/vendor/wine-build-new/` in this repository.
5. Update the gate or provenance here when the contract changes.
