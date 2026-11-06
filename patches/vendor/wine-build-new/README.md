# wine-build-new export

This directory is the Arknights patch export for the signed ARM64 runtime built in
`wine-build-new`. That workspace consumes this repository as a submodule at
`third-party/arknights-runtime`.

The workspace builds upstream Wine 11.18 with a 72-patch Hadron and Endfield queue. The
patches here are rebased against that queue, not against this repository's WineCX 11.17 tree.
See [collaborator runtime](../../../docs/arm/wine-build-new.md) for the mapping and the
skip list.

## Layout

| Path | Content |
| ---- | ------- |
| `wine/arknights/` | Nine Wine patches, applied after the 72-patch queue |
| `fex/arknights/` | One FEX patch, applied after Hadron FEX `0001` to `0005` |
| `yaagl-lock.json` | Machine-readable list of paths, hashes, and gates |

## Gates

`LMISXH_AKMOCL=1` is the master switch for the Arknights-specific patches. Each modifier
opts one behavior in. An absent or invalid modifier leaves that behavior off.

```sh
LMISXH_AKMOCL=1
LMISXH_AKMOCL_MONO=1      # Skip Wine Mono
LMISXH_AKMOCL_CEF=1       # Bilibili CEF 80.1.15 descriptor
LMISXH_AKMOCL_CN=1        # CN window behavior
```

The general patches have no gate: AF/DF context, hybrid thread entry, the three kernel
imports, AppContainer, Winsock, and the FEX lookup-cache commit. ACE is therefore not
separately gated.

## Workspace integration

The workspace adds this repository at `third-party/arknights-runtime`. Its Portfiles set
`filespath` to the workspace root and list the patches as:

```text
third-party/arknights-runtime/patches/vendor/wine-build-new/wine/arknights/0001-... \
```

The FEX port uses the matching `fex/arknights/` path. Do not copy these files into the
workspace. Keep one source of truth here.

## Validation

- All nine Wine patches apply with `patch -p1 -F0` after the workspace's 72-patch queue.
- The FEX patch applies after Hadron FEX `0001` to `0005`.
- No Wine build, prefix, game launch, or ACE run was performed for this export.
- ACE remains unverified. Complete the China update before judging an ACE result.
