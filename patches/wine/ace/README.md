# ACE compact compatibility patches

This directory contains the ordered ACE compatibility family for the `ace` and
`combined` runtime stages. The canonical patch-by-patch description is the
[ACE patch registry](../../../docs/patch-registry.md#ace).

Compatibility-only routes in the four patches use `ARKNIGHTS_RUNTIME_ACE_COMPACT=1`; absent, `0`, or
any other value leaves those ordinary Wine routes selected. General process accessors preserve their
normal behavior regardless of the compatibility toggle. The control is read by each owning component
once, preserving the upstream behavior by default.

Apply in this order:

1. `ntoskrnl/0001-ntoskrnl-compatibility-surface.patch`
2. `dispatcher/0001-kernel32-ace-dispatcher-spoof.patch`
3. `rosetta/0001-macos-rosetta-ace-workarounds.patch`
4. `timing/0001-ntdll-ace-qpc-relative-wait.patch`

These routes are intended for the ACE-protected Hypergryph clients. They are
kept separate from the Bilibili renderer compatibility family so a future
publisher or client can select only the capabilities it needs.
