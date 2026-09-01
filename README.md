# Arknights MacOS Runtime

**Reproducible, patch-gated WineCX and DXMT builds for [Arknights MacOS Client](https://github.com/LuMiSxh/Arknights-MacOS-Client).**

## Overview

Arknights MacOS Runtime owns the exact WineCX, DXMT, dependency, and patch inputs used to evaluate a
launcher runtime. It builds isolated canaries, validates the archive contract expected by the client,
and records enough provenance to reproduce or reject a candidate.

The project is pre-release. Current artifacts are engineering canaries, not supported downloads. They
must not replace the launcher's pinned runtime until the structural, licensing, and real-game promotion
gates pass.

The current canary baseline is dappermint runtime 4.6.4 with WineCX 11.16, intentionally newer than
the runtime bundled by the current client. Cursor and combined stages additionally build a pinned
post-0.80 DXMT revision. The base retains its released MoltenVK 1.4.2 and GStreamer 1.26.3 stack;
the build keeps the recipe's Darwin-capable Nix pin until a newer pin passes a separate canary.
Every input remains pinned by commit and checksum.

## Patch families

| Family | Purpose                                                                                                                                               | Default                  |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------ |
| Audio  | Follow the current macOS default output without restarting the game ([client issue #59](https://github.com/LuMiSxh/Arknights-MacOS-Client/issues/59)) | Disabled                 |
| Cursor | Experiment with a bounded DXMT frame queue for cursor latency ([client issue #34](https://github.com/LuMiSxh/Arknights-MacOS-Client/issues/34))       | Upstream value `3`       |
| CN     | Compile selected Wine/ACE compatibility work for isolated future research                                                                             | Disabled and unvalidated |

Arknights MacOS Client supports Yostar's Global, Japan, and Korea PC clients. Compiling the CN family
does not make CN supported or account-safe, and the v0.5 launcher must never activate it.

## Runtime controls

| Variable                                        | Accepted values | Missing or invalid value |
| ----------------------------------------------- | --------------- | ------------------------ |
| `ARKNIGHTS_RUNTIME_AUDIO_FOLLOW_DEFAULT_OUTPUT` | `0`, `1`        | Wine's normal routing    |
| `ARKNIGHTS_RUNTIME_DXMT_MAX_FRAME_LATENCY`      | `1` through `3` | Upstream value `3`       |
| `ARKNIGHTS_RUNTIME_CN_COMPAT`                   | `0`, `1`        | Inactive                 |

Each component parses only its own allowlisted value. There is no master switch and no process-name or
path-based activation.

## Building

Local builds require macOS 15+, Xcode command-line tools, Git, uv, Just, Nix,
`x86_64-darwin` support, Rosetta 2 on Apple Silicon, and the Homebrew `mingw-w64`, Meson, and Ninja
toolchains.

```sh
just check
just prepare combined
just build combined
just verify .build/stages/combined/candidate/Libraries
```

Generated sources, downloads, reports, and artifacts stay below `.build/`. Build and verification
commands never install or start Wine, create a prefix, launch a game, or modify an Arknights
installation.

The first candidate lane overlays only rebuilt patched modules onto the verified current runtime. It
is intentionally fast enough for hardware testing, but remains `releaseEligible: false` while
unchanged upstream binaries declare a macOS 26 minimum. A release requires a clean build of every
component for the documented macOS 15 target.

## Verification

```sh
just check
just prepare audio
just prepare cursor
just prepare cn
just prepare combined
```

GitHub Actions repeat the source checks and can build short-lived private candidate artifacts.
Promotion additionally requires complete corresponding source and notices, a relocatable Mach-O
closure, both DXMT payload architectures, immutable checksums, and a manual supported-region game
canary.

See:

- [Architecture and repository boundary](docs/architecture.md)
- [Patch registry and provenance](docs/patch-registry.md)
- [Patch-by-patch test progression](docs/testing.md)
- [Release and rollback gates](docs/releasing.md)

## License

Original build tooling and documentation are licensed under the
[Mozilla Public License 2.0](LICENSE). Wine-derived patches retain
[LGPL-2.1-or-later](LICENSES/Wine-LGPL-2.1.txt). The pinned post-0.80 DXMT revision and its patch retain
[LGPL-2.1-or-later](LICENSES/DXMT-LGPL-2.1.txt). Individual patch provenance is recorded beside each family.
