# CEF compatibility provenance

## Source pins

- Wine base: `dappermint/winecx`
- Wine commit: <!-- pin:wine.commit|code -->`5ee1af65283cf7baf162cbab545a696d29206970`<!-- /pin --> (Wine <!-- pin:wine.version -->11.19<!-- /pin -->)

The generic CEF dispatcher is an original Arknights macOS Runtime change. It isolates regional descriptors from the loader mechanism.

## Ported inventory

### `bilibili-cef80`

The Bilibili CEF 80.1.15 descriptor is limited to the `libcef.dll` basename, the three proven RVAs, and all expected bytes, checked before any write. It is tagged as the CN descriptor. See the [CEF patch registry](../../../docs/patch-registry.md#cef) for the gates.

Add no descriptor without reverse-engineering evidence for its complete hash/RVA/byte contract.
