#!/usr/bin/env bash
# Prepared inventory only: run on HOME after the active experiment closes.
# It does not train, publish, promote or queue anything.
set -Eeuo pipefail

DEFAULT=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw
SOURCE=${MASTER_CORPUS_LOCAL_PATH:-$DEFAULT}
OUT=${MASTER_CORPUS_PREFLIGHT_OUT:-master-corpus-preflight.json}

[ -f "$SOURCE" ] || {
  echo "missing full sequential corpus: $SOURCE" >&2
  echo "The Git fallback remains available, but contains only 13,266 games." >&2
  exit 2
}

python3 - "$SOURCE" "$OUT" <<'PY'
import hashlib
import json
import pathlib
import struct
import sys

source, out = map(pathlib.Path, sys.argv[1:3])
raw = source.read_bytes()
if len(raw) < 8 or raw[:4] != b"JNNW":
    raise SystemExit("not JNNW")
records = struct.unpack_from("<I", raw, 4)[0]
if len(raw) != 8 + records * 38:
    raise SystemExit("JNNW size/count mismatch")
start = struct.pack(
    "<QQQQB",
    sum(1 << (sq - 1) for sq in range(31, 51)),
    0,
    sum(1 << (sq - 1) for sq in range(1, 21)),
    0,
    0,
)
games = sum(
    raw[offset:offset + 33] == start
    for offset in range(8, len(raw), 38)
)
payload = {
    "schema": 1,
    "operation": "master-corpus-preflight",
    "source": str(source),
    "size_bytes": len(raw),
    "records": records,
    "start_position_game_boundaries": games,
    "sha256": hashlib.sha256(raw).hexdigest(),
    "scientific_output": False,
    "promotion_authorized": False,
    "automatic_next_job": None,
}
out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
print(json.dumps(payload, sort_keys=True))
PY
