# Updating pins

The runtime pins four upstream inputs in [`runtime.lock.json`](../runtime.lock.json): Wine, DXMT, the base archive, and nixpkgs. One command moves all pins to the newest upstream state. It also rewrites every mention of a pin in the repository.

## Current pins

<!-- pin-block:table -->
| Pin | Value |
| --- | --- |
| `wine.commit` | `e0aa380780b73e20fabcfe78fd42713b94929a53` |
| `wine.version` | `11.17` |
| `dxmt.commit` | `e94c312f5c054263acf261cfa109edf13e757587` |
| `dxmt.version` | `0.80-262-ge94c312` |
| `base.tag` | `v4.7.3` |
| `base.url` | `https://github.com/dappermint/Whisky/releases/download/v4.7.3/Libraries.tar.gz` |
| `base.sha256` | `a4b5d63493f80698cce5cad8e7212d9a51c8292037b00c478f4652636fcfd331` |
| `base.recipe` | `0bf3eabc2f0d95154282eb86b11205cbbaae6c65` |
| `nixpkgs.commit` | `ac62194c3917d5f474c1a844b6fd6da2db95077d` |
<!-- /pin-block -->

## Which version each pin follows

| Pin | Rule |
| --- | --- |
| Wine | Tip of the highest `wine11<N>` branch of `dappermint/winecx`. The version comes from the `VERSION` file at that commit. |
| DXMT | Head of the default branch of `3Shain/dxmt`. The version has the `git describe` form `<tag>-<commits>-g<sha>`. |
| Base archive | Newest `dappermint/Whisky` release with a `Libraries.tar.gz` asset. The hash comes from the digest of the asset. The recipe commit is the commit of the tag `runtime-<release tag>` in `dappermint/winecx-gptk`. |
| nixpkgs | Tip of the channel branch `NIXPKGS_CHANNEL` in `scripts/release/pins.py`. The channel is `nixos-25.05`, because the DXMT build needs `llvmPackages_15`, which later releases removed. |

A newer nixpkgs channel is a manual decision. Change the constant, then review the library closure.

## Update the pins

1. Set `GITHUB_TOKEN` or `GH_TOKEN` to avoid the API rate limit. The command also works without a token.
2. Run `just update-pins --dry-run`. The command resolves the new state and writes nothing.
3. Read the summary table. Each row shows the old pin, the new pin, and the status.
4. Run `just update-pins`.
5. To update one component, run `just update-pins --only wine`. The values of `--only` are `wine`, `dxmt`, `base`, and `nixpkgs`.

The command stops with no changes when it cannot resolve the base archive or its recipe commit. It also stops when the API gives no digest for the asset.

## The patch guard

Before it changes the Wine or DXMT pin, the command fetches the new commit into a temporary directory. It runs `git apply --check` and then `git apply` for each patch of that component, in lock order.

If a patch fails, the command keeps the old pin of that component. It prints the failed patch and the reason. The other components still update. The exit status stays 0.

To move a kept pin, port the failed patch to the new commit. Then run the update again.

## After the update

1. Read the output of `just check`. The update already runs the lock validation and the license check.
2. Review the gates in [`patch-registry.md`](patch-registry.md) for the new commits.
3. Review the license statements for DXMT and Wine when the upstream license can change.
4. The MoltenVK and Wine Gecko entries in `baseProvenance` do not change by themselves. Update them by hand if the new base archive changes them.
5. Dispatch the release workflow. See [`releasing.md`](releasing.md).
6. Update the client pin with the update command of the client repository.

## Check the mentions

Run `just check`. It runs `scripts/release/pins.py check`, which works offline. The check fails when a marker or an allowlisted file disagrees with the lock. The CI check workflow runs the same command.

## Add a marker

1. Choose a key from the list below.
2. Write the marker around the value. Use `|code` to put the value in a code span. Put the marker outside the backticks of the text.
3. Run `just update-pins --dry-run`. Then run `just check`.

```markdown
Wine <!-- pin:wine.version -->11.17<!-- /pin -->
<!-- pin:wine.commit|code -->`e0aa380780b73e20fabcfe78fd42713b94929a53`<!-- /pin -->
```

Fenced code blocks are not scanned. An unknown key fails the check.

| Key | Value |
| --- | --- |
| `wine.commit`, `dxmt.commit`, `nixpkgs.commit` | Full commit hash |
| `wine.short`, `dxmt.short`, `nixpkgs.short` | First seven characters of the commit |
| `wine.version`, `dxmt.version` | Version string of the lock |
| `wine.link`, `dxmt.link`, `nixpkgs.link` | Markdown link to the source tree, with the short hash as text |
| `dxmt.tag`, `dxmt.build`, `dxmt.describe` | Latest tag (`0.80`), tag with commit count (`0.80-262`), version with `v` (`v0.80-262-ge94c312`) |
| `base.tag`, `base.version` | Release tag (`v4.7.3`), release number (`4.7.3`) |
| `base.url`, `base.sha256` | URL and hash of the base archive |
| `base.recipe`, `base.recipeShort` | Full and short recipe commit |

Use `<!-- pin-block:table -->` and `<!-- /pin-block -->` on their own lines for the generated table of pins.

## Add a file that is not Markdown

1. Open `ALLOWLIST` in `scripts/release/pins.py`.
2. Add the path and the keys that the file states.
3. Run `just check`. The check fails when the file lacks the value of a key.

The update replaces the old value of each key with the new value. Prose that is not a pin stays unchanged.
