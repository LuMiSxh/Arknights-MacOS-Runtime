# Native ARM64 runtime

The ARM64 lane runs a native ARM64 Wine runtime on macOS 26.0 or newer. The x86_64 lane runs Wine under Rosetta 2 and remains the default. The Wine payload is built outside this repository; this repository builds DXMT, repacks the client tree, validates it, and creates a draft release.

The x86_64 lane stays the default until the game passes the compatibility checks. ACE is untested on the ARM64 lane.

## Catalog and pin generation

The **Draft ARM64 Release** workflow reads the catalog URL from the repository secret `ARM64_RUNTIME_CATALOG_URL`. It selects the newest ARM64 release by default, or the release id passed to the manual dispatch.

- When the selected release matches the lock pin, the fetch enforces the locked SHA-256.
- When the selected release differs, the fetch downloads it, verifies the catalog SHA-256 and size, and writes the new release id and SHA-256 to [`runtime.lock.json`](../../runtime.lock.json). Downstream steps verify against the lock.
- A missing pinned release or a SHA-256 disagreement fails the fetch.

The catalog and archive URLs never appear in output, assets, or provenance.

The lock declares `native-arm64` with `buildMode: external`. `scripts/runtime.py prepare --target native-arm64` refuses the target.

## Shipped artifact

