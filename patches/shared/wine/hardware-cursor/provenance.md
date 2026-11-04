# Hardware Cursor patch provenance

## Source pin

- Wine base: `dappermint/winecx`
- Wine commit: <!-- pin:wine.commit|code -->`e0aa380780b73e20fabcfe78fd42713b94929a53`<!-- /pin --> (Wine <!-- pin:wine.version -->11.17<!-- /pin -->)
- User report: [PC client cursor-stutter discussion](https://www.reddit.com/r/arknights/comments/1vorlzp/pc_client_fix_for_the_annoying_mouse_stuttering/)

## Patch

`0001-ntdll-hide-software-cursor-asset.patch` is an original Arknights macOS Runtime change. When `ARKNIGHTS_RUNTIME_HARDWARE_CURSOR=1`, it filters either exact case-insensitive cursor asset basename from the shared NT-to-Unix path resolution of Wine: `a9d41799f1af1868f2db495671227cd4.bin` for the Yostar Global/Japan/Korea and Taiwan clients, or `f7bcd64480c4566f25d65d642f5fba95.bin` for the China — Bilibili client. It covers file opens and metadata lookups and blocks create-if-missing calls. It does not read, embed, copy, or modify game asset contents.

The patch keeps the LGPL-2.1-or-later license of Wine. Its Wine test additions cover exact and uppercase basenames for both assets, near-match basenames, create-if-missing behavior, and both attribute-query APIs, with the gate absent and enabled.
