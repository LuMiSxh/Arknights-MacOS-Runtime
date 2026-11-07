# wine-build-new export

This directory is the Arknights patch export for the signed ARM64 runtime built in
`wine-build-new`. That workspace consumes this repository as a submodule at
`third-party/arknights-macos-runtime`.

The workspace builds upstream Wine 11.18 with a 72-patch Hadron and Endfield queue. The
patches here are rebased against that queue, not against this repository's WineCX 11.17
tree. The workspace exposes only `wine-build-new/patches/` at
`patches/wine/arknights-macos-runtime`, so its patches folder contains only patch files.
See [collaborator runtime](../docs/arm/wine-build-new.md) for the mapping and the audit.

## Layout

| Path        | Content                                                   |
| ----------- | --------------------------------------------------------- |
| `patches/`  | Ten Wine patches, applied after the 72-patch queue        |
| `lock.json` | Machine-readable list of paths, hashes, and runtime gates |

## What is in the export

The workspace applies all ten patches at build time. The `LMISXH_AKMOCL_*` variables gate
behavior at runtime; they do not select patches at build time.

| Patch                                              | Runtime gate             | Need                  | Purpose                                                  |
| -------------------------------------------------- | ------------------------ | --------------------- | -------------------------------------------------------- |
| `0001-ntdll-carry-eflags-af-df.patch`              | opt-out `_EFLAGS`        | keep until ACE run    | Keeps AF and DF across ARM64EC context switches.         |
| `0002-ntdll-hybrid-thread-entry.patch`             | opt-out `_HYBRID_THREAD` | keep until ACE run    | Starts a hybrid-module thread on its x64 export.         |
| `0003-ntoskrnl-arknights-ace-imports.patch`        | opt-out `_ACE_IMPORTS`   | keep until ACE run    | Adds three kernel imports that ACE resolves.             |
| `0004-userenv-appcontainer-apis.patch`             | opt-out `_APPCONTAINER`  | required for CEF      | Adds the AppContainer names Chromium resolves.           |
| `0005-ws2_32-address-list-sort.patch`              | opt-out `_WINSOCK`       | required for CEF      | Implements `SIO_ADDRESS_LIST_SORT` for AsyncDns.         |
| `0006-ntdll-bilibili-cef80-stack-base.patch`       | opt-out `_CEF`           | required for Bilibili | Bilibili CEF 80.1.15 stack-base descriptors.             |
| `0007-win32u-winemac-bilibili-layered-child.patch` | master + `_CN`           | required for Bilibili | Bilibili layered child window.                           |
| `0008-winemac-bilibili-join-all-spaces.patch`      | master + `_CN`           | required for Bilibili | Bilibili payment window on every Space. Requires `0007`. |
| `0009-winemac-native-fullscreen-space.patch`       | opt-out `_FULLSCREEN`    | ours, user-visible    | Puts fullscreen games in a native macOS Space.           |
| `0010-ntdll-hide-software-cursor-asset.patch`      | master + `_CURSOR`       | ours, user-visible    | Hides the two game software-cursor assets.               |

`0001` to `0006` and `0009` are on by default. Each reads one opt-out variable: unset or
`1` keeps the behavior, and any other value turns it off. `0007`, `0008`, and `0010` stay
opt-in behind `LMISXH_AKMOCL` and their modifier.

### Why the ACE patches stay

`0001`, `0002`, and `0003` are small and general. Keep them until an ACE run on the signed
runtime proves they are unnecessary. Drop criteria:

- `0003`: an ACE log shows no `unimplemented function ntoskrnl.exe.PsGetCurrentThreadProcess`,
  `PsGetCurrentThreadProcessId`, or `SeSetAuditParameter`.
- `0002`: ACE initializes without a hybrid-thread entry fault.
- `0001`: ACE initializes without a context-flag failure.

Wine 11.18 does not contain the three `0003` exports. The Endfield queue adds other ACE
imports but not these three. No ACE import dump was available for this audit.

### Why `0004` and `0005` stay

The launcher can avoid both with a `userenv.dll` shim and `--disable-features=AsyncDns`.
The runtime patches keep one implementation for every client and remove the per-game
shim. Both are general Chromium correctness fixes.

### Why `0009` and `0010` stay

The workspace queue has no equivalent. Fullscreen needs winemac because a Windows DLL
cannot reach the `NSWindow` that owns the Space and the fullscreen handshake. The cursor
filter could be approximated by a proxy DLL, but that only covers wrapped APIs and is
less durable than the shared NT name resolver. `0009` is on by default with an opt-out;
`0010` stays opt-in.

## What is not in the export

- **FEX lookup-cache eager commit.** The workspace patch
  `patches/fex/local/0009-FEX-Optimize-Hadron-JIT-memory-and-invalidation.patch` already
  calls `LookupCache::CommitL1Window()` in the constructor, after a cache clear, and when
  the dynamic L1 window grows. Our standalone patch rewrites the same constructor, does
  not apply, and would re-commit the whole cache.
- **Mono skip.** The workspace ships no Wine Mono. The cross-architecture entitlement
  removes the low-4 GB constraint that the patch worked around. Arknights is Unity-based
  and does not use Wine Mono. Set `WINEDLLOVERRIDES=mscoree=d` at prefix creation if a
  Mono download dialog appears.
- **Address space, W^X, ID registers, EC bitmap, and FEX JIT patches.** The Hadron queue
  already provides them.
- **Loader name, audio, and DXMT.** Not required for login or ACE. The DXMT patch also
  targets a different DXMT pin.

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

`0008` uses the process check that `0007` adds, so the two are always applied together.
ACE is not separately gated.

## Known limitations

- `0006` patches Bilibili `libcef.dll` in memory after a byte preflight. It does not
  verify the image hash and is not atomic if a later page protection change fails. Set
  `LMISXH_AKMOCL_CEF=0` to disable it.
- `0007` adds a property and class lookup to every layered window update before the gate
  check. The behavior is opt-in, but the code is compiled in for every user.
- `0009` selects windows by shape, not by application name. Set
  `LMISXH_AKMOCL_FULLSCREEN=0` if a non-game borderless window should stay on its Space.
- The CN payment window check is fixture-backed, not verified against the live client.

## Workspace integration

The workspace adds this repository at `third-party/arknights-macos-runtime`. A relative
symlink at `patches/wine/arknights-macos-runtime` points at `wine-build-new/patches`, so
the Portfile keeps `filespath` at `patches/wine` and lists the patches as:

```text
arknights-macos-runtime/0001-... \
```

The FEX port no longer needs an entry.

## Validation

- All ten Wine patches apply with `patch -p1 -F0` after the workspace's 72-patch queue.
- No Wine build, prefix, game launch, or ACE run was performed for this export.
- ACE remains unverified. Complete the China update before judging an ACE result.
