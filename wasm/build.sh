#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
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

# Drop a copy of the demo page next to the artefacts so it is reachable
# under the same origin when the user serves the build directory.
cp "${ROOT_DIR}/wasm/example.html" "${BUILD_DIR}/example.html" 2>/dev/null || true

echo
echo "To try the demo:"
echo "  python3 -m http.server --directory ${BUILD_DIR} 8080"
echo "  then open http://localhost:8080/example.html"
