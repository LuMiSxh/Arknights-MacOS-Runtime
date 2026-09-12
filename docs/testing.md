# Testing

> [!IMPORTANT]
> Automated checks may fetch and compile verified inputs, but never execute Wine or a game. Real
> runtime behavior belongs to the manual compatibility canary below.

## Maintainer progression

1. `just check`: tests lock validation and workflow syntax.
2. `just monitor`: verifies every pinned upstream commit and reports newer repository heads without
   changing the lock.
3. `just prepare base`: verifies the unmodified source pins.
4. `just prepare audio`, `cursor`, `performance`, and `cn`: applies each family independently without fuzz.
5. `just build combined`: builds an isolated overlay canary for iteration; it is not a release
   build.
6. `just verify`: checks archive paths, file types, DXMT native-loader markers, dependency references,
   and deployment targets. Locally rebuilt D3D10/D3D11/DXGI DLLs must receive the same DOS-stub
   preparation as `build-canary.sh`; Wine's builtin marker otherwise overrides native-first loading.
   Keep the builtin marker on `winemetal.dll`.
7. The build verifies its emitted checksum before publishing the artifact.
8. Integrate and exercise the artifact in its consumer.
9. Dispatch the release workflow with one version only after a clean full build is available. It
   creates the tag and draft release only after all release gates pass.

The source monitor runs on the first day of each month and on manual dispatch. A changed repository
head is informational; pins move only through a reviewed `runtime.lock.json` change. An unreachable
or missing pin fails the monitor without opening or mutating issues.

Do not skip the current-runtime control or Arknights macOS Runtime base comparison. Record the runtime
commit, lock, Mac, macOS version, prefix history, display, and audio devices.

## Hardware canary

- Audio: switch built-in, wired, Bluetooth, and HDMI defaults during playback; test disconnect,
  reconnect, mute, volume, sleep/wake, browser audio, and a long session.
- Cursor: compare frame latency 3, 2, and 1 at identical graphics settings, VSync modes, refresh
  rates, and capture method; record FPS, frame pacing, stutter, crashes, and cursor latency.
- Performance: compare `ARKNIGHTS_RUNTIME_PERFORMANCE=0` and `1` after restarting the game, using
  the same scene, graphics settings, and capture duration. Record ColorSync CPU samples, total CPU,
  GPU activity, and frame times separately. Exercise profile changes, display reconnect, sleep/wake,
  SDR/HDR changes, and multiple displays; HDR/EDR must remain live. A cache has a one-second expiry
  bound if macOS delays or drops a profile notification. Check startup with the flag both disabled
  and enabled; the device-initialization correction applies in both cases.
- CN: compare the absent, `0`, invalid, and `1` control values in an isolated test prefix; record
  launcher startup, login, ACE initialization, gameplay, and clean shutdown. For Bilibili, complete a
  captcha and verify both its renderer and a translucent error toast.
- Combined: test all flags absent, each family independently, and all enabled together; cover clean
  shutdown and both fresh and existing test prefixes.
