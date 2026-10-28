# Fullscreen patch provenance

## Source pin

- Wine base: `dappermint/winecx`
- Wine commit: <!-- pin:wine.commit|code -->`e0aa380780b73e20fabcfe78fd42713b94929a53`<!-- /pin --> (Wine <!-- pin:wine.version -->11.17<!-- /pin -->)

## Patch

`0001-winemac-native-fullscreen-space.patch` is an original Arknights macOS Runtime change. It changes `dlls/winemac.drv` only. It reuses the fullscreen toggle that WineCX already has for resizable windows. It adds no code from another project.

The patch keeps the LGPL-2.1-or-later license of Wine.
