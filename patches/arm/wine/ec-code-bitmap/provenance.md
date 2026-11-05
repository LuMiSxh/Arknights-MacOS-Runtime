# Provenance

Original change for this repository.

- Source in this repository: `dlls/ntdll/unix/virtual.c`.
- License: LGPL-2.1-or-later (Wine).
- Scope: ARM64EC hosts. Other hosts never allocate the bitmap.
- Evidence: observed in the native ARM64 canary. Without the patch a handled
  unaligned atomic is re-entered as emulated code and the game hangs before it
  opens a window.
