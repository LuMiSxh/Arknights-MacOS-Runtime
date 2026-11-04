# Use the FEX modules for Wow64 on ARM64

Wine's `wine.inf` points the `Wow64` values at the x86 emulator interfaces
`xtajit64.dll` and `xtajit.dll`. The native-arm64 build ships `libarm64ecfex.dll`
and `libwow64fex.dll` instead, so a 64-bit Windows program loads but never starts.

This patch changes only the `CurrentVersionWow64.ntarm64` section:

| Value                    | Default          | Arm64 build          |
| ------------------------ | ---------------- | -------------------- |
| `Wow64\amd64`            | `xtajit64.dll`   | `libarm64ecfex.dll`  |
| `Wow64\x86`              | `xtajit.dll`     | `libwow64fex.dll`    |

The `Wow64\arm` value and the known-DLL entries stay unchanged.
The x86_64 lane never receives this patch.

Apply time: after the shared patches, before the prefix is created.
