# CEF compatibility provenance

## Source pins

- Wine base: `dappermint/winecx`
- Wine commit: `e0aa380780b73e20fabcfe78fd42713b94929a53` (Wine 11.17)

The generic CEF dispatcher is an original Arknights macOS Runtime change. It
keeps regional descriptors isolated from the loader mechanism and preserves
the normal Wine route unless explicitly enabled.

## Ported inventory

### `bilibili-cef80`

The Bilibili CEF 80.1.15 descriptor is limited to the `libcef.dll` basename,
the three proven RVAs, and all expected bytes before any write. It is tagged as
the CN descriptor: `ARKNIGHTS_RUNTIME_CEF_COMPAT=1` enables the generic
descriptor route, while `ARKNIGHTS_RUNTIME_CN_COMPAT=1` remains its legacy
fallback only when the explicit CEF flag is absent.

No regional descriptor is added without reverse-engineering evidence for its
complete hash/RVA/byte contract.
