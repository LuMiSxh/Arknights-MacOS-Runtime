# Client changes for an ARM64 runtime

Client paths are relative to the `Arknights-MacOS-Client` repository. None of these changes are part
of the runtime repository.

## Contract

| Input                            | Content                                                                                 |
| -------------------------------- | --------------------------------------------------------------------------------------- |
| `runtime.json`                   | Lane, archive URL and SHA-256, prefix revision, interface paths, component versions.    |
| `RUNTIME.json` in the app bundle | The same values after the build. The build records the embedded lane in `architecture`. |

`WineRuntime.discover()` checks `bin/Arknights`, decodes `RUNTIME.json`, and reads
`interface.runtimeCapabilities`. The Python build validates the full interface before it embeds the
runtime.

## Implemented

| Area                   | Change                                                                                                 |
| ---------------------- | ------------------------------------------------------------------------------------------------------ |
| ARM64 interface        | `armInterface` uses `aarch64-unix`, `aarch64-windows`, and the ARM driver.                             |
| Architecture selection | `runtime.json.architecture` names the lane. `--runtime-architecture` overrides it for a local runtime. |
| Embedded runtime       | The app no longer thins the runtime to x86_64.                                                         |
| Injected libraries     | `GameIconBridge.dylib` and `PlatformProcessWindowBridge.dylib` are universal.                          |
| Prefix identity        | The x86 lane uses `Prefix`; the ARM64 lane uses `Prefix-ARM64`.                                        |
| Rosetta gate           | The client skips the probe when `RUNTIME.json` names the arm lane.                                     |

## Capability manifest

The native-arm64 archive ships `runtime-capabilities-arm64.json`; the x86_64 archive keeps
`runtime-capabilities.json`. Schema version 2 adds two optional booleans:

| Key           | Meaning                                                         |
| ------------- | --------------------------------------------------------------- |
| `aceCompat`   | The full ACE patch set for the lane is present. `false` on ARM. |
| `nativeArm64` | The runtime runs without Rosetta. `true` on ARM.                |

The client treats a missing key as `false`. Use `aceCompat` in the ACE warning and launch policy. Use
`nativeArm64` for diagnostics and to keep the Rosetta copy off the ARM lane. The DXMT and Metal
capabilities keep their current meaning.

## Window chrome and the SDK bridge

The x86_64 loader records SDK 27.0, so the game window uses the current macOS decorations. The ARM64
loader records SDK 12.0, which selects the legacy decorations.

The client ships `SdkBridge.dylib` for the ARM64 lane only. It interposes
`dyld_get_program_sdk_version()` and returns the running system version. The client appends it to
`DYLD_INSERT_LIBRARIES` after `GameIconBridge.dylib`. The bridge reads the version through
`kern.osproductversion`; a framework call in the interposed path recurses back into it and hangs.

## Local canary

1. Build the ARM64 runtime archive and extract `Libraries/`.
2. Prepare the runtime root that the client expects: the contents of `Libraries/Wine` at the root, `DXMT/`
   beside it, and `runtime-capabilities-arm64.json` at the root.
3. Confirm `armInterface.runtimeCapabilities` names `runtime-capabilities-arm64.json`.
4. Build the app with the prepared runtime and the arm lane:

    ```sh
    just app /path/to/runtime arm
    ```

5. Confirm `Contents/Resources/RUNTIME.json` has `"architecture": "arm"` and the aarch64 interface.
6. Start the app with a new prefix. Do not use an existing x86_64 prefix.
7. Check the runtime, DXMT, and Metal device in the log. Run to the login screen, run the ACE check,
   and record the frame time against the x86_64 control with the same scene and settings.

## Regression tests

- An ARM64 runtime is discovered as native and does not require Rosetta.
- An x86_64 runtime still requires Rosetta.
- The x86 and ARM64 lanes use different prefix paths.
- A prefix does not mix module architectures.
- The build fails when `runtime.json` and the runtime directory disagree.
- A missing `aceCompat` or `nativeArm64` decodes as `false`.

Test lane selection at the type level. Use an enum with an exhaustive `switch`, not a Boolean.

## Copy

The UI says **Rosetta** only for the x86_64 runtime. The ARM64 runtime has no translation step. Reuse
`RT-BND` for a damaged runtime and `RT-SET` for a setup failure. Add a support code only when the
recovery action differs.
