# AppContainer `userenv.dll` APIs

Chromium's sandbox loads these functions by name and checks that they resolve.
Wine 11.17 exports `CreateAppContainerProfile` only as a stub. The patch adds:

- `DeriveAppContainerSidFromAppContainerName`
- `DeleteAppContainerProfile`
- `GetAppContainerRegistryLocation`
- `GetAppContainerFolderPath`

The SID uses the Windows algorithm: SHA-256 of the lowercased container name, folded
into an `APP_PACKAGE` SID with the base RID and seven digest words. The registry and
folder locations return `E_NOTIMPL`; the sandbox does not require them to succeed.

The client can remove the process-local `userenv.dll` shim and the `userenv=n,b`
override once this patch is in the runtime.

Apply time: independent of the other Wine patches.
