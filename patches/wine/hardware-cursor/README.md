# Hardware Cursor compatibility

This directory contains the opt-in Wine patch that hides the game's software cursor asset for the
`hardware-cursor` and `combined` stages. The canonical patch contract is in the
[Hardware Cursor patch registry](../../../docs/patch-registry.md#hardware-cursor).

Set `ARKNIGHTS_RUNTIME_HARDWARE_CURSOR=1` to return `STATUS_OBJECT_NAME_NOT_FOUND` for the exact
case-insensitive final basename `a9d41799f1af1868f2db495671227cd4.bin`. Missing, `0`, or invalid
values leave Wine's normal path handling unchanged. The filter runs during shared name resolution,
covering file creation and both attribute-query APIs without changing the game installation.

Apply `0001-ntdll-hide-software-cursor-asset.patch` to the pinned WineCX source.
