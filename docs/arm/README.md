# Native ARM64 runtime

This directory covers the native ARM64 lane. The x86_64 lane runs Wine under Rosetta 2 and remains
the default.

## Decision

The project has no distributable signing identity. The two restricted entitlements need an Apple
approved signing identity, so the current ad-hoc build cannot use them. The lane uses the
entitlement-free address-space work instead. See [entitlements](entitlements.md) for the two
entitlements and the workarounds they can remove.

The lane is 64-bit only and uses 16K host pages. i386, 4K host pages, Apple D3DMetal, Rosetta 2, and a
native game build are out of scope. See [provenance](provenance.md#entitlement-availability) for the
entitlement details.

## Status

| Item                            | State                                                                   |
| ------------------------------- | ----------------------------------------------------------------------- |
| ARM64 build target              | Works                                                                   |
| Native ARM64 `wine cmd /c ver`  | Works                                                                   |
| Shared user data and 4 GB floor | Ported                                                                  |
| Wow64 wiring to the FEX modules | Ported                                                                  |
| x86_64 program under FEX        | Runs; the probe prints `fex-ok`                                         |
| ACE                             | Untested; the ARM patches are ported and the compact gate is active     |
| Game                            | Opens; Global login works                                               |
| Client ARM64 support            | Local app works; the game opens                                         |
| Dock and menu-bar name          | Baked into the loader as `Arknights`                                    |
| Window chrome                   | Legacy; the custom x18 ABI entitlement should select the current design |

The x86_64 lane stays the default until the game passes the compatibility checks.

## Terms

| Term        | Meaning                                                                        |
| ----------- | ------------------------------------------------------------------------------ |
| ARM64EC     | A Windows ABI that mixes native ARM64 and emulated x86_64 code in one process. |
| Canary      | An internal build that is tested but not released.                             |
| Entitlement | A signed permission in an Apple provisioning profile.                          |
| FEX         | A user-mode x86 and x86_64 emulator for ARM64.                                 |
| Lane        | One build and release target with its own pins and artifact.                   |
| PAGEZERO    | The low 4 GB reservation that macOS gives to a native ARM64 process.           |
| Target      | A named entry in `runtime.lock.json`.                                          |
| WineCX      | The CodeWeavers Wine source that this repository builds.                       |
| xtajit64    | The Wine interface for an x86_64 emulator on ARM64.                            |

## Reading order

1. [Architecture](architecture.md): the process model and the address space.
2. [Porting](porting.md): the patch families and the remaining work.
3. [Entitlements](entitlements.md): the removable workarounds and the window chrome.
4. [Provenance](provenance.md): the reference runtime and its public sources.
5. [Pipeline](pipeline.md): the second build target.
6. [Client](client.md): the consumer changes and the local canary.

## References

- Upstream sources: `dappermint/winecx`, `dappermint/FEX`, `3Shain/dxmt`.
- Entitlement-free reference: `metalsharp/MetalSharp-Wine`.
- Runtime contract: [`runtime.lock.json`](../../runtime.lock.json) and
  [`docs/architecture.md`](../architecture.md).
