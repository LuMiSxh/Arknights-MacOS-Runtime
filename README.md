# Arknights macOS Runtime

**Patch-gated WineCX and DXMT builds for [Arknights Client](https://github.com/LuMiSxh/Arknights-MacOS-Client).**

This repository owns the exact WineCX, DXMT, dependency, and patch inputs of the runtime artifact. It builds the x86_64 runtime and republishes the external native ARM64 runtime. Each behavior-changing route has a safe default and a component-local control. The repository validates the archive contract and records provenance.

> [!NOTE]
> This repository is not a launcher or game distribution. It contains no Arknights game files.

## Reporting problems

Use the Runtime problem template in the [Arknights Client issue tracker](https://github.com/LuMiSxh/Arknights-MacOS-Client/issues/new?template=runtime-problem.yml). Include the client and runtime versions, Mac and macOS version, region, Wine-prefix history, runtime settings, and reproduction steps. Attach logs only on request.

## Baseline

- The x86_64 lane uses dappermint runtime <!-- pin:base.version -->4.7.3<!-- /pin --> with WineCX <!-- pin:wine.version -->11.17<!-- /pin -->.
- The Performance and combined stages build a pinned post-0.80 DXMT revision.
- The `hardware-cursor` stage overlays only the patched `x86_64-unix/ntdll.so`.
- The clean x86_64 release tree contains newly built 64-bit Wine and DXMT (no GStreamer/FFmpeg) and the pinned Nix library closure.
- The native ARM64 lane is an external target. It ships the `wine-11-18-arm64-v5` Wine tree from [wine-build-new](https://github.com/riverfog7/wine-build-new) and builds DXMT from `sources.dxmt` for ARM64EC.
- The ARM64 lane requires macOS 26.0 or newer.
- The x86_64 MoltenVK library is not built from source. It comes from the third-party base archive, which a SHA-256 hash pins.
- The macOS host tools (Homebrew packages, Xcode, SDK) are not pinned. The release provenance records their versions. A rebuild can differ.
- Candidate baselines also record their Wine Gecko input.
- Commits or checksums pin all inputs.

## Patch families and runtime controls

Each component parses only its own variable. A missing or invalid value gives the default in the last column.

| Family          | Purpose                                                                                                                                  | Variable and accepted values                    | Default                                                    |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- | ---------------------------------------------------------- |
| Audio           | Follow the macOS default output without a game restart ([client issue #59](https://github.com/LuMiSxh/Arknights-MacOS-Client/issues/59)) | `LMISXH_AKMOCL=1`, `LMISXH_AKMOCL_AUDIO=1`      | Wine's normal routing                                      |
| Hardware Cursor | Hide the cursor sprite asset so macOS shows the hardware pointer                                                                         | `LMISXH_AKMOCL=1`, `LMISXH_AKMOCL_CURSOR=1`     | Inactive                                                   |
| Performance     | Initialize DXMT command helpers safely; skip release-dead present statistics                                                             | None                                            | Compile-time changes; statistics gate follows `DXMT_DEBUG` |
| ACE             | Opt-in kernel, dispatcher, Rosetta, and timing routes for ACE-protected clients                                                          | `LMISXH_AKMOCL=1`                               | Inactive                                                   |
| CEF             | Descriptor-driven CEF compatibility; proven Bilibili loader path                                                                         | `LMISXH_AKMOCL=1`, `LMISXH_AKMOCL_CEF=1`        | Inactive                                                   |
| CN              | Preflighted Bilibili layered-renderer path                                                                                               | `LMISXH_AKMOCL=1`, `LMISXH_AKMOCL_CN=1`         | Inactive                                                   |
| Fullscreen      | Put a fullscreen game window into a macOS native fullscreen Space                                                                        | `LMISXH_AKMOCL=1`, `LMISXH_AKMOCL_FULLSCREEN=1` | Inactive                                                   |

The CN gate covers the Bilibili window preflights in the [patch registry](docs/patch-registry.md#cn) and, if CEF is absent, its legacy CEF fallback.

## Building

Requirements: macOS 15+, Xcode command-line tools, Git, uv, Just, Nix, `x86_64-darwin` support, Rosetta 2 on Apple Silicon, and Homebrew `ccache`, `mingw-w64`, Meson, and Ninja.

```sh
just build combined

# Focused hardware-cursor Wine build
just build hardware-cursor

# Clean release-gated build
just build-release
just verify .build/stages/combined/candidate/Libraries
```

Outputs stay below `.build/`. These commands never install or start Wine, create a prefix, launch a game, or modify an Arknights installation.

### Native ARM64 lane

Requirements: macOS 26+, Xcode command-line tools, Git, uv, Just, Homebrew `llvm@15`, Meson, Ninja, Bison, Flex, pkg-config, and a pinned llvm-mingw release.

```sh
# The catalog URL comes from ARM64_RUNTIME_CATALOG_URL
just arm64-fetch
just arm64-dxmt
just arm64-assemble
just arm64-verify
```

The ARM64 Wine payload is built in [wine-build-new](https://github.com/riverfog7/wine-build-new). This repository builds DXMT for ARM64EC, repacks the external tree into the client contract, and validates the result. The ARM64 lane receives no patches from this repository.

## Verification

Run `just check`. Then run `just prepare STAGE` for each of `audio`, `hardware-cursor`, `performance`, `ace`, `cef`, `cn`, `fullscreen`, and `combined`.

GitHub Actions validate the pinned sources, build the release tree, and create a draft release after the checksum, runtime-interface, provenance, source, and notice checks pass. The ARM64 release workflow also rejects a Mach-O with a `minos` above 26.0.

See [architecture](docs/architecture.md), [patch registry](docs/patch-registry.md), [redistribution inventory](docs/legal/redistribution.md), [testing](docs/testing.md), [release gates](docs/releasing.md), [updating pins](docs/updating-pins.md), the [native ARM64 lane](docs/arm/README.md), and the pinned [runtime identity](runtime.lock.json).

## License

Original build tooling and documentation use the [Mozilla Public License 2.0](LICENSE). The modified Wine source in the Wine patches is subject to Wine's [LGPL-2.1-or-later terms](LICENSES/Wine-LGPL-2.1.txt).

The DXMT license is LGPL-2.1-or-later at the pinned x86_64 commit <!-- pin:dxmt.short|code -->`9839e55`<!-- /pin --> and at the ARM64 commit `647b0020`. The `LICENSE` file of each commit states this license. DXMT release v0.80 and older releases use the MIT License. The text of the LGPL-2.1 license is in [`LICENSES/DXMT-LGPL-2.1.txt`](LICENSES/DXMT-LGPL-2.1.txt). The MIT text for the older releases is in [`LICENSES/runtime/MIT-DXMT.txt`](LICENSES/runtime/MIT-DXMT.txt). The source archive contains the DXMT source. Vendored code and the items with an unverified license are listed in [`LICENSES/notices/`](LICENSES/notices/).

The directory [`LICENSES/`](LICENSES/) holds the license texts and notices of all components in the runtime archive. The file [`LICENSES/index.json`](LICENSES/index.json) lists them. Run `uv run --locked scripts/release/licenses.py generate --check` to validate it. The clean build puts a copy at `Licenses/` and a `NOTICE.md` file at the root of the runtime archive. The `Libraries/` directory is unchanged.

The release does not yet offer the corresponding source of the Nix libraries. This item is open.
