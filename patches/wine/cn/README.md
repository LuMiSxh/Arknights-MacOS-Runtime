# China client compatibility patches

This directory contains the Bilibili renderer compatibility family for the
`cn` and `combined` runtime stages. The canonical patch-by-patch description is
the [CN patch registry](../../../docs/patch-registry.md#cn).

Both patches use only `ARKNIGHTS_RUNTIME_CN_COMPAT=1`; absent, `0`, or any
other value leaves the ordinary Wine route selected. The ACE-protected client
routes live in the separate [`ace` family](../ace/README.md).

Apply in this order:

1. `cef/0001-ntdll-bilibili-cef-80-stackbase.patch`
2. `windowing/0001-win32u-winemac-bilibili-layered-child.patch`
