# Testing

> [!IMPORTANT]
> Automated checks can fetch and compile verified inputs. They never execute Wine or a game. The manual canary tests real runtime behavior.

## Maintainer progression

1. `just check`: tests lock validation and workflow syntax.
2. `just monitor`: verifies every pinned upstream commit and reports newer heads without changing the lock.
3. `just prepare base`: verifies the unmodified source pins.
4. `just prepare audio`, `cursor`, `hardware-cursor`, `performance`, `ace`, `cef`, and `cn`: applies each family independently without fuzz.
5. `just build combined`: builds an isolated overlay canary. It is not a release build.
6. `just verify`: checks archive paths, file types, DXMT native-loader markers, dependency references, and deployment targets. Prepare locally rebuilt D3D10/D3D11/DXGI DLLs with the DOS stub of `build-canary.sh`. Otherwise Wine's builtin marker overrides native-first loading. Keep the builtin marker on `winemetal.dll`.
7. The build verifies its emitted checksum before it publishes the artifact. Integrate and exercise the artifact in its consumer.
8. After a clean full build, dispatch the release workflow with one version. It creates the tag and draft release only after all release gates pass.

The source monitor runs monthly (first day) and on manual dispatch. A changed head is informational: pins move only through a reviewed `runtime.lock.json` change. An unreachable or missing pin fails the monitor, which never opens or changes issues.

Always run the current-runtime control and base comparison. Record the runtime commit, lock, Mac, macOS version, prefix history, display, and audio devices.

## Frametime capture

On macOS 27, start the client, navigate to the fixed scene, and warm it up. Run `just frametime-record CASE SECONDS` and begin the scene when instructed. The harness never launches Wine, the client, or the game. It stores raw `.atrc` traces, timeline overviews, and the manifest under `.build/frametimes/`.

Restart the game before every comparison. Capture same-binary A/A runs first to measure variation. Then run the A/B comparison with the same scene, settings, warm-up, and duration.

## Hardware canary

Test the absent, `0`, invalid, and `1` values of each control in an isolated prefix.

- Audio: switch built-in, wired, Bluetooth, and HDMI defaults during playback. Test disconnect, reconnect, mute, volume, sleep/wake, browser audio, and a long session.
- Cursor: compare frame latency 3, 2, and 1 with identical graphics settings, VSync modes, refresh rates, and capture method. Record FPS, frame pacing, stutter, crashes, and cursor latency.
- Hardware Cursor: confirm that only `a9d41799f1af1868f2db495671227cd4.bin` (Yostar/TW) or `f7bcd64480c4566f25d65d642f5fba95.bin` (CN) is hidden. Verify that the game still shows and moves the macOS pointer.
- Performance: apply the performance stage, restart the game, and run a startup and rendering smoke test. Record crashes, missing effects, and frame times. The statistics gate is compile-time only: debug builds keep the HUD and aggregation, release builds keep frame counters and synchronization. Use the settings and fixed scene of the preceding control.
- ACE: record launcher startup, ACE initialization, gameplay, and clean shutdown.
- CEF: verify that an explicit CEF control takes precedence over the legacy CN fallback. Exercise the Bilibili descriptor only with its matching module and bytes.
- CN: for Bilibili, complete a captcha. Verify the layered renderer and a translucent error toast. Include nested dialogs with a `CMyWebViewDlg` parent-chain match where available.
  - The issue #79 payment candidate is a `Chrome_WidgetWin_0` `WS_CHILD` non-popup directly parented by `CefBrowserWindow`. Its parent links lead to a non-child `CPayDlg_P_<suffix>` root. The renderer, parent, and root share one Windows PID.
  - The driver must still observe `Chrome.WindowTranslucent` and a layered surface.
  - Offline tests cover the captured tree and wrong parent, root, style, PID, owner-only, and missing-property cases. Manual payment rendering is still required.
- Combined: test all flags absent, each family alone, and all enabled, with clean shutdown, in fresh and existing prefixes.
