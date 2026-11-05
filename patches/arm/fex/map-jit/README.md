# Map FEX code buffers with MAP_JIT

macOS refuses a mapping that is writable and executable without `MAP_JIT`.
FEX allocates the dispatcher and the shared code buffer with
`PAGE_EXECUTE_READWRITE`, so Wine maps them writable-only and the JIT cannot run.

The patch adds `JitAlloc`, `JitFree`, and `JitWriteProtect` to the Windows unix
library.
`JitAlloc` maps the buffer with `MAP_JIT` and keeps it `rwx`.
FEX calls `pthread_jit_write_protect_np(0)` before writing code and
`pthread_jit_write_protect_np(1)` before running it.

The hooks cover the dispatcher buffer, the shared code buffer, cached code, and
block delinking.
The patch is a no-op outside Windows; the unix library handlers return
`STATUS_NOT_SUPPORTED` on other hosts.

The x86_64 probe prints `fex-ok` with this patch.
