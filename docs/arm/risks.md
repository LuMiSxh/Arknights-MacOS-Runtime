# ARM64 lane risks

Each risk has a mitigation and a decision point.

## Compatibility

### x86_64 programs under FEX

| Item       | Detail                                                                                                       |
| ---------- | ------------------------------------------------------------------------------------------------------------ |
| Risk       | The emulator does not reach the entry point.                                                                 |
| Impact     | The lane cannot run the game.                                                                                |
| Evidence   | A minimal AMD64 PE loads at `0x140000000` and stops before entry. The Wow64 values now name the FEX modules. |
| Mitigation | Port reference `0004`, `0017`, `0126`, and `0128`, then retest the minimal PE.                               |
| Decision   | If a minimal PE still hangs after those ports, stop the lane for the protected clients.                      |

### ACE under FEX

| Item       | Detail                                                                         |
| ---------- | ------------------------------------------------------------------------------ |
| Risk       | The anti-cheat rejects the emulator or a timing check.                         |
| Impact     | The lane cannot serve the Yostar Global, Japan, and Korea clients.             |
| Evidence   | None. The lane does not run a 64-bit program yet.                              |
| Mitigation | Test at login, in battle, and after a long session with TSO enabled.           |
| Decision   | If ACE fails, stop the lane for the protected clients. Evaluate CN separately. |

The shared ACE patches are in the ARM64 build.
The dispatcher and Rosetta parts are x86_64 only.
ACE may also reject the emulated CPU identity, the timing source, or the memory
layout.
A passing Wine start is not a passing ACE start.

### 32-bit helper processes

| Item       | Detail                                                                                     |
| ---------- | ------------------------------------------------------------------------------------------ |
| Risk       | The game or a launcher component starts a 32-bit process.                                  |
| Impact     | The process cannot start without the entitlement.                                          |
| Evidence   | Wine Mono's 32-bit helpers fail. The game is 64-bit; the CN launcher is not audited.       |
| Mitigation | Skip helpers the client does not need (the ARM64 lane skips Mono). Audit the CN launcher.  |
| Decision   | If a required component is 32-bit, the lane needs the entitlement or a 64-bit replacement. |

### 16K host pages

| Item       | Detail                                                                               |
| ---------- | ------------------------------------------------------------------------------------ |
| Risk       | A program assumes a 4K page size and fails on a 16K host page.                       |
| Impact     | Crashes in memory allocation, JIT code, or anti-cheat checks.                        |
| Evidence   | Arknights runs on Windows with 4K pages. The lane emulates 4K inside 16K host pages. |
| Mitigation | Keep the WineCX write and execute flips and test the game with ACE.                  |
| Decision   | If the emulation is not sufficient, the lane needs the entitlement for 4K pages.     |

## Performance

| Item       | Detail                                                                                  |
| ---------- | --------------------------------------------------------------------------------------- |
| Risk       | FEX translation may cost more than Rosetta translation.                                 |
| Impact     | A lower frame rate and a higher CPU load than the x86_64 lane are possible.             |
| Evidence   | None for this game. Measure both lanes with the same scene and settings.                |
| Mitigation | Tune FEX caches, TSO, and DXMT. Compare frame time, CPU time, and power draw.           |
| Decision   | Accept the lane if the frame rate stays within the agreed limit and the game is stable. |

Use the same Mac, macOS version, display, game settings, prefix state, scene, and
warm-up for both lanes.
Record one same-binary A/A run to measure variation.
Test with TSO enabled first.

## Platform

| Item       | Detail                                                                                      |
| ---------- | ------------------------------------------------------------------------------------------- |
| Risk       | Apple changes the ARM64 process layout or the fault behavior.                               |
| Impact     | The relocation and the 4 GB floor stop working.                                             |
| Evidence   | The lane depends on `PAGEZERO`, the Mach-O reservation above 4 GB, and `SIGSEGV` decoding.  |
| Mitigation | Validate on every macOS major version. Keep the entitlement-compatible branches available.  |
| Decision   | If a macOS release breaks the layout, evaluate the entitlement lane or the MetalSharp base. |

The x86_64 lane is blocked by the client on macOS 28 and later.
The ARM64 lane must work on macOS 27 and 28.

### Entitlement

| Item       | Detail                                                                                          |
| ---------- | ----------------------------------------------------------------------------------------------- |
| Risk       | A future macOS release requires the entitlement for 64-bit processes as well.                   |
| Impact     | The entitlement-free lane stops working.                                                        |
| Evidence   | Apple has not published such a requirement. Both entitlements need a per-team profile.          |
| Mitigation | Keep the entitlement-compatible branches from the ported patches. Never vendor a signed loader. |
| Decision   | Revisit only when Apple offers a path that a distributed artifact can use.                      |

A development profile is device-bound.
It remains a local canary option for i386 or 4K pages, not a distribution path.

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

| Item       | Detail                                                          |
| ---------- | --------------------------------------------------------------- |
| Risk       | A source pin moves or a download changes.                       |
| Impact     | The artifact is not reproducible.                               |
| Evidence   | The reference Wine catalog is hosted on a third-party CDN.      |
| Mitigation | Pin full commits and SHA-256 values. Build from GitHub sources. |
| Decision   | Reject any artifact whose sources are not in the lock.          |

The FEX and llvm-mingw pins are in the lock.
The LLVM 15 revision used by DXMT is pinned in the build recipe.

## Licensing

| Item       | Detail                                                                                |
| ---------- | ------------------------------------------------------------------------------------- |
| Risk       | A ported patch or a bundled binary has the wrong license.                             |
| Impact     | The release cannot distribute the artifact.                                           |
| Evidence   | MetalSharp repository material is AGPL-3.0. Its Wine changes are LGPL-2.1-or-later.   |
| Mitigation | Port only the Wine changes. Keep the author, the commit message, and the source link. |
| Decision   | Run the license generator before any release.                                         |

The reference loader is proprietary and re-signed.
Do not redistribute it.

## Open questions

1. Does FEX reach a 64-bit entry point after `0004`, `0017`, `0126`, and `0128`?
2. Does ACE initialize under FEX?
3. Does the game start a 32-bit process?
4. Does DXMT ARM64EC expose the same MetalFX and frame-limit behavior as x86_64?
5. Does the CN client need the CEF or layered-window paths on ARM64?
6. Does Apple open a cross-architecture path that a distributed artifact can use?

Answer questions 1 and 2 first.
They decide whether the lane is viable.
