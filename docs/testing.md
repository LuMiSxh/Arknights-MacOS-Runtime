# Testing

Automated checks may fetch and compile verified inputs, but never execute Wine or a game.

## Maintainer progression

1. `just check`: tests lock validation and workflow syntax.
2. `just prepare base`: verifies the unmodified source pins.
3. `just prepare audio`, `cursor`, and `cn`: applies each family independently without fuzz.
4. `just build combined`: builds an isolated private overlay canary.
5. `just verify`: checks archive paths, file types, dependency references, and deployment targets.
6. The build verifies its emitted checksum before publishing the artifact.
7. In a clean Arknights MacOS Client checkout, manually package the candidate with
   `just app <runtime-path>`.

Do not skip the current-runtime control or Arknights MacOS Runtime base comparison. Record the runtime
commit, lock, Mac, macOS version, prefix history, region, display, and audio devices.

## Hardware canary

- Audio: switch built-in, wired, Bluetooth, and HDMI defaults during playback; test disconnect,
  reconnect, mute, volume, sleep/wake, browser audio, and a long session.
- Cursor: compare frame latency 3, 2, and 1 at identical graphics settings, VSync modes, refresh
  rates, and capture method; record FPS, frame pacing, stutter, crashes, and cursor latency.
- Combined: test all flags absent, audio only, cursor only, and both on Global plus one available JP
  or KR path; cover clean shutdown and both fresh/existing prefixes.
- CN: do not activate until a current client, isolated prefix, suitable account, and informed tester
  exist. A compiled inactive path proves no compatibility.
