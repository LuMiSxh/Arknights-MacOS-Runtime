# Provenance

Port of the ID-register hunk in `metalsharp/MetalSharp-Wine` patch `0004`
("Synthesize ARM64 ID registers on macOS; use FEX as the x86 emulators"),
Avery Felts.

- Source in this repository: `dlls/ntdll/unix/system.c`.
- License: LGPL-2.1-or-later (Wine).
- Scope: arm64 macOS only. Linux keeps the `AT_HWCAP_CPUID` path.
- Not included: the Wow64 registry hunk, which is in
  [`wine/fex`](../fex/README.md).
