# Client changes for an ARM64 runtime

Client paths are relative to the `Arknights-MacOS-Client` repository.
None of these changes are part of the runtime repository.

## Contract

The client reads two inputs:

| Input                            | Content                                                                        |
| -------------------------------- | ------------------------------------------------------------------------------ |
| `runtime.json`                   | Archive URL and SHA-256, prefix revision, interface paths, component versions. |
| `RUNTIME.json` in the app bundle | The same values after the build.                                               |

`WineRuntime.discover()` checks `bin/Arknights`, decodes `RUNTIME.json`, and reads
`interface.runtimeCapabilities`.
The Python build scripts validate the full interface before they embed the runtime.

## Implemented

| Area                   | Change                                                                        |
| ---------------------- | ----------------------------------------------------------------------------- |
| ARM64 interface        | `armInterface` uses `aarch64-unix`, `aarch64-windows`, and the ARM driver.    |
| Architecture selection | `--runtime-architecture` selects the lane; `RUNTIME.json` records the label.  |
| Embedded runtime       | The app no longer thins the runtime to x86_64.                                |
| Injected libraries     | `GameIconBridge.dylib` and `PlatformProcessWindowBridge.dylib` are universal. |
| Prefix identity        | Each target uses its own prefix.                                              |
| Rosetta gate           | The ARM64 runtime reports `notRequired` and skips the probe.                  |

## Capability manifest

The native-arm64 archive ships `runtime-capabilities-arm64.json`.
Its `interface.runtimeCapabilities` value names that file.
The x86_64 archive keeps `runtime-capabilities.json`.

Schema version 2 adds two optional booleans:

| Key           | Meaning                                                         |
| ------------- | --------------------------------------------------------------- |
| `aceCompat`   | The full ACE patch set for the lane is present. `false` on ARM. |
| `nativeArm64` | The runtime runs without Rosetta. `true` on ARM.                |

The client must treat a missing key as `false`.
Use `aceCompat` in the ACE warning and launch policy.
Use `nativeArm64` for diagnostics and to keep the Rosetta copy off the ARM lane.

The DXMT and Metal capabilities keep their current meaning.
The ARM64 manifest advertises them as true because the payload is built and validated.

## Window chrome and the SDK bridge

The x86_64 loader records the current SDK (`27.0`), so the game window uses the
current macOS decorations.
The ARM64 loader records SDK `12.0`, which the kernel requires to preserve x18.
AppKit reads the SDK version when it creates a window and selects the legacy
decorations.

A prototype bridge exists but is not shipped:

1. Add a `macos-library` component in `RuntimeSupport/` that interposes
   `dyld_get_program_sdk_version()` and returns the running OS version.
2. Append its path to `DYLD_INSERT_LIBRARIES` in
   `Sources/ArknightsGameRuntime/Runtime/WineRuntime+Environment.swift`.
   Do not overwrite the existing `GameIconBridge` path; join with `:`.
3. Build it universal so one bundle serves both lanes.
4. If the app ever adopts the hardened runtime, add
   `com.apple.security.cs.allow-dyld-environment-variables`.

The prototype returned the running OS version and AppKit called it during window
creation.
It stays out of the bundle until the ARM64 lane runs the game.

## Local canary

1. Build the ARM64 runtime archive and extract `Libraries/`.
2. Point `runtime.json` at the archive and use `armInterface`.
3. Confirm `interface.runtimeCapabilities` names `runtime-capabilities-arm64.json`.
4. Build the app with the extracted runtime:

    ```sh
    just app /path/to/candidate/Libraries
    ```

5. Start the app with a new prefix.
6. Check the log for the runtime version, the DXMT version, and the Metal device.
7. Run the game to the login screen.
8. Run the ACE check.
9. Record the frame time with the same scene and settings as the x86_64 control.

Do not use an existing x86_64 prefix.
Do not compare frame time across different prefixes, display settings, or warm-up runs.

## Regression tests

Add one test for each contract that the lane selection can break:

- An ARM64 runtime is discovered as native and does not require Rosetta.
- An x86_64 runtime still requires Rosetta.
- A prefix does not mix module architectures.
- The build fails when `runtime.json` and the runtime directory disagree.
- A missing `aceCompat` or `nativeArm64` key decodes as `false`.

Test the lane selection at the type level if possible.
A small enum with an exhaustive `switch` is better than a Boolean.

## Copy

The UI says "Rosetta" in the Intel translation state and in the runtime errors.
Show this copy only for the x86_64 runtime.
The ARM64 runtime has no translation step.

Reuse `RT-BND` for a damaged runtime and `RT-SET` for a setup failure.
Add a support code only when the recovery action differs.
