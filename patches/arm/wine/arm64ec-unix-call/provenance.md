# Provenance

Original change for this repository.

- Source: `dappermint/winecx`, branch `arm64-1117`, commit
  `c8ef4872c1d53120b80aa92185fc7e295d94d092`.
- Files: `dlls/ntdll/unixlib.h`, `dlls/ntdll/loader.c`,
  `dlls/ntdll/unix/loader.c`.
- License: LGPL-2.1-or-later (Wine).
- Cause: CodeWeavers hack 22434 and the `unixlib_entry_t` table are indexed
  across the PE and Unix boundary.
