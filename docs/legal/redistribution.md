# Runtime redistribution inventory

The clean release build starts with an empty `Libraries/` directory. It installs Wine (64-bit only, without GStreamer or FFmpeg) and DXMT from the pinned patched source trees, copies MoltenVK from the checksum-pinned base artifact, and copies a dynamic library closure from the pinned Nixpkgs revision. It does not copy DXVK, Wine Mono, Wine Gecko, GStreamer plugins, FFmpeg or codec libraries, 32-bit payloads, or the product metadata of the base runtime.

## Identified components

- WineCX / Wine: Windows compatibility runtime.
  - Pinned source: [`dappermint/winecx@e0aa380`](https://github.com/dappermint/winecx/tree/e0aa380780b73e20fabcfe78fd42713b94929a53)
  - License evidence: `LGPL-2.1-or-later`; [`LICENSES/Wine-LGPL-2.1.txt`](../../LICENSES/Wine-LGPL-2.1.txt)
  - Source obligation: Ship complete corresponding source for the modified build and the applicable LGPL materials.
- DXMT: D3D10/D3D11/Metal payload and WineMetal bridge.
  - Pinned source: [`3Shain/dxmt@7c8dee1`](https://github.com/3Shain/dxmt/tree/7c8dee1c2d73415301ceb7d1fa810861cef4cd67)
  - License evidence: `LGPL-2.1-or-later`; [`LICENSES/DXMT-LGPL-2.1.txt`](../../LICENSES/DXMT-LGPL-2.1.txt)
  - Source obligation: Ship complete corresponding source for the modified build and the applicable LGPL materials.
- MoltenVK: Vulkan-to-Metal dynamic library.
  - Pinned source: [`KhronosGroup/MoltenVK@db66022`](https://github.com/KhronosGroup/MoltenVK/tree/db66022459ffb663aa2b50f6b018bc2e124f5edf)
  - License evidence: `Apache-2.0`; [upstream license](https://github.com/KhronosGroup/MoltenVK/blob/db66022459ffb663aa2b50f6b018bc2e124f5edf/LICENSE)
  - Source obligation: Include the Apache license and notices; retain the exact pinned source link in the inventory.
- Pinned Nix library closure: Font, TLS, compression, and Unicode libraries copied beside Wine.
  - Pinned source: [`NixOS/nixpkgs@ac62194`](https://github.com/NixOS/nixpkgs/tree/ac62194c3917d5f474c1a844b6fd6da2db95077d)
  - License evidence: Realised store outputs are recorded by the clean build; canonical GPL, LGPL, Apache, and MIT texts are under [`LICENSES/runtime/`](../../LICENSES/runtime/)
  - Source obligation: Keep the realised output inventory, exact Nixpkgs revision, canonical texts, and generated notices together in the release assets.

The direct Nix inputs are FreeType, GnuTLS, libpng, zlib, Brotli, bzip2, Nettle, libtasn1, libidn2, p11-kit, libunistring, GMP, and Vulkan-Headers. The build follows Mach-O references and records transitive libraries in the generated inventory.

The opt-in Hardware Cursor Wine patch filters the exact region-specific cursor asset basename during file-name resolution. It does not contain, redistribute, or modify game assets. The game installation remains user-owned and unchanged.

## Generated release inventory

The clean build writes `runtime-component-inventory.tsv`. Wine, DXMT, and MoltenVK map to their locked source identities. Each Nix library maps to the realised store output and the pinned Nixpkgs revision it came from. The release workflow includes the inventory in the source archive, as a separate draft asset, and in the generated third-party notices.
