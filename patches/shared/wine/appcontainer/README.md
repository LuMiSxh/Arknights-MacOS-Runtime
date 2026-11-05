# AppContainer compatibility APIs

Chromium's sandbox loads these functions by name and checks that they resolve.
Wine 11.17 exports `CreateAppContainerProfile` only as a stub. The patch adds:

- `DeriveAppContainerSidFromAppContainerName`
- `DeleteAppContainerProfile`
- `GetAppContainerRegistryLocation`
- `GetAppContainerFolderPath`
- `CreateAppContainerToken`
- `GetAppContainerNamedObjectPath`

The SID uses the Windows algorithm: SHA-256 of the lowercased container name, folded
into an `APP_PACKAGE` SID with the base RID and seven digest words. The registry and
folder locations return `E_NOTIMPL`; the sandbox does not require them to succeed.

The two `kernelbase` exports are stubs. They return `FALSE` with
`ERROR_CALL_NOT_IMPLEMENTED`. Chromium only requires the names to resolve, so the
sandbox disables itself instead of aborting the browser.

The client can remove the process-local `userenv.dll` shim and the `userenv=n,b`
override once this patch is in the runtime.

Apply time: independent of the other Wine patches.
