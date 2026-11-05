# Bake the game name into the loader

The loader rewrites `CFBundleName` in `__TEXT` at startup. It takes the name from
`WINEPRELOADERAPPNAME`. arm64 rejects that write, so the Dock falls back to the embedded
`__info_plist`, which names the host application.

Set the embedded name to `Arknights` at build time. The client already passes
`WINEPRELOADERAPPNAME=Arknights`, so the crash-report prefix stays `Arknights-*.ips`.

Apply it to the `native-arm64` target only.
