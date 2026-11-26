# Runtime archive and delta format

This document is the contract between this repository and the client.
The client pins one full archive per lane and, optionally, deltas from older releases.

## Assets

The release tag carries the version, so asset names do not repeat it.
Each release `v<to>` publishes these assets per architecture (`x86_64` or `arm64`):

| Asset | Content |
|---|---|
| `runtime-<arch>.tar.xz` | Full runtime archive (archive schema 3). |
| `runtime-<arch>.json` | Runtime manifest (manifest schema 1). |
| `runtime-<arch>-from-<from>.delta.tar.xz` | Delta from release `<from>` to `<to>` (delta schema 1). `<from>` is a bare version, for example `1.0.1`. |
| `source-<arch>.tar.xz` | Corresponding source archive. |
| `inventory-<arch>.tsv` | Runtime component inventory. |

Each release also publishes `provenance.json`, `THIRD-PARTY-NOTICES.txt` and `SHA256SUMS`.
`SHA256SUMS` lists every other asset as `<64 lowercase hex>  <asset name>\n`, sorted by name, so `shasum -a 256 -c SHA256SUMS` verifies a download.

Releases before archive schema 3 use the older names `Arknights-MacOS-Runtime-v<version>-<arch>.tar.gz` with `.sha256` sidecars.
Only the delta builder still reads them, as delta sources.

## Runtime manifest (manifest schema 1)

`runtime-<arch>.json` is the one file the client needs to pin a lane.
The `deltas` job writes it after the deltas exist, so it lists exactly the deltas that the release carries.
The release tag and `name` give the download URL: `https://github.com/LuMiSxh/Arknights-MacOS-Runtime/releases/download/v<version>/<name>`.

```json
{
  "schemaVersion": 1,
  "arch": "arm64",
  "version": "1.0.2",
  "minimumMacOS": "26.5",
  "archive": { "name": "runtime-arm64.tar.xz", "sha256": "…", "sizeBytes": 241874082 },
  "deltas": [
    { "from": "1.0.1", "name": "runtime-arm64-from-1.0.1.delta.tar.xz", "sha256": "…", "sizeBytes": 1234567 }
  ],
  "interface": { "…": "the lane interface of runtime.lock.json, verbatim" },
  "components": { "wine": "11.18", "dxmt": "0.80" },
  "provenance": {
    "buildRepository": "https://github.com/LuMiSxh/Arknights-MacOS-Runtime",
    "buildCommit": "…",
    "externalBuildRepository": "https://github.com/riverfog7/wine-build-new",
    "externalBuildCommit": "…",
    "wineRepository": "…",
    "wineCommit": "…",
    "dxmtRepository": "…",
    "dxmtCommit": "…"
  }
}
```

- `version` is the bare version of the release. `arch` is `x86_64` or `arm64`.
- `archive` and `deltas[]` give the asset name, the SHA-256 and the size in bytes. `deltas` is empty when the release has none.
- `interface` has the same shape as the lane `interface` in `runtime.lock.json`. Its paths are relative to the installed root.
- `components` maps `wine` and `dxmt` to their version strings. It has no `moltenvk`, because the lock does not record a MoltenVK version.
- `provenance` has flat string keys. `external*` keys exist only for the `arm64` lane.
  The `x86_64` lane adds `moltenvk*`, `nixpkgs*`, `baseRecipe*`, `baseArchiveUrl` and `baseArchiveSha256`.
  The `*Repository` values have no `.git` suffix.
- The `provenance.json` asset still carries the full runtime lock under `runtimeLock.contents`, for this release only.
  The client reads the manifest instead.

Deltas exist only for releases, never for prereleases.
A release ships deltas from the newest three published, non-draft, non-prerelease releases before it.
Delta generation is best effort: a failed delta is skipped and the full archive still ships.

## Full archive (archive schema 3)

- Compression: one xz stream (LZMA2, preset 9 extreme, CRC64 check).
- Container: POSIX tar (PAX headers allowed).
- Root: exactly one top-level directory, `Runtime/`.
  Its contents are the installed runtime root, unchanged: `bin/`, `lib/`, `share/`, `DXMT/`, `Licenses/`, `NOTICE.md`.
