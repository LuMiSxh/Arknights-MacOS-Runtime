# CEF compatibility patches

Descriptor-driven CEF family for the `cef` and `combined` stages. See the [CEF patch registry](../../../docs/patch-registry.md#cef).

`ARKNIGHTS_RUNTIME_CEF_COMPAT=1` enables regional CEF descriptors. When `CEF_COMPAT` is absent, `ARKNIGHTS_RUNTIME_CN_COMPAT=1` enables the proven Bilibili descriptor. An explicit CEF value always takes precedence. Add a descriptor only after reverse-engineering evidence identifies its complete byte contract.

Apply: `0001-ntdll-cef-compatibility.patch`
