set shell := ["bash", "-euo", "pipefail", "-c"]

uv := "uv run --locked --no-dev"
uv_dev := "uv run --locked"

default:
    @just --list

check:
    {{ uv_dev }} pytest
    {{ uv_dev }} ruff check scripts tests
    {{ uv_dev }} ruff format --check scripts tests
    {{ uv }} scripts/runtime.py validate-lock
    {{ uv }} scripts/release/licenses.py generate --check
    {{ uv }} scripts/release/pins.py check
    {{ uv_dev }} actionlint
    git diff --check

validate:
    {{ uv }} scripts/runtime.py validate-lock

update-pins *args:
    {{ uv }} scripts/release/pins.py update {{ args }}

monitor:
    {{ uv }} scripts/monitor.py --output .build/reports/source-monitor.json

frametime-record case seconds:
    {{ uv }} scripts/frametime.py record "{{ case }}" --seconds "{{ seconds }}"

prepare-arm64:
    {{ uv }} scripts/runtime.py prepare combined --target native-arm64 --all-sources --destination-root .build/stages/arm64/sources

build-arm64:
    scripts/build-arm64.sh

verify-arm64:
    {{ uv }} scripts/validate_runtime.py ".build/stages/arm64/candidate/Libraries" --target native-arm64

prepare stage="combined":
    {{ uv }} scripts/runtime.py prepare "{{ stage }}"

fetch-base:
    {{ uv }} scripts/runtime.py fetch-base

build stage="combined":
    scripts/build-canary.sh "{{ stage }}"

build-release:
    scripts/build-release.sh

verify path=".build/stages/combined/candidate/Libraries":
    {{ uv }} scripts/validate_runtime.py "{{ path }}"
