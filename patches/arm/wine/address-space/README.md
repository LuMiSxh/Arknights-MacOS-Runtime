# ARM64 address space

Wine source patch for the native-arm64 target only.
There is no runtime flag: the target cannot start without it.
See the [address-space registry](../../../../docs/patch-registry.md#address-space).

macOS keeps the low 4 GB of an arm64 process as a hard pagezero.
`KUSER_SHARED_DATA` belongs at `0x7ffe0000` inside that range, and so does the first
TEB block.
A loader signed with `com.apple.developer.cross-architecture-support` may release the
range; a distributed runtime cannot use that entitlement, so it moves the page instead.

The patch does five things:

1. It exports `__wine_user_shared_data` from ntdll and points the PE consumers
   (`kernel32`, `kernelbase`, `win32u`) at it.
2. It moves the page to `MM_SHARED_USER_DATA_VA + 4 GB` when the canonical address
   cannot be mapped.
3. It probes upward from 4 GB for the first page that `mach_vm_map` accepts, because
   dyld reserves the main executable's Mach-O region there.
4. It lets the first 64-bit TEB block take an address above 4 GB and uses the probed
   floor for thread data, stacks, and image fallbacks.
5. It emulates ARM64 loads that fault on the canonical address from the moved page.

Apply `0001-ntdll-relocate-the-shared-user-data.patch` to the pinned `arm64-1117`
source after the shared families.
