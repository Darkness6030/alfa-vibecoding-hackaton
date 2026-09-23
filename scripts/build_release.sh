#!/usr/bin/env bash
# Build a source-only ZIP without deleting previous releases.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python3 scripts/build_release.py "${1:-0.4.0}"