- Entry types: directories, regular files and relative symlinks. No hardlinks, devices or FIFOs.
- Determinism: entries are sorted by path, mtime is 0, uid and gid are 0, user and group names are empty.
  Regular files have mode `0755` when executable and `0644` otherwise; directories have `0755`.
  The same input tree therefore produces the same archive bytes.

The client writes its own `RUNTIME.json` into the installed root after extraction.
`RUNTIME.json` is never part of an archive or a delta.

## Delta (delta schema 1)

A delta is a tar.xz with the same compression and determinism rules and one top-level directory, `Delta/`:

```text
Delta/delta.json
Delta/data/0
Delta/data/1
...
```

### `delta.json`

```json
{
  "schemaVersion": 1,
  "arch": "arm64",
  "from": "1.0.1",
  "to": "1.0.2",
  "entries": [
    { "path": "bin", "type": "directory" },
    { "path": "bin/wine64", "type": "symlink", "target": "wine" },
    { "path": "lib/a.so", "type": "file", "executable": false, "size": 10, "sha256": "…",
      "op": "keep", "sourceSha256": "…" },
    { "path": "lib/b.so", "type": "file", "executable": false, "size": 20, "sha256": "…",
      "op": "patch", "sourceSha256": "…", "data": "data/0" },
    { "path": "lib/c.so", "type": "file", "executable": true, "size": 30, "sha256": "…",
      "op": "add", "data": "data/1" }
  ]
}
```

- `entries` lists the complete target tree, relative to the installed root, sorted by `path`, without the root itself.
- `path` and `target` follow the archive path rules: relative, `/`-separated, no empty, `.` or `..` components, no backslashes.
  A symlink `target` must resolve inside the root.
- `op` applies to files only:
  - `keep`: the installed file at `path` must hash to `sourceSha256`; it is reused unchanged.
  - `patch`: the installed file at `path` must hash to `sourceSha256`; the result is that file patched with `data`.
  - `add`: the content is `data` itself.
- For every file, the result must have exactly `size` bytes and hash to `sha256`.
- An installed path that `entries` does not list, other than the root `RUNTIME.json`, is removed.

### Patch data (`RTBSDF01`)

A patch is the bsdiff algorithm with uncompressed streams; the outer xz compresses it.
All integers are little-endian, signed values are two's complement.

```text
offset  size  field
0       8     magic "RTBSDF01"
8       8     u64  newSize
16      8     u64  controlCount
24      24*n  controlCount × (i64 add, i64 copy, i64 seek)
...           diff bytes   (sum of all add)
...           extra bytes  (sum of all copy)
```

Apply, starting with `newPos = 0` and `oldPos = 0`, for each control triple:

1. For `i` in `0..<add`: `new[newPos + i] = old[oldPos + i] &+ diff[next]` (byte addition modulo 256).
   Then `newPos += add`, `oldPos += add`.
2. Copy `copy` bytes from `extra` to `new[newPos...]`. Then `newPos += copy`.
3. `oldPos += seek`.

The patch is invalid when `add` or `copy` is negative, any read leaves `old`, `diff` or `extra`, any write leaves `newSize`,
the final `newPos` differs from `newSize`, or diff or extra bytes are left over.

## Client application

1. The pin lists deltas per lane as `{ "from", "url", "sha256", "sizeBytes" }`. The pin script builds each `url` from the manifest `name`; the client uses the pinned `url`.
   The client uses a delta only when `from` equals the installed version.
2. It downloads and verifies the delta like a full archive, then extracts it with the archive path rules.
3. It clones the installed root into staging, checks every `keep` and `patch` source hash, applies the entries,
   removes unlisted paths, and checks every result hash.
4. It continues with the normal install steps: validation, signature check (arm64), `RUNTIME.json`, atomic move.
5. Any failure discards the staging copy and falls back to the full archive.

## Test vector

`tests/test_deltas.py` checks this vector, and the client should check it too. The old file is `ABCDEFGH`. The new file is `ABXDEFGH!`.

| File | Bytes (hex) |
| --- | --- |
| old | `4142434445464748` |
| new | `414258444546474821` |
| patch | see the code block |

The patch has one control triple, `(add 8, copy 1, seek 0)`. Its diff bytes are `0000150000000000` and its extra byte is `21`. The hex below is grouped for reading; the test uses the same bytes without spaces.

```text
5254425344463031 0900000000000000 0100000000000000
0800000000000000 0100000000000000 0000000000000000
0000150000000000 21
```
