# Hardware Cursor patch provenance

## Source pin

- Wine base: `dappermint/winecx`
- Wine commit: `e0aa380780b73e20fabcfe78fd42713b94929a53` (Wine 11.17)
- User report: [PC client cursor-stutter discussion](https://www.reddit.com/r/arknights/comments/1vorlzp/pc_client_fix_for_the_annoying_mouse_stuttering/)

## Patch

`0001-ntdll-hide-software-cursor-asset.patch` is an original Arknights macOS Runtime change. It
filters one exact case-insensitive asset basename from Wine's shared NT-to-Unix path resolution when
`ARKNIGHTS_RUNTIME_HARDWARE_CURSOR=1`. This covers file opens and metadata lookups and also blocks
create-if-missing calls. It does not read, embed, copy, or modify game asset contents.

The patch retains Wine's LGPL-2.1-or-later license. Its upstream Wine test additions cover the exact
and uppercase basenames, near-match basenames, create-if-missing behavior, and both attribute-query
APIs. The tests can run in Wine's upstream suite under both absent and enabled gate values.
