# China client compatibility provenance

## Source pins

- Wine base: `dappermint/winecx`
- Wine commit: `e1b410a5fdd96a32722a5f2617b5068bd385b7db` (Wine 11.16)

The Bilibili windowing route is an original Arknights macOS Runtime change for
the verified client window contract. It is deliberately separate from the CEF
descriptor family and ACE compact compatibility family.

## Ported inventory

### `windowing`

The layered-child renderer route is limited to `PCGamePlatform.exe`,
Chromium's `Chrome_WidgetWin_0` and `Chrome.WindowTranslucent` property
contract, and a `CMyWebViewDlg` found anywhere in the candidate's parent
chain. This supports nested Bilibili dialogs while retaining the same process,
class, property, and CN gates. It is enabled only by
`ARKNIGHTS_RUNTIME_CN_COMPAT=1` and retains the bounded Bilibili image/window
preflights described in the [CN patch registry](../../../docs/patch-registry.md#cn).
