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

set +e
python3 jobs/tools/fetch_result_files.py \
  --prefix "$M1_EVAL_PREFIX" \
  --expected-state completed \
  --file artefacts/m1-evaluation.json=m1-evaluation.json \
  --out-dir "$W/input" \
  --report "$ART/verified-m1-evaluation.json" \
  >"$ART/fetch.stdout.log" 2>"$ART/fetch.stderr.log"
fetch_rc=$?
set -e
if [ "$fetch_rc" -ne 0 ]; then
  rclone lsf "$M1_EVAL_PREFIX" --recursive \
    >"$ART/remote-lsf.txt" 2>"$ART/remote-lsf.stderr.log" || true
  python3 - "$ART/fetch.stderr.log" "$ART" <<'PY'
import re,sys
from pathlib import Path
source=Path(sys.argv[1]); art=Path(sys.argv[2])
lines=[line.strip() for line in source.read_text(errors="replace").splitlines() if line.strip()]
message=lines[-1] if lines else "UNKNOWN"
safe=re.sub(r"[^A-Za-z0-9]+","_",message).strip("_")[:160] or "UNKNOWN"
(art/f"FETCH_ERROR__{safe}").write_text(message+"\n",encoding="utf-8")
PY
  exit "$fetch_rc"
fi

python3 jobs/tools/l3_pure_m1_readout.py \
  --input "$W/input/m1-evaluation.json" \
  --out "$ART/m1-readout.json" \
  --marker-dir "$ART"

cp "$ART/m1-readout.json" "$ART/JASS_CONTROL_SUMMARY.json"
