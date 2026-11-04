# Keep mixed host pages writable on arm64 macOS

macOS refuses `mprotect(PROT_READ | PROT_WRITE | PROT_EXEC)` without `MAP_JIT`.
A 16K host page can mix executable 4K pages with writable ones.
Wine then asks for RWX when it changes an image section.
The call fails, and `NtProtectVirtualMemory(PAGE_READWRITE)` returns
`STATUS_ACCESS_DENIED`.

On this lane a write fault on the mixed page was not delivered to the signal
handler, so dropping `PROT_WRITE` left the import address table read-only.
The patch drops `PROT_EXEC` instead.
The page stays writable, and `virtual_handle_fault` flips it for an execute
fault.

Apply time: after the address-space patch.
