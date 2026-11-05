# Entitlements and removable workarounds

The current ARM64 lane has no Apple entitlement. Two restricted entitlements would remove the
largest workarounds.

Apple grants both entitlements only to approved signing identities. The current build is ad-hoc
signed, so it cannot use them.

## Entitlements

| Entitlement                                                | Effect                                                                                                           |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `com.apple.private.custom-x18-abi`                         | Custom `x18` ABI. The kernel keeps `x18` across exceptions for a process linked with the current SDK.            |
| `com.apple.developer.cross-architecture-support-unmanaged` | Unmanaged cross-architecture support. The loader can use the low 4 GB layout without relocating the shared page. |

## Workarounds to remove

| Workaround                                 | Location                          | Entitlement                                                | Action                                                                                                           |
| ------------------------------------------ | --------------------------------- | ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Loader SDK 12.0 relink                     | `scripts/arm/build.py`            | `com.apple.private.custom-x18-abi`                         | Link the loader with the current SDK. Remove the `-platform_version` override and its comment.                   |
| Shared-user-data relocation and 4 GB floor | `patches/arm/wine/address-space/` | `com.apple.developer.cross-architecture-support-unmanaged` | Remove the patch. Keep `KUSER_SHARED_DATA` at `0x7ffe0000` and the first TEB block below 4 GB.                   |
| Mixed-host-page `PROT_EXEC` drop           | `patches/arm/wine/wx-pages/`      | `com.apple.developer.cross-architecture-support-unmanaged` | Port the reference 4K page and W^X model (`0011`, `0019`) first. Remove this patch only after that model passes. |

Keep these patches. The entitlements do not replace them:

- `patches/arm/wine/ec-code-bitmap/`: the emulator must publish its JIT pages in the ARM64EC bitmap.
- `patches/arm/wine/arm64ec-unix-call/`: fixes a WineCX table mismatch.
- `patches/arm/wine/id-registers/`: macOS does not expose the ARM64 ID registers to EL0.
- `patches/arm/wine/mono/`, the FEX patches, and the FEX registry wiring.

## Window chrome

The ARM64 loader records SDK 12.0. The window server selects the window design from the main
executable's `LC_BUILD_VERSION`, so the game window uses the legacy title bar.

In-process workarounds do not change the real frame:

- `UIDesignRequiresCompatibility=NO` has no effect on an SDK-12 process.
- Interposing `dyld_get_program_sdk_version` does not change the frame.
- `_appearancePreferringSolarium` works only when the window is created titled. Wine creates a
  window borderless and adds the title bar later. The window server keeps the legacy design after
  that round trip.
- Changing the loader's recorded SDK to 26.0 makes Wine hang before `cmd /c ver`, because the
  current exception path still needs the SDK-12 kernel behavior.

With `com.apple.private.custom-x18-abi`, link the loader with the current SDK. The window server
should then select the current design. Expect the current title bar on the ARM64 lane. This is
unverified until the signed loader runs.

Until then, the ARM64 lane keeps the legacy window chrome. The client has no chrome bridge.