| Field         | Value                                                                  |
| ------------- | ---------------------------------------------------------------------- |
| Release       | `wine-11-18-arm64-v5`                                                  |
| SHA-256       | `3008b2d45cbe1653ebdd4a0704de790ecc5668a580a84b3db42140fd5c1af31b`     |
| Wine source   | Upstream Wine 11.18, commit `7b3fff76fa5178f6ce0141b2c776afa2a822f101` |
| Minimum macOS | 26.0                                                                   |
| Builder       | [wine-build-new](https://github.com/riverfog7/wine-build-new)          |

The artifact layout is:

```text
wine/                       # lowercase
  bin/wine -> wine.app/...
  bin/wineserver
  lib/wine/aarch64-unix/
  lib/wine/aarch64-windows/
  lib/wine/i386-windows/
  share/licenses/           # Wine ARM64EC, FEX, Mesa
```

`provenance.json` records the build commit, the resolved `runtimeLock`, and the validation report. It also records the selected catalog id, SHA-256, and size under `externalArtifact`.

The archive has no DXMT, no `winemetal.so`, no `wine64`, no `Arknights` link, and no `WINEPRELOADERAPPNAME`. Patches `0012` and `0013` provide `WINEPRELOADERAPPNAME` once the external build picks them up. `scripts/arm64/assemble.py` adds `Wine/bin/wine64`, `Wine/bin/Arknights`, the DXMT payload, and the WineMetal modules outside the signed `wine.app`.

## DXMT

The release workflow builds DXMT from `sources.dxmt` at commit `647b0020ba5764e5593b12407afd76964fa11e20` with `MACOSX_DEPLOYMENT_TARGET=26.0`. It also builds a minimal Wine tree from `sources.wine` for the import libraries. That build tree is a build dependency and is never shipped. The macOS driver `winemac.so` comes from the external tree. The old external `dxmt-experimental-v1` artifact is not used.

## Entitlements and window chrome

The `wine.app` loader is Developer ID signed by team `QNY65H4MK6`, identifier `com.riverfog7.wine`, with `com.apple.developer.cross-architecture-support` and a distribution profile. Adding files outside the bundle does not invalidate that signature. The wrapper keeps the loader byte-identical. Do not re-sign, relink, or replace the loader. Ad-hoc sign only wrapper-added unsigned files; the release workflow signs the locally built `winemetal.so`.

| Entitlement                                                | Effect                                                                 |
| ---------------------------------------------------------- | ---------------------------------------------------------------------- |
| `com.apple.developer.cross-architecture-support`           | Cross-architecture support. The loader can use the low 4 GB layout without relocating the shared page. |
| `com.apple.developer.cross-architecture-support-unmanaged` | The free-account variant of the same capability.                       |
| `com.apple.private.custom-x18-abi`                         | Custom `x18` ABI. The kernel keeps `x18` across exceptions.            |

Apple grants these entitlements only to approved signing identities. A profile binds one team, one App ID, and the Macs in the profile.

The window server selects the window design from the main executable's `LC_BUILD_VERSION`. The external loader keeps its signed build metadata. The current profile grants only the cross-architecture entitlement, so expect the legacy window chrome until it also carries `com.apple.private.custom-x18-abi`. In-process workarounds do not change the real frame: `UIDesignRequiresCompatibility=NO`, interposing `dyld_get_program_sdk_version`, and `_appearancePreferringSolarium` all leave the frame unchanged. The client has no chrome bridge. Do not add one.

## Patch export

The Arknights patches for the signed runtime live in [`wine-build-new/`](../../wine-build-new/). That export has its own layout, gate table, canonical copies, and workspace audit. Its [README](../../wine-build-new/README.md) and [provenance](../../wine-build-new/provenance.md) are the only copies. The export applies fourteen Wine patches and one paired FEX patch after the workspace's 72-patch queue.

## Consumer contract

The client pins the archive URL and SHA-256 in its `runtime.json`. It decodes the embedded `RUNTIME.json`, reads `features`, and treats a missing feature as `false`. It selects the lane from `architecture`; `nativeArm64` and `aceCompat` are gone.

## Reference capture and sources

The component set comes from a read-only capture of the Yaagl ZZZ launcher on 2026-11-04. The capture identifies the sources and the shape of a working runtime. It is not a build input.

| Item                          | Value                                        |
| ----------------------------- | -------------------------------------------- |
| Capture date                  | 2026-11-04                                   |
| Host                          | Apple M4, macOS 27.2                         |
| Application support directory | `~/Library/Application Support/Yaagl ZZZ OS` |
| Installed Wine                | Wine 11.18, native ARM64                     |
| Installed DXMT                | ARM64EC build from the upstream DXMT CI      |
| Reference release             | `wine-11-18-arm64-v2`, 122178776 bytes       |

| Component             | Repository                                      | Reference                                         | Notes                                       |
| --------------------- | ----------------------------------------------- | ------------------------------------------------- | ------------------------------------------- |
| Upstream Wine 11.18   | `https://gitlab.winehq.org/wine/wine`           | Commit `7b3fff76fa5178f6ce0141b2c776afa2a822f101` | Shipped Wine payload.                       |
| FEX 2610              | `https://github.com/FEX-Emu/FEX`                | Commit `14c92681f4d62cf84d901460e0358de09c8847a7` | Pinned in the ARM64 target.                 |
| DXMT                  | `https://github.com/3Shain/dxmt`                | Commit `647b0020ba5764e5593b12407afd76964fa11e20` | Built in the release workflow.              |
| Patch export          | `https://github.com/riverfog7/wine-build-new`   | Directory `patches/`                              | ARM64 changes that the external build uses. |
| Entitlement-free Wine | `https://github.com/metalsharp/MetalSharp-Wine` | Branch `main`                                     | Reference for the address-space work.       |

The reference loader carries `com.apple.developer.cross-architecture-support`; its signature belongs to the team that owns the profile and cannot be transplanted. Do not copy the reference loader into an artifact. The installed reference tree is patched and is not a build input.

## Limits and licenses

| Limit                              | Effect                                                              |
| ---------------------------------- | ------------------------------------------------------------------- |
| No public signed loader            | This repository cannot reproduce or redistribute the reference app. |
| The installed reference is patched | The reference tree is not a clean build.                            |
| The signed loader is external      | The workflow verifies the selected artifact and never re-signs it.  |

| Component                                  | License                                    |
| ------------------------------------------ | ------------------------------------------ |
| Wine and WineCX                            | LGPL-2.1-or-later                          |
| FEX                                        | MIT                                        |
| DXMT at the current pin                    | LGPL-2.1-or-later                          |
| MetalSharp Wine changes                    | LGPL-2.1-or-later, as stated by its README |
| MetalSharp build scripts and documentation | AGPL-3.0                                   |

Port only the Wine changes from MetalSharp-Wine and keep the original commit message and source link in each patch. Do not copy the build scripts, documentation, or packaging.
