# Provenance

Original change for this repository.

- Source in this repository: `FEXCore/Source/Utils/ArchHelpers/Arm64.cpp`.
- License: MIT (FEX).
- Scope: Windows and macOS only. The write hooks are null on other hosts.
- Evidence: observed in the native ARM64 canary. Before the change the handler
  faults on its own back-patch store and the game exits with a native
  exception. After the change the handler completes, the block retries, and the
  game keeps running until the launch window timeout.
