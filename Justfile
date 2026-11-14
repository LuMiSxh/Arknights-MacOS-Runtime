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

# Build one lane as a candidate. The default version is a SemVer prerelease.
build target="rosetta-x86_64" version="0.0.0-dev":
    {{ uv }} scripts/build.py candidate --target "{{ target }}" --version "{{ version }}"

# Build one lane as a gated release artifact.
build-release target version:
    {{ uv }} scripts/build.py release --target "{{ target }}" --version "{{ version }}"

# Combine lane output directories into one release under .build/release.
combine version +inputs:
    args=(); for dir in {{ inputs }}; do args+=(--input "$dir"); done; {{ uv }} scripts/release/combine.py --version "{{ version }}" --output .build/release "${args[@]}"

verify path=".build/x86_64/candidate/Libraries":
    {{ uv }} scripts/validate_runtime.py "{{ path }}"
