# Provenance

Port of the `mprotect_exec` hunk in `metalsharp/MetalSharp-Wine` patch `0003`
("Run on arm64 macOS without low 4G remapping and with 16K pages"),
Avery Felts.

- Source in this repository: `dlls/ntdll/unix/virtual.c`.
- License: LGPL-2.1-or-later (Wine).
- Scope: arm64 macOS only. Other hosts keep the existing protection request.
- Deviation: the reference drops `PROT_WRITE`; this lane drops `PROT_EXEC`
  because write faults on the mixed page were not delivered to the signal
  handler.
