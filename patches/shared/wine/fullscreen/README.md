# Native fullscreen Space

Wine source patch that puts a fullscreen game window into a macOS native fullscreen Space. The gate is `ARKNIGHTS_RUNTIME_NATIVE_FULLSCREEN_SPACE=1`. See the [Fullscreen patch registry](../../../docs/patch-registry.md#fullscreen).

A window already in a Space stays there while another process's modal dialog disables it. In a Space the close button is enabled and sends the normal Win32 close.

Apply: `0001-winemac-native-fullscreen-space.patch` to the pinned WineCX source. It applies to both the Rosetta and the ARM64 Wine branches, alone and after the `cn` family. The ARM64 branch has extra includes and an earlier shader-cache helper, so the `macdrv_main.c` hunks apply at an offset.
