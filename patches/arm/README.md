# ARM64 patches

This directory holds patches that apply only to the native-arm64 target.
Shared patches are in `../shared/`, and x86_64-only patches are in `../x86/`.

Nothing is here yet. These patches belong here as they are written:

- The ARM64 port of the ACE dispatcher spoof. The x86 patch embeds `int3` machine
  code, which cannot compile for ARM64EC, and CN clients set `ACE_COMPACT=1`.

Name a target list in `runtime.lock.json` for each patch here.
A patch without that list applies to every target.
