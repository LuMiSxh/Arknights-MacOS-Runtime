# Skip Wine Mono in the ARM64 lane

The Wine Mono support package runs 32-bit and ARM64EC helper executables.
The 32-bit helpers need memory below 4 GB, which macOS refuses without the
cross-architecture entitlement. Wine retries the install on every prefix
creation and opens a download dialog when no cached package exists.

Arknights does not use .NET. The ARM64 lane therefore skips the install.
The guard uses `__aarch64__`, which covers the `aarch64-windows` and
`arm64ec-windows` builds. The x86_64 lane keeps the stock behavior.

Apply time: independent of the other Wine patches.
