# Wine CoreAudio default-output follow patch

Carries the two-commit Wine draft merge request [!11370](https://gitlab.winehq.org/wine/wine/-/merge_requests/11370), `winecoreaudio: Expose virtual endpoints for default devices`, onto the Arknights macOS Runtime WineCX pin.

## Provenance

- Upstream project: [Wine](https://gitlab.winehq.org/wine/wine)
- Upstream patch commits: `4d143f4cdbba2302799c29d67bf404ba2a60004f` and `65140f3139855dcc3fb96091210e3bb95ac7327f`
- Original author: Rhodri Richards (`rhodri.development@gmail.com`)
- Base runtime source: `dappermint/winecx` commit `e0aa380780b73e20fabcfe78fd42713b94929a53` (Wine 11.17)
- License: the modified Wine source file is LGPL-2.1-or-later. This patch uses the same license. Preserve the Wine copyright and license header when you distribute a built runtime.

This canary carries an unmerged Wine draft. The runtime adds only the opt-in `ARKNIGHTS_RUNTIME_AUDIO_FOLLOW_DEFAULT_OUTPUT=1`, parsed once per process. An absent, malformed, or `0` value keeps normal Wine behavior. When enabled, the virtual endpoint of an eligible shared render stream follows the default output, and an explicitly selected endpoint can recover after disconnect and reconnect. Capture and exclusive streams are unchanged.

## Build and test notes

Apply to the exact WineCX pin:

```sh
git apply --check patches/wine/audio/0001-winecoreaudio-default-output.patch
git apply patches/wine/audio/0001-winecoreaudio-default-output.patch
```

The patch adds no third-party dependency. The HAL callback reduces CoreAudio notifications to a pthread signal. A Wine worker thread retargets and stops/starts the AudioUnit. The render callback lock is never held across a stop or start. Process detach unregisters both HAL listeners, joins the worker, and restores the previous HAL run loop before Wine unloads the driver.

Test both environment modes. Switch the macOS default output during an active shared render stream. Confirm that the stream continues on the new output, keeps the application volume, and recovers after a device disconnects and reconnects. A successful compile does not prove upstream compatibility, because the draft can change its endpoint-notification semantics.
