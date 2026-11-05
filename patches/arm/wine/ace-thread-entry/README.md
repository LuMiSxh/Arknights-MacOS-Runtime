# Start a hybrid-module thread on its x64 export

An x64 process can start a thread on the native ARM64 export of an ARM64X module. The thread then
runs ARM64 code as x64 code and faults.

ACE injects `kernel32!LoadLibraryW` into the game with `CreateRemoteThread` and takes that path.
The patch resolves the same export through `GetProcAddress` from the loaded module and starts the
thread there. It changes `fixup_native_thread_entry` and `LdrInitializeThunk` in
`dlls/ntdll/signal_arm64ec.c`.

Apply it to the `native-arm64` target only.
