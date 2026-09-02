# Wine CoreAudio default-output follow patch

This patch carries the two-commit Wine draft merge request [!11370](https://gitlab.winehq.org/wine/wine/-/merge_requests/11370), `winecoreaudio: Expose virtual endpoints for default devices`, onto the Arknights macOS Runtime WineCX pin.

## Provenance

- Upstream project: [Wine](https://gitlab.winehq.org/wine/wine)
- Upstream merge request: [!11370](https://gitlab.winehq.org/wine/wine/-/merge_requests/11370)
- Upstream patch commits: `4d143f4cdbba2302799c29d67bf404ba2a60004f` and `65140f3139855dcc3fb96091210e3bb95ac7327f`
- Original author: Rhodri Richards (`rhodri.development@gmail.com`)
- Base runtime source: `dappermint/winecx` commit `7dbc5b5322a6ef3fb04bdc643c64b188fd641149` (Wine 11.16)
- License: the modified Wine source file is LGPL-2.1-or-later; this patch is carried under the same license. Preserve the existing Wine copyright and license header when distributing a built runtime.

The patch is a canary carry of an unmerged Wine draft. Arknights macOS Runtime-specific changes are limited to the explicit `ARKNIGHTS_RUNTIME_AUDIO_FOLLOW_DEFAULT_OUTPUT=1` opt-in, parsed once per process. An absent, malformed, or `0` value leaves the normal Wine endpoint list and stream behavior in place. When enabled, eligible shared render streams are watched: the virtual endpoint follows the current default output, while an explicitly selected endpoint may recover after disconnect and reconnect. Capture and exclusive streams retain their normal behavior.

## Build and test notes

Apply this patch after checking out the exact WineCX pin:

```sh
git apply --check patches/wine/audio/0001-winecoreaudio-default-output.patch
git apply patches/wine/audio/0001-winecoreaudio-default-output.patch
```

The patch adds no third-party dependency. CoreAudio property notifications are reduced to a pthread signal in the HAL callback; retargeting and AudioUnit stop/start work run on a Wine worker thread. The render callback lock is never held across AudioUnit stop or start. Process detach unregisters both HAL listeners, joins the worker, and restores the previous HAL run loop before Wine unloads the driver.

The canary must test both process-environment modes, then switch the macOS default output while an active shared render stream is playing. Confirm that the stream continues on the new output, preserves application volume, and recovers after a device is disconnected and reconnected. A successful compile does not establish upstream compatibility: the source merge request is still a draft and its endpoint-notification semantics may change before upstream acceptance.
