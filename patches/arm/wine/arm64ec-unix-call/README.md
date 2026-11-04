# Keep the ARM64EC unix-call table in step

`libarm64ecfex.dll` is an ARM64EC module.
The ARM64EC compiler defines `__x86_64__`, so the PE side called CodeWeavers'
`unix_pe_module_loaded` hook.
The aarch64 `ntdll.so` table has no such entry.
The call read past the table and jumped into unrelated data.

Gate the hook, the enum entry, and both Unix tables on
`defined(__x86_64__) && !defined(__arm64ec__)`.
The x86_64 lane keeps the hook.
The ARM64 lane does not call it, and the enum stays in step with the table.

Apply time: after the address-space patch.
