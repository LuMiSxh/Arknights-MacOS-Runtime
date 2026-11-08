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

prepare:
    {{ uv }} scripts/runtime.py prepare

fetch-base:
    {{ uv }} scripts/runtime.py fetch-base

build:
    {{ uv }} scripts/build.py canary

build-release:
    {{ uv }} scripts/build.py release

verify path=".build/runtime/candidate/Libraries":
    {{ uv }} scripts/validate_runtime.py "{{ path }}"

arm64-fetch:
    {{ uv }} scripts/arm64/fetch_external.py --target native-arm64 --output .build/arm64/incoming

arm64-dxmt:
    {{ uv }} scripts/arm64/build_dxmt.py --target native-arm64 --root .build/arm64

arm64-assemble:
    {{ uv }} scripts/arm64/assemble.py --wine .build/arm64/incoming/wine --dxmt .build/arm64/dxmt --output .build/arm64/Libraries

arm64-provenance tag:
    {{ uv }} scripts/arm64/provenance.py --target native-arm64 --tag "{{ tag }}" --runtime-archive ".build/arm64/release/Arknights-MacOS-Runtime-{{ tag }}.tar.gz" --source-archive ".build/arm64/release/Arknights-MacOS-Runtime-{{ tag }}-source.tar.gz" --external-artifact .build/arm64/incoming/external.json --output .build/arm64/release/provenance.json

arm64-verify:
    {{ uv }} scripts/validate_runtime.py .build/arm64/Libraries --target native-arm64
