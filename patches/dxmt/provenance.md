# DXMT patch provenance

## Source pin

- Upstream: [3Shain/dxmt](https://github.com/3Shain/dxmt)
- DXMT commit: <!-- pin:dxmt.commit|code -->`9839e55f98d4aca103957ee4132d6395a325a9ed`<!-- /pin -->
- DXMT version: <!-- pin:dxmt.describe|code -->`v0.80-361-g9839e55`<!-- /pin -->
  (unreleased post-<!-- pin:dxmt.tag -->0.80<!-- /pin --> canary)
- License: LGPL-2.1-or-later, matching the pinned DXMT revision and the modified
  source files

## 0001 Release present statistics

Original runtime optimization by the runtime maintainers. It is not ported from
another project.

The patch changes the DXMT present path only. It keeps the frame counters,
per-frame measurements, and debug HUD unchanged, and gates only the
release-dead aggregation and presentation update work.
