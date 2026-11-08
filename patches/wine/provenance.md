# Wine patch provenance

## Source pins

- Wine base: `dappermint/winecx`
- Wine commit: <!-- pin:wine.commit|code -->`a54b8240683e92bf4c15cb1ba6bf92a9539bd768`<!-- /pin --> (Wine <!-- pin:wine.version -->11.17<!-- /pin -->)
- ACE reference: [`stoicswe/Endfield_FineWine`](https://github.com/stoicswe/Endfield_FineWine)
- ACE reference checkout: `e5d4ccad235eefe32d912733e57e4c0bb53a5b58`
- ACE reference patch sets (upstream names): `stage1-macos` and `stage2-dwproton`

The reference repository records the original dw-proton/Endfield work and
authors. The ACE patches port selected changes to this WineCX pin.
Every Wine patch keeps the LGPL-2.1-or-later license of Wine.

## 0003 ACE imports

An Endfield FineWine port of the non-X11 kernel surface. The reference records
the original authors.

The patch carries:

- process image name and primary-token support
- thread process and context accessors
- current-thread process and process-ID accessors, as unconditional aliases of
  the current-process functions
- unconditional image-name and exit-status accessors for valid process objects,
  without NULL checks on their `_In_` process parameters
- the `KeCapturePersistentThreadState` export stub: it logs its arguments,
  returns `STATUS_NOT_IMPLEMENTED`, and never dereferences or writes through a
  pointer
- the callable `SeSetAuditParameter` no-op: it logs its arguments and returns
  `STATUS_SUCCESS` when the gate is on, and never dereferences or writes through
  its pointer arguments. Otherwise the original Wine stub stays active.
- physical-memory compatibility stubs
- process-object metadata lifetime handling

Wine 11.17 already provides the process session and creation-time accessors and
the bug-check callback exports, so the patch omits them.

The ARM copy is a reduced copy that adds three exports that Wine 11.18 lacks.
The x86 copy keeps the full surface.

## 0004 AppContainer

Original change for this repository, derived from the client's scoped
`RuntimeSupport/Vuplex/UserenvCompat.c`.

- Source: `dappermint/winecx`, branch `arm64-1117`, commit
  `c8ef4872c1d53120b80aa92185fc7e295d94d092`.
- Files: `dlls/userenv/userenv_main.c`, `dlls/userenv/userenv.spec`,
  `dlls/kernelbase/kernelbase.spec`, `dlls/kernelbase/security.c`.
- Reference: Microsoft AppContainer `userenv.dll` contract and the client shim's
  Windows-compatible SID derivation.

## 0005 Winsock address list sort

Original change for this repository.

- Source: `dappermint/winecx`, branch `arm64-1117`, commit
  `c8ef4872c1d53120b80aa92185fc7e295d94d092`.
- Files: `include/winsock2.h`, `include/wine/afd.h`, `dlls/ws2_32/socket.c`,
  `dlls/ntdll/unix/socket.c`.
- Reference: Microsoft Winsock `SIO_ADDRESS_LIST_SORT` contract.

## 0006 CEF

Original Arknights macOS Runtime change. The generic CEF dispatcher isolates
regional descriptors from the loader mechanism.

The `bilibili-cef80` descriptor covers CEF 80.1.15. It is limited to the
`libcef.dll` basename, the three proven RVAs, and all expected bytes, checked
before any write. It is tagged as the CN descriptor.
Do not add a descriptor without reverse-engineering evidence for its complete
hash, RVA, and byte contract.

## 0007 Bilibili layered child

Original Arknights macOS Runtime change for the verified client window contract.
It is separate from the CEF and ACE families.

The layered-child renderer route is limited to `PCGamePlatform.exe`, the
Chromium `Chrome_WidgetWin_0` and `Chrome.WindowTranslucent` property contract,
and a `CMyWebViewDlg` anywhere in the parent chain of the candidate. This
supports nested Bilibili dialogs. Only the CN gate enables the route. The route
keeps the bounded Bilibili image and window preflights.

## 0008 Bilibili join all Spaces

Original Arknights macOS Runtime change. It makes the Bilibili platform window
join all Spaces under the same gate as `0007`.

## 0009 Native fullscreen Space

Original Arknights macOS Runtime change. It changes `dlls/winemac.drv` only. It
reuses the fullscreen toggle that WineCX already has for resizable windows. It
adds no code from another project.

The ARM copy is in `wine-build-new/patches/0009-winemac-native-fullscreen-space.patch`.
The ARM branch has extra includes and an earlier shader-cache helper, so its
`macdrv_main.c` hunks apply at an offset.

## 0010 Hardware cursor

Original Arknights macOS Runtime change.

- User report: [PC client cursor-stutter discussion](https://www.reddit.com/r/arknights/comments/1vorlzp/pc_client_fix_for_the_annoying_mouse_stuttering/)

When the gate is on, the patch filters either exact case-insensitive cursor asset
basename from the shared NT-to-Unix path resolution of Wine:
`a9d41799f1af1868f2db495671227cd4.bin` for the Yostar Global/Japan/Korea and
Taiwan clients, or `f7bcd64480c4566f25d65d642f5fba95.bin` for the China -
Bilibili client. It covers file opens and metadata lookups and blocks
create-if-missing calls. It does not read, embed, copy, or modify game asset
contents.

The Wine test additions cover exact and uppercase basenames for both assets,
near-match basenames, create-if-missing behavior, and both attribute-query APIs,
with the gate absent and enabled.

## 0011 Command-Q

Original Arknights macOS Runtime change. It changes the Quit item of the
application menu in `dlls/winemac.drv/cocoa_app.m` from the mask
`NSEventModifierFlagCommand | NSEventModifierFlagOption` to
`NSEventModifierFlagCommand`. The other menu items keep their masks.

## 0012 Audio default output

Port of the two-commit Wine draft merge request
[!11370](https://gitlab.winehq.org/wine/wine/-/merge_requests/11370),
`winecoreaudio: Expose virtual endpoints for default devices`.

- Upstream project: [Wine](https://gitlab.winehq.org/wine/wine)
- Upstream patch commits: `4d143f4cdbba2302799c29d67bf404ba2a60004f` and
  `65140f3139855dcc3fb96091210e3bb95ac7327f`
- Original author: Rhodri Richards (`rhodri.development@gmail.com`)
- Base runtime source: `dappermint/winecx` commit
  <!-- pin:wine.commit|code -->`a54b8240683e92bf4c15cb1ba6bf92a9539bd768`<!-- /pin -->
  (Wine <!-- pin:wine.version -->11.17<!-- /pin -->)
- License: the modified Wine source file is LGPL-2.1-or-later. This patch uses
  the same license. Preserve the Wine copyright and license header when you
  distribute a built runtime.

This canary carries an unmerged Wine draft. The draft can change its
endpoint-notification semantics, so a successful compile does not prove upstream
compatibility. The patch adds no third-party dependency.

## 0013 ACE timing

An Endfield FineWine port of the relative `NtDelayExecution` QPC path. The
reference records the original authors. The patch applies only to negative
relative waits.

## 0014 ACE dispatcher

An Endfield FineWine port of the x86_64 `KiUserApcDispatcher` and
`KiUserCallbackDispatcher` `GetProcAddress` int3-stub workaround. The reference
records the original authors. It uses no process-name heuristics. The stub is
x86 machine code, so the patch is x86-only.

## 0015 ACE Rosetta

An Endfield FineWine port of the Rosetta workarounds that the ACE client needs:
bounded multi-byte NOP decoding, and classification of the ACE
privileged-instruction fault that Rosetta reports as an invalid-opcode trap.
CrossOver CET and XGETBV handling is unchanged. The reference records the
original authors. The patch is x86-only and changes `signal_x86_64.c`.

## Canonical copies

The x86 copies live in this directory. The ARM copies live in
`wine-build-new/patches/`. The copies can differ in content, but they share
numbers, names, gates, and gate semantics. Edit the copy for its target, then
rebase.
