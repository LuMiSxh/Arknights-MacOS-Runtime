# China client compatibility provenance

## Source pins

- Wine base: `dappermint/winecx`
- Wine commit: `e0aa380780b73e20fabcfe78fd42713b94929a53` (Wine 11.17)

The Bilibili windowing route is an original Arknights macOS Runtime change for the verified client window contract. It is separate from the CEF and ACE families.

## Ported inventory

### `windowing`

The layered-child renderer route is limited to `PCGamePlatform.exe`, the Chromium `Chrome_WidgetWin_0` and `Chrome.WindowTranslucent` property contract, and a `CMyWebViewDlg` anywhere in the parent chain of the candidate. This supports nested Bilibili dialogs. Only `ARKNIGHTS_RUNTIME_CN_COMPAT=1` enables the route. It keeps the bounded Bilibili image/window preflights in the [CN patch registry](../../../docs/patch-registry.md#cn).
