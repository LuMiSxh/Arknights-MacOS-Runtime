# x86_64 patches

This directory holds patches that apply only to the `rosetta-x86_64` target.
Shared patches are in `../shared/`, and ARM64-only patches are in `../arm/`.

## ACE family

The x86_64 ACE routes are the [dispatcher spoof](wine/ace/dispatcher/0001-kernel32-ace-dispatcher-spoof.patch)
and the [Rosetta workarounds](wine/ace/rosetta/0001-macos-rosetta-ace-workarounds.patch).
Both belong to the [ACE family](../../shared/wine/ace/README.md) and use the same
`ARKNIGHTS_RUNTIME_ACE_COMPACT=1` gate.
The kernel and timing routes are shared.

Apply the family in the order of the family README:

1. `wine/ace/dispatcher/0001-kernel32-ace-dispatcher-spoof.patch`
2. `wine/ace/rosetta/0001-macos-rosetta-ace-workarounds.patch`

The dispatcher stub is `int3` machine code, so it cannot compile for ARM64EC.
The Rosetta patch changes `signal_x86_64.c`.
