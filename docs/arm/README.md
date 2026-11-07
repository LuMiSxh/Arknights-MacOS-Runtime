# Native ARM64 runtime

The ARM64 lane runs a native ARM64 Wine runtime on macOS 26.0 or newer. The x86_64 lane runs Wine under Rosetta 2 and remains the default.

## Build model

The ARM64 Wine runtime is built outside this repository in the [wine-build-new](https://github.com/riverfog7/wine-build-new) workspace. That workspace has the Developer ID signature and provisioning profile that this repository cannot obtain.

The **Draft ARM64 Release** workflow uses the newest ARM64 release in the external catalog by default. Pass a catalog release id to select a specific release. It builds DXMT for ARM64EC, repacks the client contract, validates the tree, and creates a draft release. [`runtime.lock.json`](../../runtime.lock.json) keeps the last verified baseline (`wine-11-18-arm64-v5`).

`native-arm64` is an external target. `scripts/runtime.py prepare --target native-arm64` refuses it. The lane receives no patches from this repository. The ARM64 patch export is in [`wine-build-new/`](../../wine-build-new/).

## Status

| Item                 | State                                                 |
| -------------------- | ----------------------------------------------------- |
| ARM64 release target | External; macOS 26.0 or newer                         |
| Wine payload         | Newest ARM64 catalog release; baseline `wine-11-18-arm64-v5` |
| DXMT                 | Built from `sources.dxmt` for ARM64EC in the workflow |
| Client ARM64 support | Implemented; the manual canary is pending             |
| ACE                  | Untested on the ARM64 lane                            |
| Window chrome        | The external loader keeps its signature               |

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
| WineCX      | The CodeWeavers Wine source that this repository builds for x86_64.            |
| xtajit64    | The Wine interface for an x86_64 emulator on ARM64.                            |

## Reading order

1. [Entitlements](entitlements.md): the entitlements and the window chrome.
2. [Provenance](provenance.md): the shipped artifact and the reference capture.
3. [Client](client.md): the consumer contract and the canary.
4. [Patch export](wine-build-new.md): the `wine-build-new` export.

## References

- External Wine artifact: [wine-build-new](https://github.com/riverfog7/wine-build-new).
- DXMT source: `3Shain/dxmt`.
- Runtime contract: [`runtime.lock.json`](../../runtime.lock.json) and
  [`docs/architecture.md`](../architecture.md).
