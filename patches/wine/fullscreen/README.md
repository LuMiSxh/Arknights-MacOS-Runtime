# Native fullscreen Space

Wine source patch that puts a fullscreen game window into a macOS native fullscreen Space. The gate is `ARKNIGHTS_RUNTIME_NATIVE_FULLSCREEN_SPACE=1`. See the [Fullscreen patch registry](../../../docs/patch-registry.md#fullscreen).

A window already in a Space stays there while another process's modal dialog disables it.

Apply: `0001-winemac-native-fullscreen-space.patch` to the pinned WineCX source. It applies alone and after the `cn` family.
