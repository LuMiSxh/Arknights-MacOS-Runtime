# CEF compatibility patches

This directory contains the descriptor-driven CEF compatibility family for the
`cef` and `combined` runtime stages. The canonical patch description is the
[CEF patch registry](../../../docs/patch-registry.md#cef).

`ARKNIGHTS_RUNTIME_CEF_COMPAT=1` enables regional CEF descriptors. An absent,
`0`, or invalid value leaves the normal Wine loader route unchanged. For
backward compatibility, `ARKNIGHTS_RUNTIME_CN_COMPAT=1` enables the proven
Bilibili descriptor when `CEF_COMPAT` is absent. An explicit CEF value always
takes precedence over the legacy CN fallback.

The Bilibili descriptor remains isolated behind its exact module, RVA, and byte
preflights. Add future regional descriptors to the generic dispatcher only
after reverse-engineering evidence identifies their complete byte contract.

Apply in this order:

1. `0001-ntdll-cef-compatibility.patch`
