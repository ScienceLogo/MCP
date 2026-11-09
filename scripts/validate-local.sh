#!/usr/bin/env bash
set -eu

# Lint, then build the image and run the tests inside it.
# CONTAINER selects the container tool (default: docker; podman works too).
ruff check .
ruff format --check .
"${CONTAINER:-docker}" build --target test .
