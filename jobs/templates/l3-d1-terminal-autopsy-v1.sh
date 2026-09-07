#!/usr/bin/env bash
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_STAGE_SPEC:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"; GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$IN" "$ART" "$GEOM"
RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }

D_JOB="cpx62-1849-l3-decision-math-d1-wdl-listwise-fit-stage-env-recovery-requeue-v1"
D_ATTEMPT="20260906T222203Z-08fd187a"
D_CODE="08fd187aa187f26bd7179df2c68056a74e28355d"
D_ROOT="r2:jass-data/runs/$D_JOB/$D_ATTEMPT"
C_JOB="cpx62-1845-l3-decision-math-c-sibling-dataset-v2-v1"
C_ATTEMPT="20260906T191758Z-4ae3fca8"
C_CODE="4ae3fca82f19338132911811978761b91bd39573"
C_ROOT="r2:jass-data/runs/$C_JOB/$C_ATTEMPT"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"; PY="$VENV/bin/python"

finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  (cd "$W" && find . -maxdepth 1 -name '*.log' -type f -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.feat "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

SPEC_CODE=$(python3 - "$JASS_STAGE_SPEC" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['code_sha'])
PY
)
[ "$(git rev-parse HEAD)" = "$SPEC_CODE" ] || die "stage spec / HEAD mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX62 contract mismatch"
[ -x "$PY" ] || die "numeric venv missing"

say "D1 terminal autopsy start job=$JASS_JOB_ID code=$SPEC_CODE fits=0 games=0"

# Terminal D1 artefacts only. No new fit, no WDL relabel and no full-ladder input.
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$D_ROOT" \
  --file artefacts/WDL_CONTROL-fit.json=WDL_CONTROL-fit.json \
  --file artefacts/WDL_LISTWISE-fit.json=WDL_LISTWISE-fit.json \
  --file artefacts/WDL_CONTROL.pjtw.gz=WDL_CONTROL.pjtw.gz \
  --file artefacts/WDL_LISTWISE.pjtw.gz=WDL_LISTWISE.pjtw.gz \
  --file artefacts/D1_TRANSFER_READOUT.json=D1_TRANSFER_READOUT.json \
  --file artefacts/scientific-summary.json=scientific-summary.json \
  --file artefacts/D1_DECISION_GROUPS.json=D1_DECISION_GROUPS.json \
  --out-dir "$IN" --report "$ART/verified-d1-terminal.json" >"$W/fetch-d1.log" 2>&1
cmp "$IN/D1_TRANSFER_READOUT.json" "$IN/scientific-summary.json" || die "D1 terminal summary/readout drift"

# C is used only to reconstruct exact child positions and static features.
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$C_ROOT" \
  --file artefacts/sibling-dataset-v2.jsonl=c-dataset.jsonl \
  --file artefacts/sibling-dataset-v2-manifest.json=c-manifest.json \
  --file artefacts/scientific-summary.json=c-summary.json \
  --out-dir "$IN" --report "$ART/verified-c.json" >"$W/fetch-c.log" 2>&1

"$PY" - "$ART/verified-d1-terminal.json" "$ART/verified-c.json" "$IN" \
  "$D_JOB" "$D_ATTEMPT" "$D_CODE" "$C_JOB" "$C_ATTEMPT" "$C_CODE" <<'PY'
import hashlib,json,sys
vd,vc,root,dj,da,dc,cj,ca,cc=sys.argv[1:]
D=json.load(open(vd)); C=json.load(open(vc)); root=root.rstrip('/')
if (D.get('job_id'),D.get('attempt_id'),D.get('code_sha'),D.get('result_state')) != (dj,da,dc,'completed'):
 raise SystemExit('D1 terminal identity drift')
if (C.get('job_id'),C.get('attempt_id'),C.get('code_sha'),C.get('result_state')) != (cj,ca,cc,'completed'):
 raise SystemExit('C identity drift')
r=json.load(open(root+'/D1_TRANSFER_READOUT.json'))
if r.get('verdict')!='D1_DECISION_TRANSFER_NOT_ESTABLISHED_V1' or r.get('next_stage')!='STOP' or r.get('equal_node_gate_authorized') is not False:
 raise SystemExit('D1 terminal failure contract drift')
cs=json.load(open(root+'/c-summary.json')); cm=json.load(open(root+'/c-manifest.json'))
if cs.get('verdict')!='C_SIBLING_DATASET_V2_AUTHENTICATED_V1' or cs.get('parents')!=4000 or cs.get('actions')!=38053:
 raise SystemExit('C terminal contract drift')
sha=hashlib.sha256(open(root+'/c-dataset.jsonl','rb').read()).hexdigest()
if cm.get('dataset',{}).get('sha256')!=sha: raise SystemExit('C dataset SHA drift')
PY

gunzip -c "$IN/WDL_CONTROL.pjtw.gz" >"$W/WDL_CONTROL.pjtw"
gunzip -c "$IN/WDL_LISTWISE.pjtw.gz" >"$W/WDL_LISTWISE.pjtw"

"$PY" jobs/tools/d1_decision_prepare.py --dataset "$IN/c-dataset.jsonl" \
  --out-jnnw "$W/decision-children.jnnw" --out-groups "$W/reconstructed-groups.json" \
  --out-receipt "$ART/D1_AUTOPSY_DECISION_PREPARE.json" >"$W/decision-prepare.log" 2>&1
cmp "$W/reconstructed-groups.json" "$IN/D1_DECISION_GROUPS.json" || die "D1 decision-group reconstruction drift"

python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
J="$W/build/jass"
timeout 1800s "$J" --dump-eval-features "$W/decision-children.jnnw" "$W/decision.feat" >"$W/features-decision.log" 2>&1

env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools:." \
  "$PY" jobs/tools/d1_terminal_autopsy.py \
    --control-fit "$IN/WDL_CONTROL-fit.json" --listwise-fit "$IN/WDL_LISTWISE-fit.json" \
    --readout "$IN/D1_TRANSFER_READOUT.json" \
    --decision-data "$W/decision-children.jnnw" --decision-feat "$W/decision.feat" \
    --decision-groups "$IN/D1_DECISION_GROUPS.json" \
    --control-model "$W/WDL_CONTROL.pjtw" --listwise-model "$W/WDL_LISTWISE.pjtw" \
    --out "$ART/D1_TERMINAL_AUTOPSY.json" >"$W/autopsy.log" 2>&1
cp "$ART/D1_TERMINAL_AUTOPSY.json" "$ART/scientific-summary.json"

"$PY" - "$ART/D1_TERMINAL_AUTOPSY.json" "$RES" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); s=r['decision']['by_split']; w=r['wdl']
with open(sys.argv[2],'a') as f:
 f.write(f"verdict={r['verdict']}\n")
 f.write(f"classification={r['classification']}\n")
 for split in ('train','valid','test'):
  f.write(f"{split}_delta_ce={s[split]['delta_ce_mean']:.9f} improved={s[split]['fraction_improved']:.6f} catastrophic={s[split]['catastrophic_regression_rate_delta_lt_minus1']:.6f}\n")
 f.write(f"delta_wdl={w['delta_wdl']:.9f} tolerance={w['noninferiority_tolerance']:.6f}\n")
 f.write("fits=0 model_searches=0 teacher_searches=0 strength_games=0 promotions=0 bakes=0 equal_node=false\n")
PY
say "D1 terminal autopsy complete"
