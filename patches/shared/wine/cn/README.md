# China client compatibility patches

Bilibili windowing family for the `cn` and `combined` stages. The gate is the master switch plus `LMISXH_AKMOCL_CN=1`. See the [CN patch registry](../../../docs/patch-registry.md#cn). The CEF descriptor is in the [`cef` family](../cef/README.md). The ACE routes are in the [`ace` family](../ace/README.md).

Apply in order:

1. `windowing/0001-win32u-winemac-bilibili-layered-child.patch`
2. `windowing/0002-winemac-bilibili-join-all-spaces.patch`
