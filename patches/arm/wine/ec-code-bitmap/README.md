# Map the ARM64EC code bitmap writable

`PEB->EcCodeBitMap` records which pages hold native ARM64EC code.
Wine maps it read-only and only makes the pages of a view writable when an
image publishes its ARM64EC ranges.

The emulator cannot publish its own JIT pages through that map, so its code
stays classified as emulated.
`NtContinue` then restarts emulation at a host address instead of resuming the
JIT natively.

The patch maps the bitmap writable up front.
Commit accounting is unchanged, because the pages stay demand-zero.

Apply to the pinned `arm64-1117` source after the shared families.
