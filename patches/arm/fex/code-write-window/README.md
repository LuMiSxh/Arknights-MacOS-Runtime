# Open a code write window around unaligned atomic handling

FEX emulates an unaligned `lock`-prefixed access by back-patching the JIT block.
It rewrites the instruction words and locks the block tail spin lock in place.
On macOS the code buffers are mapped with `MAP_JIT`, so they are write-protected
while guest code runs.
The first back-patch store then faults inside the handler and FEX passes that
fault to Windows as a native exception.

The patch opens the existing code write window for the whole JIT path of
`HandleUnalignedAccess`.
`CodeWriteProtectHook` and `CodeWriteFlushHook` are null on hosts without
write-xor-execute, so other hosts are unchanged.

The patch also documents that a null address means the whole code space, because
the handler patches both code and block metadata.

Apply to the FEX source at the pinned commit, after `map-jit`.
