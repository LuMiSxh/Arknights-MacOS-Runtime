# Menu patch provenance

## Source pin

- Wine base: `dappermint/winecx`
- Wine commit: <!-- pin:wine.commit|code -->`b1417d2773a0dfc15cc78b78e1257ee965bcca89`<!-- /pin --> (Wine <!-- pin:wine.version -->11.19<!-- /pin -->)

## Patch

`0001-winemac-command-q-quit.patch` is an original Arknights macOS Runtime change. It changes the Quit item of the application menu in `dlls/winemac.drv/cocoa_app.m` from the mask `NSEventModifierFlagCommand | NSEventModifierFlagOption` to `NSEventModifierFlagCommand`. The other menu items keep their masks.

The patch keeps the LGPL-2.1-or-later license of Wine.
