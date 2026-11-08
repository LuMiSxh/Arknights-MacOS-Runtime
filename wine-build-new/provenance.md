# Provenance

Each patch in `wine-build-new/patches/` and `wine-build-new/fex/` is listed below.
The canonical copy of each patch is in [README.md](README.md#canonical-copies).

- `0001-ntdll-carry-eflags-af-df.patch` ports MetalSharp-Wine patch `0017` (`ntdll: Carry
  EFlags AF and DF through ARM64EC contexts`). The MetalSharp-Wine source is
  `metalsharp/MetalSharp-Wine` by Avery Felts, at https://github.com/metalsharp/MetalSharp-Wine.
  Source file in Wine: `dlls/ntdll/unwind.h`.
- `0002-ntdll-hybrid-thread-entry.patch` ports MetalSharp-Wine patch `0126` (`ntdll: Start an
  x64 thread entered on a hybrid module's native export on its x64 export`). Same upstream
  as `0001`. Source file in Wine: `dlls/ntdll/signal_arm64ec.c`.
- `0003-ntoskrnl-arknights-ace-imports.patch` is a reduced copy of the ntoskrnl surface in
  [patches/wine/provenance.md#0003-ace-imports](../patches/wine/provenance.md#0003-ace-imports).
  It adds three exports that Wine 11.18 lacks.
- `0004-userenv-appcontainer-apis.patch` is an original change for this repository. It is
  derived from the client's scoped `RuntimeSupport/Vuplex/UserenvCompat.c`. See
  [AppContainer provenance](../patches/wine/provenance.md#0004-appcontainer).
- `0005-ws2_32-address-list-sort.patch` is an original change for this repository. It
  implements the Microsoft Winsock `SIO_ADDRESS_LIST_SORT` contract. See
  [Winsock provenance](../patches/wine/provenance.md#0005-winsock-address-list-sort).
- `0006-ntdll-bilibili-cef80-stack-base.patch` is an original change for this repository. It
  adds the Bilibili CEF 80.1.15 descriptor. See
  [CEF provenance](../patches/wine/provenance.md#0006-cef).
- `0007-win32u-winemac-bilibili-layered-child.patch` is an original change for this
  repository. It adds the Bilibili layered-child route. See
  [Bilibili windowing provenance](../patches/wine/provenance.md#0007-bilibili-layered-child).
- `0008-winemac-bilibili-join-all-spaces.patch` is an original change for this repository. It
  makes the Bilibili platform window join all Spaces. See
  [Bilibili windowing provenance](../patches/wine/provenance.md#0008-bilibili-join-all-spaces).
- `0009-winemac-native-fullscreen-space.patch` is an original change for this repository. It
  reuses the fullscreen toggle that WineCX already has. See
  [fullscreen provenance](../patches/wine/provenance.md#0009-native-fullscreen-space).
- `0010-ntdll-hide-software-cursor-asset.patch` is an original change for this repository.
  It was prompted by a user report. See
  [hardware cursor provenance](../patches/wine/provenance.md#0010-hardware-cursor).
- `0011-winemac-command-q-quit.patch` is an original change for this repository. It ports the
  x86 Command-Q change in `patches/wine/0011-winemac-command-q-quit.patch` to Wine 11.18.
  See [Command-Q provenance](../patches/wine/provenance.md#0011-command-q).
- `fex/0001-arm64ec-restore-carried-eflags.patch` applies to FEX commit
  `14c92681f4d62cf84d901460e0358de09c8847a7` (`FEX-Emu/FEX`). The upstream author is not
  recorded in this repository. The FEX license is MIT; see
  [LICENSES/notices/fex.txt](../LICENSES/notices/fex.txt).

Wine base for the export: upstream Wine 11.18, commit `7b3fff76fa5178f6ce0141b2c776afa2a822f101`.

License of the Wine patches: LGPL-2.1-or-later (Wine).
