# Arknights macOS Runtime

**Patch-gated WineCX and DXMT builds for [Arknights Client](https://github.com/LuMiSxh/Arknights-MacOS-Client).**

This repository owns the exact WineCX, DXMT, dependency, and patch inputs of the runtime artifact. Each behavior-changing route has a safe default and a component-local control. The repository validates the archive contract and records provenance.

> [!NOTE]
> This repository is not a launcher or game distribution. It contains no Arknights game files.

## Reporting problems

Use the Runtime problem template in the [Arknights Client issue tracker](https://github.com/LuMiSxh/Arknights-MacOS-Client/issues/new?template=runtime-problem.yml). Include the client and runtime versions, Mac and macOS version, region, Wine-prefix history, runtime settings, and reproduction steps. Attach logs only on request.

## Baseline

- dappermint runtime <!-- pin:base.version -->4.7.3<!-- /pin --> with WineCX <!-- pin:wine.version -->11.19<!-- /pin -->.
- The Cursor, Performance, and combined stages build a pinned post-0.80 DXMT revision.
- The `hardware-cursor` stage overlays only the patched `x86_64-unix/ntdll.so`.
- The clean release tree contains newly built 64-bit Wine and DXMT (no GStreamer/FFmpeg) and the pinned Nix library closure.
- The MoltenVK library is not built from source. It comes from the third-party base archive, which a SHA-256 hash pins.
- The macOS host tools (Homebrew packages, Xcode, SDK) are not pinned. The release provenance records their versions. A rebuild can differ.
- Candidate baselines also record their Wine Gecko input.
- Commits or checksums pin all inputs.

## Patch families and runtime controls

Each component parses only its own variable. A missing or invalid value gives the default in the last column.

| Family          | Purpose                                                                                                                                  | Variable and accepted values                                | Default                                                    |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- | ---------------------------------------------------------- |
| Audio           | Follow the macOS default output without a game restart ([client issue #59](https://github.com/LuMiSxh/Arknights-MacOS-Client/issues/59)) | `ARKNIGHTS_RUNTIME_AUDIO_FOLLOW_DEFAULT_OUTPUT`: `0`, `1`   | Wine's normal routing                                      |
| Cursor          | Bound the DXMT frame queue for cursor latency ([client issue #34](https://github.com/LuMiSxh/Arknights-MacOS-Client/issues/34))          | `ARKNIGHTS_RUNTIME_DXMT_MAX_FRAME_LATENCY`: `0` through `3` | Upstream maximum `3`                                       |
| Hardware Cursor | Hide the cursor sprite asset so macOS shows the hardware pointer                                                                         | `ARKNIGHTS_RUNTIME_HARDWARE_CURSOR`: `0`, `1`               | Inactive                                                   |
| Performance     | Initialize DXMT command helpers safely; skip release-dead present statistics                                                             | None                                                        | Compile-time changes; statistics gate follows `DXMT_DEBUG` |
| ACE             | Opt-in kernel, dispatcher, Rosetta, and timing routes for ACE-protected clients                                                          | `ARKNIGHTS_RUNTIME_ACE_COMPACT`: `0`, `1`                   | Inactive                                                   |
| CEF             | Descriptor-driven CEF compatibility; proven Bilibili loader path                                                                         | `ARKNIGHTS_RUNTIME_CEF_COMPAT`: `0`, `1`                    | Inactive                                                   |
| CN              | Preflighted Bilibili layered-renderer path                                                                                               | `ARKNIGHTS_RUNTIME_CN_COMPAT`: `0`, `1`                     | Inactive                                                   |

The CN gate covers the Bilibili window preflights in the [patch registry](docs/patch-registry.md#cn) and, if CEF is absent, its legacy CEF fallback.

## Building

Requirements: macOS 15+, Xcode command-line tools, Git, uv, Just, Nix, `x86_64-darwin` support, Rosetta 2 on Apple Silicon, and Homebrew `mingw-w64`, Meson, and Ninja.

```sh
just build combined

# Focused hardware-cursor Wine build
just build hardware-cursor

# Clean release-gated build
just build-release
just verify .build/stages/combined/candidate/Libraries
```

Outputs stay below `.build/`. These commands never install or start Wine, create a prefix, launch a game, or modify an Arknights installation.

## Verification

Run `just check`. Then run `just prepare STAGE` for each of `audio`, `cursor`, `hardware-cursor`, `performance`, `ace`, `cef`, `cn`, and `combined`.

GitHub Actions validate the pinned sources, build the release tree, and create a draft release after the checksum, runtime-interface, provenance, source, and notice checks pass.

See [architecture](docs/architecture.md), [patch registry](docs/patch-registry.md), [redistribution inventory](docs/legal/redistribution.md), [testing](docs/testing.md), [release gates](docs/releasing.md), [updating pins](docs/updating-pins.md), and the pinned [runtime identity](runtime.lock.json).

## License

Original build tooling and documentation use the [Mozilla Public License 2.0](LICENSE). The modified Wine source in the Wine patches is subject to Wine's [LGPL-2.1-or-later terms](LICENSES/Wine-LGPL-2.1.txt).

The DXMT license is LGPL-2.1-or-later at the pinned commit <!-- pin:dxmt.short|code -->`e94c312`<!-- /pin -->. The `LICENSE` file of that commit states this license. DXMT release v0.80 and older releases use the MIT License. The text of the LGPL-2.1 license is in [`LICENSES/DXMT-LGPL-2.1.txt`](LICENSES/DXMT-LGPL-2.1.txt). The MIT text for the older releases is in [`LICENSES/runtime/MIT-DXMT.txt`](LICENSES/runtime/MIT-DXMT.txt). The source archive contains the DXMT source. Vendored code and the items with an unverified license are listed in [`LICENSES/notices/`](LICENSES/notices/).

The directory [`LICENSES/`](LICENSES/) holds the license texts and notices of all components in the runtime archive. The file [`LICENSES/index.json`](LICENSES/index.json) lists them. Run `uv run --locked scripts/release/licenses.py generate --check` to validate it. The clean build puts a copy at `Licenses/` and a `NOTICE.md` file at the root of the runtime archive. The `Libraries/` directory is unchanged.

The release does not yet offer the corresponding source of the Nix libraries. This item is open.
