# Publish JIT buffers as ARM64EC code

Wine decides whether a continuation resumes native ARM64EC code or restarts
emulation from `PEB->EcCodeBitMap`.
FEX never marks its code buffers, so a continuation after a handled fault
restarts emulation at the host JIT address.
The guest then decodes translated code as x86 and the thread hangs.

The patch marks every code buffer as EC code when the unix library allocates it
and clears the bits when it is freed.
It covers the dispatcher buffer, the shared code buffer, and cached code.

The marking runs only when the platform provides the JIT allocator.
Other hosts keep the default classification.

Apply to the FEX source at the pinned commit, after `map-jit`.
