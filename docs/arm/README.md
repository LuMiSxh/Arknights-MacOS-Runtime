# Native ARM64 runtime

This directory holds the native ARM64 runtime lane.
The x86_64 lane runs Wine under Rosetta 2 and remains the default.

## Decision

The project has no distributable signing identity.
Both cross-architecture entitlements need a provisioning profile that names one
Mac, so a signed loader is device-bound and cannot ship.
The lane therefore uses the entitlement-free address-space work.

The lane is 64-bit only and uses 16K host pages.
i386 programs, 4K host pages, Apple D3DMetal, Rosetta 2, and a native game build
are out of scope.
See [results](results.md#entitlement) and
[provenance](provenance.md#entitlement-availability).

## Status

| Item                            | State                                      |
| ------------------------------- | ------------------------------------------ |
| ARM64 build target              | Works                                      |
| Native ARM64 `wine cmd /c ver`  | Works                                      |
| Shared user data and 4 GB floor | Ported                                     |
| Wow64 wiring to the FEX modules | Ported                                     |
| x86_64 program under FEX        | Loads, FEX initializes, x64 startup stalls |
| Game and ACE                    | Not started                                |
| Client ARM64 support            | Local app works; game is not playable      |
| SDK 12 window-chrome bridge     | Prototyped, not shipped                    |

The x86_64 lane stays the default until a 64-bit program runs under FEX and the
game passes the compatibility checks.
See [results](results.md) for the experiment log and the current blockers.

## Terms

| Term        | Meaning                                                                             |
| ----------- | ----------------------------------------------------------------------------------- |
| ARM64EC     | A Windows ABI that mixes native ARM64 code and emulated x86_64 code in one process. |
| Canary      | An internal build that is tested but not released.                                  |
| Entitlement | A signed permission in an Apple provisioning profile.                               |
| FEX         | A user-mode x86 and x86_64 emulator for ARM64.                                      |
| Lane        | One build and release target with its own pins and artifact.                        |
| PAGEZERO    | The low 4 GB reservation that macOS gives to a native ARM64 process.                |
| Target      | A named entry in `runtime.lock.json`.                                               |
| WineCX      | The CodeWeavers Wine source that this repository builds.                            |
| xtajit64    | The Wine interface for an x86_64 emulator on ARM64.                                 |

## Reading order

1. [Results](results.md): what was tried and where it failed.
2. [Provenance](provenance.md): the reference runtime and the public sources.
3. [Architecture](architecture.md): the process model and the address space.
4. [Porting](porting.md): the patch families and the remaining work.
5. [Pipeline](pipeline.md): the second build target.
6. [Client](client.md): the consumer changes and the local canary.
7. [Risks](risks.md): the open compatibility and maintenance risks.

## References

- Upstream sources: `dappermint/winecx`, `dappermint/FEX`, `3Shain/dxmt`.
- Entitlement-free reference: `metalsharp/MetalSharp-Wine`.
- Current runtime contract: [`runtime.lock.json`](../../runtime.lock.json) and
  [`docs/architecture.md`](../architecture.md).
