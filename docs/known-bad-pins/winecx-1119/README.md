# winecx wine1119 repair patches (reference only)

These patches are not part of the runtime. The patch guard and the lock do not read this folder.

Each patch repairs one defect of `dappermint/winecx` commit `b1417d2` (11.19) on macOS x86_64. See [Known-bad pins](../../updating-pins.md#known-bad-pins).

1. `0002-ntdll-drop-early-dbg-init.patch` removes the early `dbg_init()` call.
2. `0003-macos-restore-top-down-reserve.patch` restores the `WINE_TOP_DOWN` reserve.
3. `0004-ntdll-guard-null-peb-in-virtual-map-image.patch` guards the NULL `peb` in `virtual_map_image`.

Patches 0002 and 0003 were verified in a scratch prefix. Patch 0004 was not verified.
