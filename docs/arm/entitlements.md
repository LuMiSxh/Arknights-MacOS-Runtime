# Entitlements and window chrome

The ARM64 runtime is built in the external
[wine-build-new](https://github.com/riverfog7/wine-build-new) workspace. That build has the
cross-architecture entitlement. This repository cannot obtain the same profile, so it pins the
released artifact and never re-signs the loader.

## Entitlements

| Entitlement                                                | Effect                                                                                                 |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `com.apple.developer.cross-architecture-support`           | Cross-architecture support. The loader can use the low 4 GB layout without relocating the shared page. |
| `com.apple.developer.cross-architecture-support-unmanaged` | The free-account variant of the same capability.                                                       |
| `com.apple.private.custom-x18-abi`                         | Custom `x18` ABI. The kernel keeps `x18` across exceptions for a process linked with the current SDK.  |

Apple grants these entitlements only to approved signing identities. A profile binds one team, one
App ID, and the Macs in the profile. Another team cannot reuse the signature.

## Workarounds

The external build uses the cross-architecture entitlement. It does not need the shared-user-data
relocation, the 4 GB floor, or the mixed-page workaround. Those workarounds belong to the
entitlement-free reference build and are not part of the shipped ARM64 path.

The external build keeps these changes in its own patch queue:

- The ARM64EC code bitmap marks the emulator's JIT pages.
- The ARM64EC unix-call table is fixed for the upstream Wine tree.
- The ARM64 ID registers are synthesized from the `hw.optional.arm.*` sysctls.
- FEX code buffers use the Hadron JIT and W^X model.

See the [patch export](wine-build-new.md) for the Arknights patches and the workspace queue.

## Window chrome

The window server selects the window design from the main executable's `LC_BUILD_VERSION`. The
external loader keeps its signed build metadata and cannot be relinked or re-signed by this
repository.

With `com.apple.private.custom-x18-abi`, the loader can record the current SDK and keep `x18`. The
window then uses the current design. The external profile currently grants only the
cross-architecture entitlement, so expect the legacy window chrome until the profile also carries
the custom-x18 entitlement.

In-process workarounds do not change the real frame:

- `UIDesignRequiresCompatibility=NO` has no effect on a legacy-SDK process.
- Interposing `dyld_get_program_sdk_version` does not change the frame.
- `_appearancePreferringSolarium` works only when the window is created titled. Wine creates a
  window borderless and adds the title bar later. The window server keeps the legacy design after
  that round trip.

The client has no chrome bridge. Do not add one.
