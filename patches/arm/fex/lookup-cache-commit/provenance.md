# Provenance

Original change for this repository.

- Source in this repository: `FEXCore/Source/Interface/Core/LookupCache.cpp`.
- License: MIT (FEX).
- Scope: Windows only. `FEXCore::Allocator::VirtualAlloc` ignores the commit
  flag on every other host.
- Evidence: observed in the native ARM64 canary; the probe compiles the entry block and prints `fex-ok`.
