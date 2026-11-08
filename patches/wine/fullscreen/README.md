# Native fullscreen Space

Wine source patch that puts a fullscreen game window into a macOS native fullscreen Space. The gate is `LMISXH_AKMOCL_FULLSCREEN=1`. See the [Fullscreen patch registry](../../../docs/patch-registry.md#fullscreen).

A window already in a Space stays there while another process's modal dialog disables it. In a Space the close button is enabled and sends the normal Win32 close.

Apply: `0001-winemac-native-fullscreen-space.patch` to the pinned WineCX source. It applies to both the Rosetta and the ARM64 Wine branches, alone and after the `cn` family. The ARM64 branch has extra includes and an earlier shader-cache helper, so the `macdrv_main.c` hunks apply at an offset.

Content clicks stay in the Wine view. They do not reach the Cocoa frame drag handler. This prevents repeated activation and display refreshes in a native fullscreen Space.

Layered windows stay auxiliary to the fullscreen game. The driver tracks `WS_EX_LAYERED` at creation and on style changes, including the borderless feature path. This prevents transparent platform overlays from opening a separate Space.
