#!/usr/bin/env bash
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_STAGE_SPEC:?}"; : "${JASS_JOB_ID:?}"; : "${ED1_AUDIT_GO:?}"
cd "$JASS_CODE_DIR"
export PYTHONPATH="$JASS_CODE_DIR"
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$ART/RESULTS.txt"; : >"$RES"
phase(){ printf 'phase=%s time_utc=%s\n' "$1" "$(date -u +%FT%TZ)" | tee -a "$RES"; }
finalize(){
  rc=$?; trap - EXIT ERR; set +e
  if [ "$rc" -ne 0 ]; then
    printf 'ED1 technical failure rc=%s; no scientific verdict\n' "$rc" >>"$RES"
  fi
  exit "$rc"
}
trap finalize EXIT
[ "$ED1_AUDIT_GO" = 1 ]
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ]
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ]
PY="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}/bin/python"
[ -x "$PY" ]; "$PY" -c 'import numpy'
SPEC_CODE=$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["code_sha"])' "$JASS_STAGE_SPEC")
[ "$(git rev-parse HEAD)" = "$SPEC_CODE" ]

phase authenticate-existing-cohorts
A_JOB=cpx62-1864-l3-scan-oracle-gate0-d3-retrospective-v1
A_ATT=20260907T195559Z-8782aed3
B_JOB=cpx62-1872-l3-j12-factorial-gate0-v1
B_ATT=20260908T111609Z-f4a438fd
S_JOB=home-1651-l3-scan-ceiling-selection-v1
S_ATT=20260829T133348Z-28e12fba
Q_JOB=home-1657-l3-scan-ceiling-scan-base-v1
Q_ATT=20260829T144418Z-46623b26
fetch(){
  local job="$1" attempt="$2" receipt="$3"; shift 3
  timeout 300s python3 jobs/tools/fetch_result_files.py \
    --prefix "r2:jass-data/runs/$job/$attempt" --expected-state completed \
    --out-dir "$IN" --report "$ART/$receipt.json" "$@" >"$W/$receipt.log" 2>&1
}
fetch "$A_JOB" "$A_ATT" verified-a --file artefacts/gate0-parent-ids.txt=cohort-a.txt
fetch "$B_JOB" "$B_ATT" verified-b --file artefacts/j12-parent-ids.txt=cohort-b.txt
fetch "$S_JOB" "$S_ATT" verified-groups --file artefacts/siblings.tsv=siblings.tsv
files=(); reads=()
for i in 00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15; do
  files+=(--file "artefacts/scores/scan-base-shard-${i}-scores.tsv.gz=scan-${i}.tsv.gz")
  reads+=(--scan-score "$IN/scan-${i}.tsv.gz")
done
phase authenticate-cached-score-ladder
fetch "$Q_JOB" "$Q_ATT" verified-scan "${files[@]}"
"$PY" - "$ART" "$A_JOB" "$A_ATT" "$B_JOB" "$B_ATT" "$S_JOB" "$S_ATT" "$Q_JOB" "$Q_ATT" <<'PY'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); values=sys.argv[2:]
for name,job,attempt in zip(('a','b','groups','scan'),values[::2],values[1::2]):
    r=json.loads((art/f'verified-{name}.json').read_text())
    if (r.get('job_id'),r.get('attempt_id'),r.get('result_state'),r.get('exit_code')) != (job,attempt,'completed',0):
        raise SystemExit(f'upstream identity/state drift: {name}')
    if not str(r.get('code_sha','')).startswith(attempt.split('-')[-1]):
        raise SystemExit(f'upstream code identity drift: {name}')
PY

phase seal-5k-50k-partial-order-before-200k-audit
"$PY" jobs/tools/ed1_partial_order_audit.py freeze --groups "$IN/siblings.tsv" \
  --cohort-a "$IN/cohort-a.txt" --cohort-b "$IN/cohort-b.txt" "${reads[@]}" \
  --out "$ART/ed1-label-audit-only.json" >"$W/freeze.log" 2>&1
phase audit-at-cached-200k
# No engine executable or model fit is invoked anywhere in this stage.
timeout 600s "$PY" jobs/tools/ed1_partial_order_audit.py audit \
  --labels "$ART/ed1-label-audit-only.json" "${reads[@]}" \
  --out "$ART/ed1-readout.json" --details "$ART/ed1-parent-diagnostics.json" >"$W/audit.log" 2>&1
"$PY" - "$ART" "$SPEC_CODE" "$JASS_JOB_ID" <<'PY'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); p=json.loads((art/'ed1-readout.json').read_text())
p.update(code_sha=sys.argv[2],job_id=sys.argv[3])
with (art/'scientific-summary.json').open('x') as f: json.dump(p,f,indent=2,sort_keys=True,allow_nan=False); f.write('\n')
(art/('VERDICT__'+p['verdict'])).write_text(p['verdict']+'\n')
print(p['verdict'])
PY
phase terminal
printf 'new_scan_searches=0 new_jass_nodes=0 fits=0 strength_games=0 training_allowed=false\n' >>"$RES"
