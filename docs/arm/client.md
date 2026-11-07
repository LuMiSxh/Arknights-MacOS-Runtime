# Client changes for an ARM64 runtime

Client paths are relative to the `Arknights-MacOS-Client` repository. None of these changes are part
of the runtime repository.

## Contract

| Input                            | Content                                                                                 |
| -------------------------------- | --------------------------------------------------------------------------------------- |
| `runtime.json`                   | Lane, archive URL and SHA-256, prefix revision, interface paths, component versions.    |
| `RUNTIME.json` in the app bundle | The same values after the build. The build records the embedded lane in `architecture`. |

`WineRuntime.discover()` checks `bin/Arknights`, decodes `RUNTIME.json`, and reads
`features`. The Python build validates the lock before it embeds the runtime.

## Implemented

| Area                   | Change                                                                                                 |
| ---------------------- | ------------------------------------------------------------------------------------------------------ |
| ARM64 interface        | `armInterface` uses `aarch64-unix`, `aarch64-windows`, and the ARM driver.                             |
| Architecture selection | `runtime.json.architecture` names the lane. `--runtime-architecture` overrides it for a local runtime. |
| Embedded runtime       | The app no longer thins the runtime to x86_64.                                                         |
| Injected libraries     | `GameIconBridge.dylib` and `PlatformProcessWindowBridge.dylib` are universal.                          |
| Prefix identity        | The x86 lane uses `Prefix`; the ARM64 lane uses `Prefix-ARM64`.                                        |
| Rosetta gate           | The client skips the probe when `RUNTIME.json` names the arm lane.                                     |

## Runtime features

The runtime lock and the embedded `RUNTIME.json` carry one `features` object:

```json
{
    "hardwareCursor": true,
    "metalFXSpatialUpscaling": true,
    "nativeFullscreenSpace": true
}
```

The client treats a missing feature as `false`. `nativeArm64` is gone; the lane in `architecture`
already identifies an ARM64 runtime. `aceCompat` is gone; it was About-only and had no launch policy.

## Window chrome

The external ARM64 loader keeps its Developer ID signature and provisioning profile. Do not re-sign, relink, or replace it. The client has no chrome bridge. In-process interposition and AppKit appearance changes do not change the real frame. See [entitlements](entitlements.md#window-chrome).

## Local canary

1. Download the ARM64 runtime archive that `runtime.json` pins and verify its SHA-256.
2. Extract `Libraries/`.
3. Prepare the runtime root that the client expects: the contents of `Libraries/Wine` at the root and `DXMT/` beside it.
4. Confirm the runtime `features` match the lane.
5. Build the app with the prepared runtime and the arm lane:

    ```sh
    just app /path/to/runtime arm
    ```

6. Confirm `Contents/Resources/RUNTIME.json` has `"architecture": "arm"` and the aarch64 interface.
7. Start the app with a new prefix. Do not use an existing x86_64 prefix.
8. Check the runtime, DXMT, and Metal device in the log. Run to the login screen, run the ACE check,
   and record the frame time against the x86_64 control with the same scene and settings.

## Regression tests

- An ARM64 runtime is discovered as native and does not require Rosetta.
- An x86_64 runtime still requires Rosetta.
- The x86 and ARM64 lanes use different prefix paths.
- A prefix does not mix module architectures.
- The build fails when `runtime.json` and the runtime directory disagree.
- A missing feature decodes as `false`.

Test lane selection at the type level. Use an enum with an exhaustive `switch`, not a Boolean.

## Copy

The UI says **Rosetta** only for the x86_64 runtime. The ARM64 runtime has no translation step. Reuse
`RT-BND` for a damaged runtime and `RT-SET` for a setup failure. Add a support code only when the
recovery action differs.
