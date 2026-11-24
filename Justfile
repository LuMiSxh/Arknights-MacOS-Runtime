set shell := ["bash", "-euo", "pipefail", "-c"]

uv := "uv run --locked --no-dev"
uv_dev := "uv run --locked"
uv_deltas := "uv run --locked --no-dev --group deltas"

default:
    @just --list

check:
    {{ uv_dev }} --group deltas pytest
    {{ uv_dev }} ruff check scripts tests
    {{ uv_dev }} ruff format --check scripts tests
    {{ uv }} -m scripts lock validate
    {{ uv }} -m scripts pins export --check
    {{ uv }} -m scripts release licenses generate --check
    {{ uv }} -m scripts pins check
    {{ uv_dev }} actionlint
    git diff --check

validate:
    {{ uv }} -m scripts lock validate

# Pin maintenance: `just pins update [--dry-run] [--only COMPONENT]`, `check`, or `export [--check]`.
pins action *args:
    {{ uv }} -m scripts pins {{ action }} {{ args }}

monitor:
    {{ uv }} -m scripts monitor --output .build/reports/source-monitor.json

frametime-record case seconds:
    {{ uv }} -m scripts frametime record "{{ case }}" --seconds "{{ seconds }}"

# Clone the pinned sources of a lane and apply its patches.
prepare lane="rosetta-x86_64" *args:
    {{ uv }} -m scripts lock prepare --target "{{ lane }}" {{ args }}

# Build one lane. The default mode is a candidate; `release` runs the release gates.
build lane="rosetta-x86_64" version="0.0.0-dev" mode="candidate":
    {{ uv }} -m scripts build "{{ mode }}" --target "{{ lane }}" --version "{{ version }}"

# Combine lane output directories into one release under .build/release.
combine version +inputs:
    args=(); for dir in {{ inputs }}; do args+=(--input "$dir"); done; {{ uv }} -m scripts release combine --version "{{ version }}" --output .build/release "${args[@]}"

# Write delta archives from recent releases into a combined release directory.
deltas version dist:
    {{ uv_deltas }} -m scripts release deltas --version "{{ version }}" --dist "{{ dist }}"

verify path=".build/x86_64/candidate/Libraries":
    {{ uv }} -m scripts validate-runtime "{{ path }}"
