# Menu patch provenance

## Source pin

- Wine base: `dappermint/winecx`
- Wine commit: <!-- pin:wine.commit|code -->`e0aa380780b73e20fabcfe78fd42713b94929a53`<!-- /pin --> (Wine <!-- pin:wine.version -->11.17<!-- /pin -->)

## Patch

`0001-winemac-command-q-quit.patch` is an original Arknights macOS Runtime change. It changes the Quit item of the application menu in `dlls/winemac.drv/cocoa_app.m` from the mask `NSEventModifierFlagCommand | NSEventModifierFlagOption` to `NSEventModifierFlagCommand`. The other menu items keep their masks.

The patch keeps the LGPL-2.1-or-later license of Wine.
