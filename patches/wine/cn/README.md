# China client compatibility patches

This directory contains the Bilibili windowing compatibility family for the
`cn` and `combined` runtime stages. The canonical patch-by-patch description is
the [CN patch registry](../../../docs/patch-registry.md#cn).

The windowing patch uses only `ARKNIGHTS_RUNTIME_CN_COMPAT=1`; absent, `0`, or
any other value leaves the ordinary Wine route selected. The CEF loader
descriptor lives in the separate [`cef` family](../cef/README.md). The
ACE-protected client routes live in the separate [`ace` family](../ace/README.md).

Apply in this order:

1. `windowing/0001-win32u-winemac-bilibili-layered-child.patch`
