# ARM64 patches

This directory holds patches that apply only to the native-arm64 target.
Shared patches are in `../shared/`, and x86_64-only patches are in `../x86/`.

Families:

- [`wine/address-space`](wine/address-space/README.md): relocates the shared user
  data page, finds a mappable floor above the main executable's Mach-O reservation,
  and emulates canonical-address loads.
- [`wine/fex`](wine/fex/README.md): points the Wow64 values at the FEX modules
  that the ARM64 build ships.
- [`wine/mono`](wine/mono/README.md): skips the Wine Mono installer, which needs
  32-bit helpers that cannot run without the cross-architecture entitlement.

Still to write:

- ARM64 ID registers and `EFlags` (reference `0004`/`0017`).
- Hybrid entry points and executable data views (reference `0126`/`0128`).
- The ARM64 port of the ACE dispatcher spoof. The x86 patch embeds `int3` machine
  code, which cannot compile for ARM64EC, and CN clients set `ACE_COMPACT=1`.

Name a target list in `runtime.lock.json` for each patch here.
A patch without that list applies to every target.
