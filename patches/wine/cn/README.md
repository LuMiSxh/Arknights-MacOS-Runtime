# CN compatibility patches

This directory is the ordered CN patch family for the `cn` and `combined`
runtime stages. The canonical, patch-by-patch description is the
[CN patch registry](../../../docs/patch-registry.md#cn).

All six patches use only `ARKNIGHTS_RUNTIME_CN_COMPAT=1`; absent, `0`, or any
other value leaves the ordinary Wine route selected. The registry records the
additional Bilibili image and window preflights.

Apply in this order:

1. `ntoskrnl/0001-ntoskrnl-compatibility-surface.patch`
2. `dispatcher/0001-kernel32-cn-dispatcher-spoof.patch`
3. `rosetta/0001-macos-rosetta-cn-workarounds.patch`
4. `timing/0001-ntdll-cn-qpc-relative-wait.patch`
5. `cef/0001-ntdll-bilibili-cef-80-stackbase.patch`
6. `windowing/0001-win32u-winemac-bilibili-layered-child.patch`

The historical `wintrust` candidate is intentionally omitted: it affected
`winex11.drv`/`winewayland.drv`, not `winemac.drv`, and would add an unrelated
signature bypass.
