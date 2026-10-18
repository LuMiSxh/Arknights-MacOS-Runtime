# Wine build fix for winemac.drv

Renames the static helper `RegCloseKey` in `dlls/winemac.drv/d3dmetal.c` to `macdrv_reg_close_key`. It fixes a compile error in the pinned WineCX source. See the [Build patch registry](../../../docs/patch-registry.md#build).

## Why the patch is needed

The pinned source includes `winreg.h` through `macdrv.h`. That header declares `RegCloseKey` as a non-static function. The static definition in `d3dmetal.c` then fails with this error:

```text
error: static declaration of 'RegCloseKey' follows non-static declaration
```

The build of `winemac.so` stops. The patch changes two lines and no behavior.

## Stages

The patch applies in the `audio`, `hardware-cursor`, `ace`, `cef`, `cn`, and `combined` stages. It does not apply in the `performance` stage. That stage builds DXMT against the unpatched base Wine tree.

## Removal

Drop this patch when the pinned WineCX source compiles `winemac.drv` without it.

Apply: `0001-winemac-d3dmetal-static-regclosekey.patch` to the pinned WineCX source.
