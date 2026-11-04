# ACE compact compatibility patches

Ordered ACE family for the `ace` and `combined` stages. The gate is `ARKNIGHTS_RUNTIME_ACE_COMPACT=1`. See the [ACE patch registry](../../../docs/patch-registry.md#ace). General process accessors ignore the gate.

Apply in this order:

1. `ntoskrnl/0001-ntoskrnl-compatibility-surface.patch`
2. `dispatcher/0001-kernel32-ace-dispatcher-spoof.patch`
3. `rosetta/0001-macos-rosetta-ace-workarounds.patch`
4. `timing/0001-ntdll-ace-qpc-relative-wait.patch`

The routes target the ACE-protected Hypergryph clients. They stay separate from the Bilibili renderer family.
