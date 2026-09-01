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
	{{ uv_dev }} actionlint
	git diff --check

validate:
	{{ uv }} scripts/runtime.py validate-lock

prepare stage="combined":
	{{ uv }} scripts/runtime.py prepare "{{stage}}"

fetch-base:
	{{ uv }} scripts/runtime.py fetch-base

build stage="combined":
	scripts/build-canary.sh "{{stage}}"

verify path=".build/stages/combined/candidate/Libraries":
	{{ uv }} scripts/validate_runtime.py "{{path}}"
