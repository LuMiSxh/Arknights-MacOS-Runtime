# wine-build-new export

This directory is the Arknights patch export for the signed ARM64 runtime built in
[wine-build-new](https://github.com/riverfog7/wine-build-new). That workspace consumes this
repository as a submodule at `third-party/arknights-macos-runtime`.

The workspace builds upstream Wine 11.18 with a 72-patch Hadron and Endfield queue. The
patches here are rebased against that queue, not against this repository's WineCX 11.17
tree. The workspace links each patch individually from `wine-build-new/patches/` into
`patches/wine/arknights-macos-runtime/`, matching its other third-party patch families.
The canonical copy of each patch is listed under [Canonical copies](#canonical-copies).

## Layout

| Path        | Content                                                   |
| ----------- | --------------------------------------------------------- |
| `patches/`  | Fourteen Wine patches, applied after the 72-patch queue   |
| `fex/`      | The paired FEX context patch for Wine patch `0001`        |
| `lock.json` | Machine-readable list of paths, hashes, and runtime gates |

## What is in the export

The workspace applies all fourteen patches at build time. The `LMISXH_AKMOCL_*` variables gate
behavior at runtime; they do not select patches at build time.

| Patch                                              | Runtime gate             | Need                  | Purpose                                                  |
| -------------------------------------------------- | ------------------------ | --------------------- | -------------------------------------------------------- |
| `0001-ntdll-carry-eflags-af-df.patch`              | opt-out `_EFLAGS`        | keep until ACE run    | Keeps PF, AF and DF across ARM64EC context switches.     |
| `0002-ntdll-hybrid-thread-entry.patch`             | opt-out `_HYBRID_THREAD` | keep until ACE run    | Starts a hybrid-module thread on its x64 export.         |
| `0003-ntoskrnl-arknights-ace-imports.patch`        | opt-out `_ACE_IMPORTS`   | keep until ACE run    | Adds three kernel imports that ACE resolves.             |
| `0004-userenv-appcontainer-apis.patch`             | opt-out `_APPCONTAINER`  | required for CEF      | Adds the AppContainer names Chromium resolves.           |
| `0005-ws2_32-address-list-sort.patch`              | opt-out `_WINSOCK`       | required for CEF      | Implements `SIO_ADDRESS_LIST_SORT` for AsyncDns.         |
| `0006-ntdll-bilibili-cef80-stack-base.patch`       | opt-out `_CEF`           | required for Bilibili | Bilibili CEF 80.1.15 stack-base descriptors.             |
| `0007-win32u-winemac-bilibili-layered-child.patch` | `_CN` (default off)      | required for Bilibili | Bilibili layered child window.                           |
| `0008-winemac-bilibili-join-all-spaces.patch`      | `_CN` (default off)      | required for Bilibili | Bilibili payment window on every Space. Requires `0007`. |
| `0009-winemac-native-fullscreen-space.patch`       | `_FULLSCREEN` (default off) | ours, user-visible | Puts fullscreen games in a native macOS Space.           |
| `0010-ntdll-hide-software-cursor-asset.patch`      | `_CURSOR` (default off)  | ours, user-visible    | Hides the two game software-cursor assets.               |
| `0011-winemac-command-q-quit.patch`               | opt-out `_MENU`          | ours, user-visible    | Makes Command+Q quit from the app menu.                  |
| `0012-ntdll-name-the-macos-loader-link-after-the-application.patch` | none (always on) | ours, user-visible | Names the loader link and `WINEPRELOADERAPPNAME` after the program. |
| `0013-winemac-name-the-application-menu-after-the-program.patch` | none (always on) | ours, user-visible | Shows `WINEPRELOADERAPPNAME` in the Hide and Quit menu items. |
| `0014-ntdll-promote-cx-unix-environment-variables.patch` | none (always on) | launcher helper injection | Promotes `__CX_UNIX_<name>` to the child's Unix environment. |

`0001` to `0006` and `0011` default on: unset or exactly `1` keeps the patch on. `0007`, `0008`, `0009`, and `0010` default off: only exactly `1` enables them. Any other value turns the patch off.

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
less durable than the shared NT name resolver. `0009` and `0010` both stay opt-in.

## Paired FEX context patch

Apply `fex/0001-arm64ec-restore-carried-eflags.patch` after the FEX patch queue in
`wine-build-new`. Its source pin and checksum are in `lock.json` under `fex`.
Build and deploy it with Wine patch `0001`. Do not deploy the FEX patch with an
older Wine runtime that drops these context bits.

Wine and FEX use CPSR packet bits 26, 27 and 19 for PF, AF and DF. Wine converts
these bits in saved contexts. FEX accepts the restored flags when it resumes x64
execution. Both sides use `LMISXH_AKMOCL_EFLAGS`: unset or `1` keeps the patch on;
any other value turns it off.

The address-list patch preserves input order as a compatibility fallback. It does
not implement Windows destination-address ranking. It validates the count and
copy sizes before writing output and uses Wine's existing asynchronous completion
path for both separate and in-place buffers.

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
- **Audio and DXMT.** Not required for login or ACE. The DXMT patch also targets a
  different DXMT pin. The loader-name patches `0012` and `0013` are in the export.

## Gates and opt-outs

`0001` to `0006` and `0011` default on: unset or exactly `1` keeps the patch on.
Any other value turns it off.

`0012` to `0014` have no runtime gate and are always applied. `0012` names the loader
link after the program and sets `WINEPRELOADERAPPNAME`; `0013` reads that variable;
`0014` does nothing unless the program sets a `__CX_UNIX_<name>` variable.

```sh
LMISXH_AKMOCL_EFLAGS=0          # Do not carry PF, AF and DF
LMISXH_AKMOCL_HYBRID_THREAD=0   # Do not fix up hybrid-module thread entries
LMISXH_AKMOCL_ACE_IMPORTS=0     # Do not export the ACE kernel imports
LMISXH_AKMOCL_APPCONTAINER=0    # Do not implement the AppContainer names
LMISXH_AKMOCL_WINSOCK=0         # Do not implement SIO_ADDRESS_LIST_SORT
LMISXH_AKMOCL_CEF=0             # Do not apply the Bilibili CEF descriptor
LMISXH_AKMOCL_MENU=0            # Do not make Command+Q quit from the app menu
```

`0007`, `0008`, `0009`, and `0010` default off. Only exactly `1` enables them:

```sh
LMISXH_AKMOCL_CN=1          # Bilibili window behavior (0007 and 0008)
LMISXH_AKMOCL_CURSOR=1      # Hide the software cursor asset (0010)
LMISXH_AKMOCL_FULLSCREEN=1  # Use a native fullscreen Space
```

`0008` uses the process check that `0007` adds, so the two are always applied together.
Each ACE patch has its own default-on gate.

The Global client does not need `LMISXH_AKMOCL_CN`. It does not load the Bilibili CEF build, and `0006` does not cover the Global CEF build.

## Known limitations

- `0006` patches Bilibili `libcef.dll` in memory after a byte preflight. It does not
  verify the image hash and is not atomic if a later page protection change fails. Set
  `LMISXH_AKMOCL_CEF=0` to disable it.
- `0007` adds a property and class lookup to every layered window update before the gate
  check. The behavior is opt-in, but the code is compiled in for every user.
- `0009` selects windows by shape, not by application name. Leave
  `LMISXH_AKMOCL_FULLSCREEN` unset if a non-game borderless window should stay on its Space.
- The CN payment window check is fixture-backed, not verified against the live client.

## Workspace integration

The workspace adds this repository at `third-party/arknights-macos-runtime`. Each patch
file is linked individually into `patches/wine/arknights-macos-runtime/`, so the Portfile
keeps `filespath` at `patches/wine` and lists the patches as:

```text
arknights-macos-runtime/0001-... \
```

The FEX port no longer needs an entry.

## Workspace pins

| Item        | Value                                                                  |
| ----------- | ---------------------------------------------------------------------- |
| Workspace   | [wine-build-new](https://github.com/riverfog7/wine-build-new), branch `arknights-arm64` |
| Wine        | Upstream 11.18, commit `7b3fff76fa5178f6ce0141b2c776afa2a822f101`     |
| FEX         | Commit `14c92681f4d62cf84d901460e0358de09c8847a7`                      |
| Hadron      | Commit `6f401bcfcf4c1cbf7fbd724974fc8d3562262b1c`                      |
| Endfield    | Commit `568afd1a32e25e40170eb7484f6790d1e1d370fd`                      |
| Submodule   | `third-party/arknights-macos-runtime`, branch `main`                   |
| Patch alias | `patches/wine/arknights-macos-runtime/`, one symlink per patch         |

## Canonical copies

Edit the canonical copy, then rebase it into `wine-build-new/patches/`. Where the canonical copy is this directory, edit it here.

| Patch                  | Canonical copy                              |
| ---------------------- | ------------------------------------------- |
| `0001`, `0002`         | `wine-build-new/patches/` (this directory)  |
| `0003`                 | `patches/wine/0003-ntoskrnl-arknights-ace-imports.patch` (reduced) |
| `0004`                 | `patches/wine/0004-userenv-appcontainer-apis.patch` |
| `0005`                 | `patches/wine/0005-ws2_32-address-list-sort.patch` |
| `0006`                 | `patches/wine/0006-ntdll-bilibili-cef80-stack-base.patch` (rebased) |
| `0007`, `0008`         | `patches/wine/0007-win32u-winemac-bilibili-layered-child.patch`, `patches/wine/0008-winemac-bilibili-join-all-spaces.patch` (rebased) |
| `0009`                 | `patches/wine/0009-winemac-native-fullscreen-space.patch` (rebased) |
| `0010`                 | `patches/wine/0010-ntdll-hide-software-cursor-asset.patch` |
| `0012`, `0013`, `0014` | `wine-build-new/patches/` (this directory)  |
| `fex/0001`             | `wine-build-new/fex/` (this directory)      |

## Workspace queue audit

| Question                                      | Result                                                                                                                                                       |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| FEX lookup-cache eager commit                 | Not needed. The workspace FEX `local/0009` commits the L1 window in the constructor, after a cache clear, and when the window grows.                        |
| Mono skip                                     | Not needed. The workspace ships no Wine Mono, the entitlement removes the low-4 GB constraint, and `WINEDLLOVERRIDES=mscoree=d` covers a fresh prefix.     |
| ACE imports (`0003`)                          | Kept until an ACE run. Wine 11.18 lacks the exports, but no Arknights ACE import dump was available.                                                         |
| Hybrid thread entry (`0002`)                  | Kept until an ACE run. The reference fix is an EA overlay case, not ACE.                                                                                     |
| AF/DF context (`0001`)                        | Kept until an ACE run. FEX rebuilds emulated flags, but native ARM64EC context handling still drops them.                                                    |
| AppContainer (`0004`)                         | Kept. It replaces a per-game `userenv.dll` shim and covers all clients.                                                                                      |
| AsyncDns (`0005`)                             | Kept. It replaces a per-game `--disable-features=AsyncDns` workaround.                                                                                       |
| Bilibili CEF and windowing (`0006` to `0008`) | Kept. No client-side equivalent exists for the CEF descriptor or layered surfaces. `0006` is on by default; `0007` and `0008` stay opt-in.                  |
| Fullscreen (`0009`)                           | Kept. A Windows DLL cannot change the `NSWindow` collection behavior or the fullscreen handshake.                                                            |
| Hardware cursor (`0010`)                      | Kept. A proxy DLL covers only wrapped APIs. Deleting the assets is undone by Repair.                                                                         |

ACE remains unverified. Drop `0001` to `0003` only after an ACE run on the signed runtime shows they are unnecessary. The China update must complete first.

### Work the workspace already has

Do not send the matching Arknights patches. The Hadron and Endfield queues already provide the same behavior.

| Work                                                                       | Provided by                                                                               |
| -------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| 4 GB `__PAGEZERO`, top-down allocations, cross-architecture loader         | Hadron wine `0001`, `0008`, `0040`; `local/0003`                                          |
| Executable and writable host-page flips                                    | Hadron wine `0002`, `0006`, `0034`, `0035`, `0036`                                        |
| ARM64 ID registers                                                         | Hadron wine `0020`                                                                        |
| ARM64EC code bitmap, `RtlIsEcCode` bounds                                  | Hadron wine `0011`, `0041`                                                                |
| Per-thread W^X JIT, `MAP_JIT`, unaligned back-patching, EC-code allocation | Hadron FEX `0001` to `0005`                                                               |
| Wow64 registry values                                                      | The `fex-wine` port installs `xtajit.dll` and `xtajit64.dll`                              |
| ACE timing, dispatcher spoof, object callbacks, notify routines            | Endfield `misc/0009` to `0011`, `ace-core/0003` to `0015`, `adapted/0001`, `0012`, `0017` |

## Entitlements

The workspace profile currently grants `com.apple.developer.cross-architecture-support`.
It does not yet grant `com.apple.private.custom-x18-abi`. Confirm the final profile before judging
the window chrome. See [entitlements and window chrome](../docs/arm/README.md#entitlements-and-window-chrome).

## Yaagl

Yaagl has no generic patch-gate layer. It selects a Wine distribution per game and sets
environment variables in each client's `program-launch-game.ts`. It already uses this for
`WINEDLLOVERRIDES`, `WINEMSYNC`, `WINEESYNC`, and `WINE_ENABLE_TIMEOUT_FIX`.

Upstream Yaagl has no Arknights client, so this change adds nothing to Yaagl. A future
Arknights client sets the opt-outs it needs. The CN and cursor patches still need
`LMISXH_AKMOCL` and their modifier.

## Updating the export

1. Change the canonical patch (see [Canonical copies](#canonical-copies)).
2. Rebase it onto the workspace queue in a Wine 11.18 checkout.
3. Run the full queue. Every patch must apply with `-F0`.
4. Replace the file under `wine-build-new/patches/`.
5. Update the gate or provenance in this file when the contract changes.

## Validation

- All fourteen Wine patches apply with `patch -p1 -F0` after the workspace's 72-patch queue.
- No Wine build, prefix, game launch, or ACE run was performed for this export.
- ACE remains unverified. Complete the China update before judging an ACE result.
