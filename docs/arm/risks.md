# ARM64 lane risks

This document lists the risks of the entitlement-free ARM64 lane.
Each risk has a mitigation and a decision point.

## Compatibility

### ACE under FEX

| Item       | Detail                                                                                                              |
| ---------- | ------------------------------------------------------------------------------------------------------------------- |
| Risk       | The anti-cheat rejects the emulator or a timing check.                                                              |
| Impact     | The lane cannot serve the Yostar Global, Japan, and Korea clients.                                                  |
| Evidence   | None. The stack was not tested with ACE.                                                                            |
| Mitigation | Test the game with the MetalSharp-Wine archive before the port. Test at login, in battle, and after a long session. |
| Decision   | If ACE fails, stop the lane for the protected clients. Evaluate the CN client separately.                           |

The current ACE patch family has four parts.
The kernel, dispatcher, and timing parts are portable.
The Rosetta part changes `signal_x86_64.c` and does nothing on ARM64.
ACE may also reject the emulated CPU identity, the timing source, or the memory layout.
Do not assume that a passing Wine start means a passing ACE start.

### 32-bit helper processes

| Item       | Detail                                                                                       |
| ---------- | -------------------------------------------------------------------------------------------- |
| Risk       | The game or a launcher component starts a 32-bit process.                                    |
| Impact     | The process cannot start without the entitlement.                                            |
| Evidence   | The current game build is 64-bit. The CN launcher components are not audited.                |
| Mitigation | List the processes of a running session on the x86_64 lane. Test each one on the ARM64 lane. |
| Decision   | If a required component is 32-bit, the lane needs the entitlement or a 64-bit replacement.   |

### 16K host pages

| Item       | Detail                                                                                                 |
| ---------- | ------------------------------------------------------------------------------------------------------ |
| Risk       | A program assumes a 4K page size and fails on a 16K host page.                                         |
| Impact     | Crashes in memory allocation, JIT code, or anti-cheat checks.                                          |
| Evidence   | Arknights runs on Windows with 4K pages. The ARM64 lane emulates 4K granularity inside 16K host pages. |
| Mitigation | Port the exact write protection patches. Test with the game and with ACE.                              |
| Decision   | If the emulation is not sufficient, the lane needs the entitlement for 4K pages.                       |

## Performance

| Item       | Detail                                                                                    |
| ---------- | ----------------------------------------------------------------------------------------- |
| Risk       | FEX translation may cost more than Rosetta translation.                                   |
| Impact     | A lower frame rate and a higher CPU load than the x86_64 lane are possible.               |
| Evidence   | None for this game. Measure both lanes with the same scene and settings.                  |
| Mitigation | Tune FEX caches, TSO, and DXMT. Compare the frame time, the CPU time, and the power draw. |
| Decision   | Accept the lane if the frame rate stays within the agreed limit and the game is stable.   |

The comparison must use the same Mac, macOS version, display, game settings, prefix state, scene, and warm-up.
Record at least one same-binary A/A run to measure variation.

TSO emulation is a correctness feature with a performance cost.
Test with TSO enabled first. Disable it only after ACE and the game pass.

## Platform

| Item       | Detail                                                                                       |
| ---------- | -------------------------------------------------------------------------------------------- |
| Risk       | Apple changes the ARM64 process layout or the fault behavior.                                |
| Impact     | The relocation and the fault handler stop working.                                           |
| Evidence   | The lane depends on `PAGEZERO`, `mach_vm_region`, and `SIGSEGV` decoding.                    |
| Mitigation | Validate on every macOS major version. Keep the entitlement-compatible path from patch 0018. |
| Decision   | If a macOS release breaks the layout, evaluate the entitlement lane or the MetalSharp base.  |

The current x86_64 lane is blocked by the client on macOS 28 and later.
The ARM64 lane must work on macOS 27 and 28.

## Maintenance

| Item       | Detail                                                                               |
| ---------- | ------------------------------------------------------------------------------------ |
| Risk       | The ported patches conflict with each WineCX update.                                 |
| Impact     | Each runtime update needs manual work.                                               |
| Evidence   | The reference patches are written against Wine 11.20. The baseline is Wine 11.17.    |
| Mitigation | Keep each port as one small patch with a test. Group them by contract. Rebase early. |
| Decision   | If the port becomes larger than the WineCX update, move to the MetalSharp base.      |

Do not copy the MetalSharp application, packaging, or tracing code.
Keep the Wine changes separate from the AGPL-3.0 repository material.

## Supply chain

| Item       | Detail                                                                                                              |
| ---------- | ------------------------------------------------------------------------------------------------------------------- |
| Risk       | A source pin moves or a download changes.                                                                           |
| Impact     | The artifact is not reproducible.                                                                                   |
| Evidence   | The reference Wine catalog is hosted on a third-party CDN.                                                          |
| Mitigation | Pin full commits and SHA-256 values. Build from GitHub sources. Never treat the reference archive as a build input. |
| Decision   | Reject any artifact whose sources are not in the lock.                                                              |

The FEX build is not yet in the repository.
Pin the FEX commit and the llvm-mingw archive before the first build.
Record the LLVM 15 source revision for DXMT.

## Licensing

| Item       | Detail                                                                                                                      |
| ---------- | --------------------------------------------------------------------------------------------------------------------------- |
| Risk       | A ported patch or a bundled binary has the wrong license.                                                                   |
| Impact     | The release cannot distribute the artifact.                                                                                 |
| Evidence   | MetalSharp repository material is AGPL-3.0. Its Wine changes are LGPL-2.1-or-later.                                         |
| Mitigation | Port only the Wine changes. Keep the author, the commit message, and the source link. Do not copy scripts or documentation. |
| Decision   | Run the license generator before any release.                                                                               |

The reference loader is proprietary and re-signed.
Do not redistribute it.

## Open questions

1. Does ACE initialize under FEX?
2. Does the game start any 32-bit process?
3. Does the game use a timing pattern that FEX changes?
4. Does DXMT ARM64EC expose the same MetalFX and frame limit behavior as the x86_64 build?
5. Does the CN client need the CEF or layered window paths on ARM64?
6. Does WineCX 11.17 accept the ported address space patches without a broad rebase?
7. Does the MetalSharp FEX fork differ from `dappermint/FEX` in a way that matters for this game?

Answer question 1 and question 2 first.
They decide whether the lane is viable at all.
