# Provenance

This change follows the registry part of `metalsharp/MetalSharp-Wine` patch
`0004` ("Synthesize ARM64 ID registers, default Wow64 to the FEX modules").

- Reference: `metalsharp/MetalSharp-Wine`, Wine 11.20, patch `0004`.
- Source in this repository: `loader/wine.inf.in`.
- License: LGPL-2.1-or-later (Wine).
- Scope: native-arm64 only. The x86_64 lane keeps the `xtajit` modules.

The ID-register and `EFlags` parts of the reference patch are not included.
They remain on the porting list.
