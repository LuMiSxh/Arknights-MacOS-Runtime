# Arknights macOS Runtime

**Reproducible, patch-gated WineCX and DXMT builds for [Arknights Client](https://github.com/LuMiSxh/Arknights-MacOS-Client).**

## Overview

Arknights macOS Runtime owns the exact WineCX, DXMT, dependency, and patch inputs used to build a
runtime artifact. The artifact contains the Audio, Cursor, and CN patch families; every
behavior-changing route retains a safe default and a documented component-local control. The
repository validates the archive contract and records enough provenance to reproduce the artifact.

> [!NOTE]
> This is a runtime build repository, not a launcher or game distribution. It does not contain
> Arknights game files.

## Reporting problems

Report runtime problems in the
[Arknights Client issue tracker](https://github.com/LuMiSxh/Arknights-MacOS-Client/issues/new?template=runtime-problem.yml).
Use the Runtime problem template and include the client and runtime versions, Mac and macOS, selected
region, Wine-prefix history, runtime settings, and reproduction steps. Attach logs only when a
maintainer requests a specific file.

The current baseline is dappermint runtime 4.6.4 with WineCX 11.16. Cursor and combined stages
additionally build a pinned post-0.80 DXMT revision. The clean release tree contains newly built Wine
and DXMT, the pinned Nix media/library closure, and the pinned MoltenVK payload. Candidate baselines
also record their Wine Gecko input. All repository-controlled source, archive, recipe, and patch
inputs are pinned by commit and/or checksum.

## Patch families

| Family | Purpose                                                                                                                                               | Runtime default                                       |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| Audio  | Follow the current macOS default output without restarting the game ([client issue #59](https://github.com/LuMiSxh/Arknights-MacOS-Client/issues/59)) | Wine's normal routing unless enabled                  |
| Cursor | Provide a bounded DXMT frame queue control for cursor latency ([client issue #34](https://github.com/LuMiSxh/Arknights-MacOS-Client/issues/34))       | Upstream maximum `3`; values `1` through `3` accepted |
| CN     | Provide selected Wine/ACE compatibility routes                                                                                                        | Inactive unless explicitly enabled                    |

The complete artifact contains all three families. Missing or invalid control values preserve the
defaults listed above.

## Runtime controls

| Variable                                        | Accepted values | Missing or invalid value |
| ----------------------------------------------- | --------------- | ------------------------ |
| `ARKNIGHTS_RUNTIME_AUDIO_FOLLOW_DEFAULT_OUTPUT` | `0`, `1`        | Wine's normal routing    |
| `ARKNIGHTS_RUNTIME_DXMT_MAX_FRAME_LATENCY`      | `1` through `3` | Upstream value `3`       |
| `ARKNIGHTS_RUNTIME_CN_COMPAT`                   | `0`, `1`        | Inactive                 |

Each component parses only its own allowlisted value. The runtime has no cross-component master switch
and no process-name or path-based activation.

## Building

Local builds require macOS 15+, Xcode command-line tools, Git, uv, Just, Nix,
`x86_64-darwin` support, Rosetta 2 on Apple Silicon, and the Homebrew `mingw-w64`, Meson, and Ninja
toolchains.

```sh
just check
just prepare combined
just build combined

# Clean release-gated build
just build-release
just verify .build/stages/combined/candidate/Libraries
```

Generated sources, downloads, reports, and artifacts stay below `.build/`. Build and verification
commands never install or start Wine, create a prefix, launch a game, or modify an Arknights
installation.

## Verification

```sh
just check
just prepare audio
just prepare cursor
just prepare cn
just prepare combined
```

GitHub Actions validate the pinned sources, build the release tree, and create a draft release after
the checksum, runtime-interface, provenance, source, and notice checks pass.

See:

- [Architecture and repository boundary](docs/architecture.md)
- [Patch registry and provenance](docs/patch-registry.md)
- [Runtime redistribution inventory](docs/legal/redistribution.md)
- [Patch-by-patch test progression](docs/testing.md)
- [Release and rollback gates](docs/releasing.md)
- [Pinned runtime identity](runtime.lock.json)

## License

Original build tooling and documentation in this repository are licensed under the
[Mozilla Public License 2.0](LICENSE). The modified Wine source represented by the Wine patches is
subject to Wine's [LGPL-2.1-or-later terms](LICENSES/Wine-LGPL-2.1.txt), and the modified DXMT source
represented by the DXMT patch is subject to the pinned revision's
[LGPL-2.1-or-later terms](LICENSES/DXMT-LGPL-2.1.txt). These license files and the family-level
provenance records are inputs to a redistribution review; they do not by themselves claim that a
complete corresponding-source or notice package is already published for a runtime binary.
