# Provenance

The two ACE patches in this export are ports of `metalsharp/MetalSharp-Wine`
(https://github.com/metalsharp/MetalSharp-Wine), Avery Felts.

- `patches/0001-ntdll-carry-eflags-af-df.patch` ports MetalSharp-Wine patch `0017`
  ("ntdll: Carry EFlags AF and DF through ARM64EC contexts"). Source in this
  repository: `dlls/ntdll/unwind.h`.
- `patches/0002-ntdll-hybrid-thread-entry.patch` ports MetalSharp-Wine patch `0126`
  ("ntdll: Start an x64 thread entered on a hybrid module's native export on its x64
  export"). Source in this repository: `dlls/ntdll/signal_arm64ec.c`.

License: LGPL-2.1-or-later (Wine).
