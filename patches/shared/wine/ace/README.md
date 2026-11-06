# ACE compact compatibility patches

Ordered ACE family for the `ace` and `combined` stages. The gate is the `LMISXH_AKMOCL=1` master switch. See the [ACE patch registry](../../../docs/patch-registry.md#ace). General process accessors ignore the gate.

Apply in this order:

1. `ntoskrnl/0001-ntoskrnl-compatibility-surface.patch`
2. [`dispatcher/0001-kernel32-ace-dispatcher-spoof.patch`](../../../x86/wine/ace/dispatcher/0001-kernel32-ace-dispatcher-spoof.patch) (x86_64 only)
3. [`rosetta/0001-macos-rosetta-ace-workarounds.patch`](../../../x86/wine/ace/rosetta/0001-macos-rosetta-ace-workarounds.patch) (x86_64 only)
4. `timing/0001-ntdll-ace-qpc-relative-wait.patch`

The dispatcher and Rosetta patches depend on x86 machine code, so they live in `patches/x86`.
The kernel and timing patches apply to both targets.

The routes target the ACE-protected Hypergryph clients. They stay separate from the Bilibili renderer family.
