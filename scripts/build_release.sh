#!/usr/bin/env bash
# Build the release ZIP with only allowed files (K10).
# Excludes: .git, .venv, __pycache__, .idea, .env, secrets, weights, builds,
# videos, PDFs, large data.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:-0.1.0}"
OUT="${ROOT}/dist/alfagen-pii-guard-${VERSION}.zip"

rm -rf "${ROOT}/dist"
mkdir -p "${ROOT}/dist"

# Stage allowed files into a temp dir.
STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT

# Copy source, tests, configs, docs (text only).
cp -R "${ROOT}/app" "${STAGE}/app"
cp -R "${ROOT}/tests" "${STAGE}/tests"
cp -R "${ROOT}/benchmarks" "${STAGE}/benchmarks"
cp -R "${ROOT}/docs" "${STAGE}/docs"
cp "${ROOT}/Dockerfile" "${STAGE}/"
cp "${ROOT}/docker-compose.yml" "${STAGE}/"
cp "${ROOT}/docker-compose.dental.yml" "${STAGE}/"
cp "${ROOT}/docker-compose.load.yml" "${STAGE}/"
cp "${ROOT}/requirements.txt" "${STAGE}/"
cp "${ROOT}/README.md" "${STAGE}/"
cp "${ROOT}/AGENTS.md" "${STAGE}/"
cp "${ROOT}/.dockerignore" "${STAGE}/"

# Remove non-source artifacts from the stage.
find "${STAGE}" -name "__pycache__" -type d -prune -exec rm -rf {} +
find "${STAGE}" -name "*.pyc" -delete
find "${STAGE}" -name ".DS_Store" -delete
# Remove PDFs and binary docs from the stage (not allowed in ZIP).
find "${STAGE}/docs" -name "*.pdf" -delete
find "${STAGE}/docs" -name "*.txt" -delete
# Remove the container list (contains server info, not needed in ZIP).
rm -f "${STAGE}/docs/dental-containers-before.txt"

# Build the ZIP.
cd "${STAGE}"
zip -r "${OUT}" . > /dev/null

echo "Built ${OUT}"
echo "Contents:"
unzip -l "${OUT}" | tail -5
echo "Size: $(du -h "${OUT}" | cut -f1)"