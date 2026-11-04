# `SIO_ADDRESS_LIST_SORT`

Chromium's asynchronous DNS resolver calls `WSAIoctl(SIO_ADDRESS_LIST_SORT)` to order
IPv6 destinations. Wine returned `WSAEOPNOTSUPP`, so CEF retried the call and an OAuth
page stayed blank. The patch adds the constant and handles the ioctl in `ws2_32`.

The returned list keeps the supplied order. Windows applies RFC 6724 destination
ordering, which needs the source addresses; Chromium only needs a valid list.

The client can remove `--disable-features=AsyncDns` from the Vuplex wrapper once this
patch is in the runtime.

Apply time: independent of the other Wine patches.
