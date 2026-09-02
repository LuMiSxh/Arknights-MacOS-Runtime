# CN compatibility patches

This directory contains the CN compatibility patch family included by the `cn`
and `combined` runtime stages. Its behavior-changing routes are inactive by default.

The patches target the pinned `dappermint/winecx` source commit
`7dbc5b5322a6ef3fb04bdc643c64b188fd641149` (WineCX 11.16). Apply them in
lexicographic order:

1. `ntoskrnl/0001-ntoskrnl-compatibility-surface.patch`
2. `dispatcher/0001-kernel32-cn-dispatcher-spoof.patch`
3. `rosetta/0001-macos-rosetta-cn-workarounds.patch`
4. `timing/0001-ntdll-cn-qpc-relative-wait.patch`

Every new behavior is gated by the exact environment value
`ARKNIGHTS_RUNTIME_CN_COMPAT=1`, read once per process. An absent variable, `0`, or any
other value leaves the existing Wine path selected. The dispatcher workaround
is compiled only for the x86_64 Wine build that runs under Rosetta; it does not
invent an ARM `int3` equivalent. No patch guesses from process names.

The patch family deliberately excludes the historical `wintrust` change: it
only targeted `winex11.drv`/`winewayland.drv`, while the macOS driver is
`winemac.drv`, so carrying it would add an unrelated signature bypass without
addressing this runtime.

Validation performed against the pinned checkout:

```text
git apply --check patches/wine/cn/ntoskrnl/0001-ntoskrnl-compatibility-surface.patch
git apply --check patches/wine/cn/dispatcher/0001-kernel32-cn-dispatcher-spoof.patch
git apply --check patches/wine/cn/rosetta/0001-macos-rosetta-cn-workarounds.patch
git apply --check patches/wine/cn/timing/0001-ntdll-cn-qpc-relative-wait.patch
```

Validate the patches with a clean macOS build and isolated execution checks for
both the inactive and enabled routes.
