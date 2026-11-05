# Provenance

Original change for this repository.

- Source in this repository: `FEXCore` and `Source/Windows`.
- License: MIT (FEX).
- Scope: Windows and macOS only. The hooks are null on other hosts.
- Evidence: observed in the native ARM64 canary; FEX code buffers stay writable and executable with `MAP_JIT`.
