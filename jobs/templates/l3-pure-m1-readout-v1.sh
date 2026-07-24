#!/usr/bin/env bash
set -Eeuo pipefail

: "${M1_EVAL_PREFIX:?}"
REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
W="${JASS_RUN_DIR:-$PWD/.run}/work"
ART="${JASS_RUN_DIR:-$PWD/.run}/artefacts"
mkdir -p "$W" "$ART"

python3 -m py_compile \
  jobs/tools/fetch_result_files.py \
  jobs/tools/l3_pure_m1_readout.py

python3 jobs/tools/fetch_result_files.py \
  --prefix "$M1_EVAL_PREFIX" \
  --expected-state completed \
  --file artefacts/m1-evaluation.json=m1-evaluation.json \
  --out-dir "$W/input" \
  --report "$ART/verified-m1-evaluation.json"

python3 jobs/tools/l3_pure_m1_readout.py \
  --input "$W/input/m1-evaluation.json" \
  --out "$ART/m1-readout.json" \
  --marker-dir "$ART"

cp "$ART/m1-readout.json" "$ART/JASS_CONTROL_SUMMARY.json"
