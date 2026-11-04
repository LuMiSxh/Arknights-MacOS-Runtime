# Provenance

This is an original change for this repository, not a port.

- Source: `dappermint/winecx`, branch `arm64-1117`, commit
  `c8ef4872c1d53120b80aa92185fc7e295d94d092`.
- Function: `install_wine_mono()` in `dlls/mscoree/mscoree_main.c`.
- License: LGPL-2.1-or-later, inherited from WineCX.
- Reason: the Wine Mono support package requires 32-bit helpers, which cannot
  run on native ARM64 macOS without the cross-architecture entitlement.
