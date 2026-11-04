# Native ARM64 runtime

This directory holds the plan for a native ARM64 runtime lane.
The current lane runs an x86_64 Wine under Rosetta 2.
macOS 28 removes general Rosetta 2 support, so the current lane has a fixed lifetime.

## Decision

The project has no distributable signing identity.
An entitlement is only valid in a binary that embeds a provisioning profile for the same team and App ID.
The loader in the reference runtime carries the profile of its distributor.
This project cannot sign with that identity, and must not redistribute the file.

Apple publishes two cross-architecture entitlements:

| Entitlement                                                | Account                      |
| ---------------------------------------------------------- | ---------------------------- |
| `com.apple.developer.cross-architecture-support`           | Paid Apple Developer Program |
| `com.apple.developer.cross-architecture-support-unmanaged` | Free developer account       |

Both need your own App ID, a provisioning profile, and the provisioning UDID of your Mac.
The profile names one Mac, so the signed loader is device-bound and cannot ship to users.
Free accounts report no access to Certificates, Identifiers & Profiles to create that profile.
See [provenance](provenance.md#entitlement-availability).

Therefore the ARM64 lane must not depend on the entitlement.
The lane is 64-bit only and uses 16K host pages, which need no entitlement.

The primary plan is an entitlement-free WineCX ARM64 build with three ports:

1. WineCX `arm64-1117` (Wine 11.17, the current Wine version).
2. FEX for x86_64 emulation through ARM64EC.
3. DXMT ARM64EC for Direct3D 10 and 11.

A small patch family from MetalSharp-Wine relocates the shared user data page and handles write and execute protection.
The patches remove the dependency on the entitled loader.

The fallback plan is MetalSharp-Wine as the ARM64 base.
That project already runs without the entitlement, but it carries 129 Wine patches and needs a full rebase of this repository's patches.

See [porting](porting.md) for the patch set and [risks](risks.md) for the open questions.

## Scope

In scope:

- A native ARM64 build of WineCX and DXMT.
- x86_64 Windows programs run by FEX.
- The existing patch families, except the Rosetta-specific part of ACE.
- A second build and release target in this repository.
- The runtime interface that the client consumes.

Out of scope:

- i386 programs. They need the low 4 GB of address space and the entitlement.
- 4K host pages. They need the entitlement.
- Apple D3DMetal. It ships x86_64 only.
- Rosetta 2 in any form.
- A native version of the game.

## Status

| Item                             | State                               |
| -------------------------------- | ----------------------------------- |
| Reference ARM64 runtime captured | Complete                            |
| Public sources identified        | Complete                            |
| Lock target dimension            | Complete                            |
| Entitlement lane                 | Rejected, no distributable identity |
| Entitlement-free patch set       | Planned, not ported                 |
| ARM64 build target               | Not implemented                     |
| ARM64 canary artifact            | Not built                           |
| ACE under FEX                    | Not tested                          |
| Client ARM64 support             | Not implemented                     |

The x86_64 Rosetta lane stays the default until the ARM64 canary passes the compatibility checks.

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

1. [Provenance](provenance.md) records the reference runtime and the public sources.
2. [Architecture](architecture.md) explains the process model and the address space.
3. [Porting](porting.md) lists the patch family that removes the entitlement dependency.
4. [Pipeline](pipeline.md) describes the second build target.
5. [Client](client.md) lists the consumer changes and the local canary.
6. [Risks](risks.md) lists the open compatibility and maintenance risks.

## References

- Upstream sources: `dappermint/winecx`, `dappermint/FEX`, `3Shain/dxmt`.
- Entitlement-free reference: `metalsharp/MetalSharp-Wine`.
- Entitlement facts: the [Wine on ARM64 macOS](https://list.winehq.org/hyperkitty/list/wine-devel@list.winehq.org/thread/CKG5CEN2BE5VRXZ7O7NX4YUSBH3247WH/) announcement on Wine-devel, 2026-08-07.
- Free-account entitlement report: [Apple Developer Forums](https://developer.apple.com/forums/tags/provisioning-profiles), 2026-10.
- Current runtime contract: [`runtime.lock.json`](../../runtime.lock.json) and [`docs/architecture.md`](../architecture.md).
