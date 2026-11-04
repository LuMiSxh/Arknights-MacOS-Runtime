# China client compatibility provenance

## Source pins

- Wine base: `dappermint/winecx`
- Wine commit: <!-- pin:wine.commit|code -->`e0aa380780b73e20fabcfe78fd42713b94929a53`<!-- /pin --> (Wine <!-- pin:wine.version -->11.17<!-- /pin -->)

The Bilibili windowing route is an original Arknights macOS Runtime change for the verified client window contract. It is separate from the CEF and ACE families.

## Ported inventory

### `windowing`

`0002-winemac-bilibili-join-all-spaces.patch` is an original runtime change. It makes the Bilibili platform window join all Spaces under the same gate.

The layered-child renderer route is limited to `PCGamePlatform.exe`, the Chromium `Chrome_WidgetWin_0` and `Chrome.WindowTranslucent` property contract, and a `CMyWebViewDlg` anywhere in the parent chain of the candidate. This supports nested Bilibili dialogs. Only `ARKNIGHTS_RUNTIME_CN_COMPAT=1` enables the route. It keeps the bounded Bilibili image/window preflights in the [CN patch registry](../../../docs/patch-registry.md#cn).
