# Agent Instructions

## Scope

- Build a reproducible WineCX and DXMT runtime for Arknights Client on Apple Silicon.
- Target macOS 15+. Overlay canaries may inherit byte-identical newer base binaries only when validation marks them non-release-eligible; releases reject them.
- Treat the v0.5 runtime artifact as release-bound only after its documented structural, licensing,
  provenance, and manual compatibility gates pass.
- Treat runtime environment variables as component-local controls. Each patch parses only its own
  gate; the gate rule below defines the accepted values.
- Keep original code, documentation, patch metadata, and commits in English.
- Write docs in ASD-STE100 Simplified Technical English: short sentences, active voice, one instruction per step, one term per concept, no filler.

## Commands

| Task                     | Command              |
| ------------------------ | -------------------- |
| Fast checks              | `just check`         |
| Validate lock            | `just validate`      |
| Monitor source pins      | `just monitor`       |
| Prepare pinned sources   | `just prepare`       |
| Build all-patches canary | `just build`         |
| Build release runtime    | `just build-release` |
| Verify artifact          | `just verify`        |

## Conventions

- `runtime.lock.json` is the sole source of source pins, patch order, archive paths, and deployment target. The native ARM64 artifact comes from the external catalog; the workflow verifies its SHA-256 and records the selection in provenance. When the selected release differs from the lock pin, the fetch writes the new release id and SHA-256 to the lock; when it matches, it enforces the locked SHA-256.
- Use full commits and SHA-256 hashes; reject floating refs and unverified downloads.
- Keep generated sources, downloads, reports, and artifacts under `.build/`; never commit binaries.
- Run Python through the root `pyproject.toml` and `uv.lock` with `uv run --locked`; keep runtime orchestration standard-library-only.
- Preserve upstream patch authorship, source links, trailers, and licenses in `docs/patch-registry.md`.
- Each patch has one documented gate, `LMISXH_AKMOCL_<NAME>`. A default-on gate is on when the
  variable is unset or exactly `1`; any other value turns it off. A default-off gate is on only for
  exactly `1`. The `_CN` and `_CURSOR` gates default off.
- Never infer patched behavior from a process name or path.
- Exception: the Bilibili windowing (`0007`, `0008`) and fullscreen (`0009`) patches may check the
  process name to exclude or scope helper processes. Document each such check in
  `docs/patch-registry.md`.
- Workflows use minimum permissions and pin actions to explicit `v` version tags.
- Do not run Wine, create prefixes, launch games, or publish releases during automated checks.
- Never replace release assets; corrections receive a new version.

## References

| Need                | File                     |
| ------------------- | ------------------------ |
| Repository boundary | `docs/architecture.md`     |
| Patch ownership     | `docs/patch-registry.md`   |
| Testing             | `docs/testing.md`          |
| Promotion           | `docs/releasing.md`        |
| Native ARM64 lane   | `docs/arm/README.md`       |
| ARM64 patch export  | `wine-build-new/README.md` |
