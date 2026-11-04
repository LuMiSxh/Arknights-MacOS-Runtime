# Client changes for an ARM64 runtime

This document lists the changes in the Arknights MacOS Client that an ARM64 runtime needs.
Client paths are relative to the `Arknights-MacOS-Client` repository.
None of these changes are part of the runtime repository.

## Current contract

The client reads two inputs:

| Input                            | Current content                                                                |
| -------------------------------- | ------------------------------------------------------------------------------ |
| `runtime.json`                   | Archive URL and SHA-256, prefix revision, interface paths, component versions. |
| `RUNTIME.json` in the app bundle | The same values after the build.                                               |

`WineRuntime.discover()` checks `bin/Arknights` and decodes `RUNTIME.json`.
It also reads `interface.runtimeCapabilities`.
The Python build scripts validate the full interface before they embed the runtime.

The runtime itself is launcher-agnostic.
The client supplies the prefix, the display settings, the environment, and the log file.

## Required changes

| File                             | Change                                                                                                                    | Reason                                                                       |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `runtime.json`                   | Add an ARM64 interface: `lib/wine/aarch64-unix`, `lib/wine/aarch64-windows`, `macDriver`, `requiredFiles`, `executables`. | The paths are x86_64 only today.                                             |
| `RuntimeSupport/support.toml`    | Build `GameIconBridge.dylib` and `PlatformProcessWindowBridge.dylib` for arm64, or as universal binaries.                 | The current build forces `-arch x86_64` in `scripts/build_compatibility.py`. |
| `WineRuntime`                    | Record the runtime architecture. Use `lipo -archs` on `bin/wine64`, or a new `interface.architecture` field.              | The launcher must select the lane without guessing.                          |
| `RosettaAvailability`            | Return `notRequired` for an ARM64 runtime and skip the probe.                                                             | Rosetta is irrelevant to this runtime.                                       |
| `IntelTranslationController`     | Do not gate Play on Rosetta for an ARM64 runtime.                                                                         | The current gate blocks the game.                                            |
| `GameRuntimeError`               | Keep the Rosetta errors for the x86_64 runtime only.                                                                      | The messages are wrong for ARM64.                                            |
| `WinePrefixLibraryDeduplicator`  | Read the module directory from the runtime layout, or skip the pair when the directory is absent.                         | It hardcodes `x86_64-windows` and `i386-windows`.                            |
| `WinePrefixLegacyLibraryCleaner` | Skip the cleaner when the runtime has no `x86_64-windows` directory.                                                      | The directory is the proof that the runtime is real.                         |
| `scripts/build_app.py`           | Do not thin the embedded runtime to x86_64.                                                                               | `thin_universal_files()` currently removes the arm64 slice.                  |
| `scripts/runtime_config.py`      | No code change if `runtime.json` names the ARM64 paths.                                                                   | The validator is layout driven.                                              |
| `Sources/.../WinePrefix...`      | Give each runtime target its own prefix, or reset the prefix when the target changes.                                     | x86_64 and ARM64EC DLLs must not share `system32`.                           |

## Prefix identity

A prefix contains the PE modules that Wine installs during `wineboot`.
The x86_64 runtime installs x86_64 modules.
The ARM64 runtime installs ARM64EC and Aarch64 modules.
A prefix must contain only one architecture.

Use one of these options:

1. A prefix path that includes the target name.
2. A prefix revision bump that rebuilds the prefix on the target change.
3. A migration that clears `drive_c/windows/system32` and `syswow64` before the first launch.

Option 1 is the simplest. The game files stay outside the prefix.
The client applies the display and font settings on each launch, so a new prefix only costs the first `wineboot`.

## Injected macOS libraries

Wine injects two Mach-O libraries into the game process:

| Library                             | Injection                               | Architecture requirement            |
| ----------------------------------- | --------------------------------------- | ----------------------------------- |
| `GameIconBridge.dylib`              | `DYLD_INSERT_LIBRARIES`                 | Must match the Wine host, so arm64. |
| `PlatformProcessWindowBridge.dylib` | Injected by the WineCX unix passthrough | Must match the Wine host, so arm64. |

`DYLD_INSERT_LIBRARIES` with an x86_64 library stops an arm64 process at launch.
For the first canary, build the two libraries for arm64.
A universal build keeps both lanes on one artifact.

The Vuplex and Bilibili Windows executables are PE files.
They run as x86_64 under FEX and need no change.

## Proposed interface

Use this interface block for the first canary.
It keeps the client schema and changes only the architecture paths.

```json
"interface": {
  "archive": { "wineDirectory": "Wine", "dxmtDirectory": "DXMT" },
  "executables": ["bin/wine64", "bin/wineserver"],
  "runtimeCapabilities": "runtime-capabilities.json",
  "requiredFiles": [
    "lib/wine/aarch64-unix/winecoreaudio.so",
    "lib/wine/aarch64-windows/winemetal.dll"
  ],
  "macDriver": "lib/wine/aarch64-unix/winemac.so",
  "launcher": { "path": "bin/Arknights", "target": "wine64" },
  "dxmt": {
    "payloadDirectory": "DXMT",
    "destinations": { "x64": "system32" },
    "libraries": ["d3d10core.dll", "d3d11.dll", "dxgi.dll", "winemetal.dll"]
  }
}
```

The DXMT destination stays `x64` and `system32`.
Only the payload architecture changes.

## Canary procedure

1. Build the ARM64 runtime archive and extract `Libraries/`.
2. Copy `runtime.json` to a local branch.
3. Replace the interface block with the ARM64 paths from the proposed interface above.
4. Keep the archive URL and SHA-256 of the released runtime, or pin the canary values.
5. Build the support libraries for arm64.
6. Build the app with the extracted runtime:

    ```sh
    just app /path/to/candidate/Libraries
    ```

7. Start the app with a new prefix.
8. Check the log for the runtime version, the DXMT version, and the Metal device.
9. Run the game to the login screen.
10. Run the ACE check.
11. Record the frame time with the same scene and settings as the x86_64 control.

Do not use an existing x86_64 prefix.
Do not compare frame time across different prefixes, display settings, or warm-up runs.

## Regression tests

Add one test for each contract that the lane selection can break:

- An ARM64 runtime is discovered as native and does not require Rosetta.
- An x86_64 runtime still requires Rosetta.
- A prefix does not mix module architectures.
- The build fails when `runtime.json` and the runtime directory disagree.

Test the lane selection at the type level if possible.
A small enum with an exhaustive `switch` is better than a Boolean.

## Copy

The UI says "Rosetta" in the Intel translation state and in the runtime errors.
Show this copy only for the x86_64 runtime.
The ARM64 runtime has no translation step.

Do not add a new support code for the ARM64 lane yet.
Reuse `RT-BND` for a damaged runtime and `RT-SET` for a setup failure.
Add a code only when the recovery action differs.
