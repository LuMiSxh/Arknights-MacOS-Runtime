# Commit the FEX lookup cache eagerly

FEX reserves the lookup cache with `VirtualAlloc(TotalCacheSize, false, false)`.
On Windows that leaves the region reserved and uncommitted.
FEX expects to commit a page from its `ResetToConsistentState` callback when the
guest faults on it.

Under Wine the fault returns `STATUS_ACCESS_VIOLATION` and the callback never
runs.
The first block lookup then faults on the same instruction forever.

The patch passes `Commit=true` for that allocation.
`FEXCore::Allocator::VirtualAlloc` ignores the flag outside Windows, so other
hosts are unchanged.

The region is 256 MB of reserved address space with lazy physical pages, so the
commit costs no resident memory.

Apply to the FEX source at the pinned commit.
