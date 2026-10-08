# Hardware Cursor compatibility

Opt-in Wine patch that hides the software cursor asset of the game, for the `hardware-cursor` and `combined` stages. See the [Hardware Cursor patch registry](../../../docs/patch-registry.md#hardware-cursor).

`ARKNIGHTS_RUNTIME_HARDWARE_CURSOR=1` returns `STATUS_OBJECT_NAME_NOT_FOUND` for the two exact cursor asset basenames in the registry. Otherwise path handling is normal. The filter runs in shared name resolution and covers file creation and both attribute-query APIs.

Apply: `0001-ntdll-hide-software-cursor-asset.patch` to the pinned WineCX source.
