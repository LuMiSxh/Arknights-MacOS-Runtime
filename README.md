<div align="center">

<img src="https://raw.githubusercontent.com/LuMiSxh/Arknights-MacOS-Client/main/Resources/AppIcon.png" width="112" height="112" alt="Arknights Client app icon" />

# Arknights macOS Runtime

**Patch-gated WineCX and DXMT builds for [Arknights Client](https://github.com/LuMiSxh/Arknights-MacOS-Client).**

[![Release](https://img.shields.io/github/v/release/LuMiSxh/Arknights-MacOS-Runtime?style=flat-square&labelColor=23252a&color=477acc)](https://github.com/LuMiSxh/Arknights-MacOS-Runtime/releases)
[![macOS 15+](https://img.shields.io/badge/macOS-15%2B-477acc?style=flat-square&labelColor=23252a)](#baseline)
[![Apple Silicon](https://img.shields.io/badge/Apple%20Silicon-required-477acc?style=flat-square&labelColor=23252a)](#baseline)
[![MPL-2.0 license](https://img.shields.io/badge/license-MPL--2.0-477acc?style=flat-square&labelColor=23252a)](LICENSE)

</div>

This repository owns the exact WineCX, DXMT, dependency, and patch inputs of the runtime artifact that [Arknights Client](https://github.com/LuMiSxh/Arknights-MacOS-Client) downloads. It builds the x86_64 runtime and republishes the external native ARM64 runtime.

> [!NOTE]
> This repository is not a launcher or game distribution. It contains no Arknights game files.

## Baseline

- The x86_64 lane uses dappermint runtime <!-- pin:base.version -->4.7.3<!-- /pin --> with WineCX <!-- pin:wine.version -->11.17<!-- /pin -->. One build applies every Wine patch (`0003`–`0015`) and the DXMT patch (`0001`).
- The clean x86_64 release tree contains newly built 64-bit Wine and DXMT (no GStreamer/FFmpeg) and the pinned Nix library closure.
- The x86_64 MoltenVK library comes from the third-party base archive, which a SHA-256 hash pins.
- The native ARM64 lane is external. It ships the `wine-11-18-arm64-v5` Wine tree from [wine-build-new](https://github.com/riverfog7/wine-build-new) and builds DXMT for ARM64EC. It requires macOS 26.0 or newer.
- Commits or checksums pin all inputs. The macOS host tools are not pinned; the release provenance records their versions.

## Patches and gates

Every patch has one gate, `LMISXH_AKMOCL_<NAME>`. A default-on gate is on when the variable is unset or exactly `1`; any other value turns it off. A default-off gate, including `LMISXH_AKMOCL_CN` and `LMISXH_AKMOCL_CURSOR`, needs exactly `1`.

The [Wine patch table](patches/wine/README.md) lists each patch, its gate, and its default. The [DXMT patch](patches/dxmt/README.md) uses `DXMT_DEBUG` at build time. The [patch registry](docs/patch-registry.md) records provenance, manual checks, and removal conditions.

## Build

Requirements: macOS 15+, Xcode command-line tools, Git, uv, Just, Nix, `x86_64-darwin` support, Rosetta 2 on Apple Silicon, and Homebrew `ccache`, `mingw-w64`, Meson, and Ninja.

```sh
just check
just prepare
just build
just verify
```

`just prepare` clones the pinned sources and applies every patch in lock order. `just build` creates the all-patches overlay canary. `just build-release` creates the clean release artifact. Outputs stay below `.build/`. These commands never install or start Wine, create a prefix, launch a game, or modify an Arknights installation.

### Native ARM64 lane

Requirements: macOS 26+, Homebrew `llvm@15`, Meson, Ninja, Bison, Flex, pkg-config, and a pinned llvm-mingw release.

```sh
just arm64-fetch
just arm64-dxmt
just arm64-assemble
just arm64-verify
```

The ARM64 Wine payload is built in [wine-build-new](https://github.com/riverfog7/wine-build-new). This repository builds DXMT for ARM64EC, repacks the external tree into the client contract, and validates the result. See the [native ARM64 lane](docs/arm/README.md) and the [patch export](wine-build-new/README.md).

## Reporting problems

Use the Runtime problem template in the [Arknights Client issue tracker](https://github.com/LuMiSxh/Arknights-MacOS-Client/issues/new?template=runtime-problem.yml). Include the client and runtime versions, Mac and macOS version, region, Wine-prefix history, runtime settings, and reproduction steps. Attach logs only on request.

## Documentation

- [Architecture](docs/architecture.md): build model and runtime flags.
- [Patch registry](docs/patch-registry.md): provenance, manual checks, and removal.
- [Testing](docs/testing.md): maintainer progression and hardware canary.
- [Releasing](docs/releasing.md): lanes, gates, and provenance.
- [Updating pins](docs/updating-pins.md): pin rules, known-bad pins, and the patch guard.
- [Redistribution](docs/legal/redistribution.md): component and license inventory.
- [Native ARM64 lane](docs/arm/README.md): external build, catalog, and provenance.
- [ARM64 patch export](wine-build-new/README.md): layout, gates, and canonical copies.

## License

Original build tooling and documentation use the [Mozilla Public License 2.0](LICENSE). The modified Wine source in the Wine patches is subject to Wine's [LGPL-2.1-or-later terms](LICENSES/Wine-LGPL-2.1.txt).

DXMT is LGPL-2.1-or-later at the pinned x86_64 commit <!-- pin:dxmt.commit|code -->`9839e55f98d4aca103957ee4132d6395a325a9ed`<!-- /pin --> and at the ARM64 commit `647b0020ba5764e5593b12407afd76964fa11e20`. DXMT release v0.80 and older releases use the MIT License. The texts are in [`LICENSES/DXMT-LGPL-2.1.txt`](LICENSES/DXMT-LGPL-2.1.txt) and [`LICENSES/runtime/MIT-DXMT.txt`](LICENSES/runtime/MIT-DXMT.txt).

[`LICENSES/`](LICENSES/) holds the license texts and notices of every component in the runtime archive. [`LICENSES/index.json`](LICENSES/index.json) lists them. Run `uv run --locked scripts/release/licenses.py generate --check` to validate it.

The release does not yet offer the corresponding source of the Nix libraries.
