# China client compatibility provenance

## Source pins

- Wine base: `dappermint/winecx`
- Wine commit: <!-- pin:wine.commit|code -->`5ee1af65283cf7baf162cbab545a696d29206970`<!-- /pin --> (Wine <!-- pin:wine.version -->11.19<!-- /pin -->)

The Bilibili windowing route is an original Arknights macOS Runtime change for the verified client window contract. It is separate from the CEF and ACE families.

## Ported inventory

### `windowing`

The layered-child renderer route is limited to `PCGamePlatform.exe`, the Chromium `Chrome_WidgetWin_0` and `Chrome.WindowTranslucent` property contract, and a `CMyWebViewDlg` anywhere in the parent chain of the candidate. This supports nested Bilibili dialogs. Only `ARKNIGHTS_RUNTIME_CN_COMPAT=1` enables the route. It keeps the bounded Bilibili image/window preflights in the [CN patch registry](../../../docs/patch-registry.md#cn).
