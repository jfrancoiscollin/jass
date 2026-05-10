#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Build the Jass engine as a WebAssembly module via Emscripten.
#
# Requires the Emscripten SDK to be activated: `emcmake` and `emmake` must be
# on PATH. See https://emscripten.org/docs/getting_started/downloads.html.
#
# Usage: ./wasm/build.sh [Debug|Release]   (default: Release)

set -euo pipefail

BUILD_TYPE="${1:-Release}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${ROOT_DIR}/build-wasm"

if ! command -v emcmake >/dev/null 2>&1; then
    echo "error: 'emcmake' not found on PATH — install and activate emsdk first." >&2
    exit 1
fi

mkdir -p "${BUILD_DIR}"

emcmake cmake -S "${ROOT_DIR}" -B "${BUILD_DIR}" \
    -DCMAKE_BUILD_TYPE="${BUILD_TYPE}"

emmake cmake --build "${BUILD_DIR}" -j

echo
echo "Build artefacts in ${BUILD_DIR}:"
ls -1 "${BUILD_DIR}"/jass.* 2>/dev/null || true
