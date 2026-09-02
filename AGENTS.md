# Agent Instructions

## Scope

- Build a reproducible WineCX and DXMT runtime for Arknights Client on Apple Silicon.
- Target macOS 15+. Overlay canaries may inherit byte-identical newer base binaries only when validation marks them non-release-eligible; releases reject them.
- Treat the v0.5 runtime artifact as release-bound only after its documented structural, licensing,
  provenance, and manual compatibility gates pass.
- Treat runtime environment variables as component-local controls; absent or invalid values preserve
  each component's documented default.
- Keep original code, documentation, patch metadata, and commits in English.

## Commands

| Task                  | Command                                                  |
| --------------------- | -------------------------------------------------------- |
| Fast checks           | `just check`                                             |
| Validate lock         | `just validate`                                          |
| Monitor source pins   | `just monitor`                                           |
| Apply one stage       | `just prepare audio`                                     |
| Build combined canary | `just build combined`                                    |
| Build release runtime | `just build-release`                                     |
| Verify artifact       | `just verify .build/stages/combined/candidate/Libraries` |

## Conventions

- `runtime.lock.json` is the sole source of pins, patch order, archive paths, and deployment target.
- Use full commits and SHA-256 hashes; reject floating refs and unverified downloads.
- Keep generated sources, downloads, reports, and artifacts under `.build/`; never commit binaries.
- Run Python through the root `pyproject.toml` and `uv.lock` with `uv run --locked`; keep runtime orchestration standard-library-only.
- Preserve upstream patch authorship, source links, trailers, and licenses in `docs/patch-registry.md`.
- Gate each patch family with one documented `ARKNIGHTS_RUNTIME_` variable; absent or invalid input
  preserves the documented default.
- Never infer patched behavior from a process name or path.
- Workflows use minimum permissions and pin actions to explicit `v` version tags.
- Do not run Wine, create prefixes, launch games, or publish releases during automated checks.
- Never replace release assets; corrections receive a new version.

## References

| Need                | File                     |
| ------------------- | ------------------------ |
| Repository boundary | `docs/architecture.md`   |
| Patch ownership     | `docs/patch-registry.md` |
| Testing             | `docs/testing.md`        |
| Promotion           | `docs/releasing.md`      |
