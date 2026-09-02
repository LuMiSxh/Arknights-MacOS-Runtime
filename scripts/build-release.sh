#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0

set -euo pipefail

repository_root="$(cd "$(dirname "$0")/.." && pwd -P)"
exec "$repository_root/scripts/build-canary.sh" combined --clean-release
