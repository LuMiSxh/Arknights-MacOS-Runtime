# ARM64 address space provenance

## Source pins

- Wine base: `dappermint/winecx`, branch `arm64-1117`
- Wine commit: `c8ef4872c1d53120b80aa92185fc7e295d94d092` (Wine 11.17)
- Reference fork: [`metalsharp/MetalSharp-Wine`](https://github.com/metalsharp/MetalSharp-Wine), Wine 11.20
- Reference patches: `0003`, `0008`, `0016` in `patches/wine/`
- Original author: Avery Felts `<averyfelts@aol.com>`
- License: LGPL-2.1-or-later (Wine)

## Ported inventory

### `0003` — run on arm64 macOS without low 4 GB remapping

Ports the shared user data relocation, the `__wine_user_shared_data` export and its
PE consumers, and the `signal_arm64.c` fault emulation.
The reference patch also changes the write/execute page handling; WineCX 11.17 already
flips those pages in `virtual_handle_fault`, so that part is not ported.

### `0008` — emulate `LDAPUR` loads from the canonical address

Adds the `ldapur`/`ldapurs*` forms that x86 emulators emit for TSO loads to the
emulation added by `0003`.

### `0016` — skip occupied regions when searching for free memory

Applies unchanged.

### Reference `0005`

Not ported as a separate change. The relocation in `virtual_alloc_first_teb` runs after
the canonical mapping fails, which covers the probe's intent.

## Adaptations for WineCX 11.17

- The four PE consumers declare `DECLSPEC_IMPORT` before the type. Clang rejects the
  reference placement after the pointer.
- The first 64-bit TEB block no longer passes the low-2 GB hint on arm64 macOS, because
  that range is not mappable either. 32-bit processes keep the old behavior.
- The relocation and TEB changes live in `virtual_alloc_first_teb`; Wine 11.20 renamed
  the function to `virtual_alloc_first_thread_data`.
- `init_user_space_floor()` is an addition for macOS 26 and later. The main executable's
  Mach-O reservation sits above 4 GB and is not visible to `mach_vm_region`, so the
  patch probes for the first mappable page instead of using a fixed floor.
