#!/usr/bin/env bash
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"; : "${JASS_STAGE_SPEC:?}"
: "${JASS_JOB_ID:?}"; : "${D4C_POST_TEACHER_RECOVERY_GO:?}"
export PYTHONPATH="$JASS_CODE_DIR${PYTHONPATH:+:$PYTHONPATH}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART" "$W/teacher"
RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "TECHNICAL_ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

PY="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}/bin/python"; [ -x "$PY" ] || die "numeric venv missing"
"$PY" -c 'import numpy,scipy' || die "numeric venv lacks numpy/scipy"
SPEC_CODE=$("$PY" - "$JASS_STAGE_SPEC" <<'PY'
import json,sys; print(json.load(open(sys.argv[1]))['code_sha'])
PY
)
[ "$(git rev-parse HEAD)" = "$SPEC_CODE" ] || die "stage spec / HEAD mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX62 resource drift"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree must be detached/clean"
[ "$D4C_POST_TEACHER_RECOVERY_GO" = 1 ] || die "D4c post-teacher recovery GO missing"

SRC_JOB="cpx62-1870-l3-d4c-rank-breaker-micro-screen-recovery-v1"
SRC_ATTEMPT="20260908T054613Z-346c46a2"; SRC_CODE="346c46a2f39fe2a22cd6f175b455b5072629e583"
SRC_ROOT="r2:jass-data/runs/$SRC_JOB/$SRC_ATTEMPT"
D4_JOB="cpx62-1862-l3-decision-math-d4-search-utility-offline-cardinality-recovery-requeue-v1"
D4_ATTEMPT="20260907T182914Z-1c779cc8"; D4_CODE="1c779cc87608a12b26432cad6a23872aeb5eabe8"
D4_ROOT="r2:jass-data/runs/$D4_JOB/$D4_ATTEMPT"
D1_JOB="cpx62-1849-l3-decision-math-d1-wdl-listwise-fit-stage-env-recovery-requeue-v1"; D1_ATTEMPT="20260906T222203Z-08fd187a"; D1_ROOT="r2:jass-data/runs/$D1_JOB/$D1_ATTEMPT"
MODEL_SHA="e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0"
G0_JOB="cpx62-1864-l3-scan-oracle-gate0-d3-retrospective-v1"; G0_ATTEMPT="20260907T195559Z-8782aed3"; G0_ROOT="r2:jass-data/runs/$G0_JOB/$G0_ATTEMPT"
SEL_JOB="home-1651-l3-scan-ceiling-selection-v1"; SEL_ATTEMPT="20260829T133348Z-28e12fba"; SEL_ROOT="r2:jass-data/runs/$SEL_JOB/$SEL_ATTEMPT"
SCAN_JOB="home-1657-l3-scan-ceiling-scan-base-v1"; SCAN_ATTEMPT="20260829T144418Z-46623b26"; SCAN_ROOT="r2:jass-data/runs/$SCAN_JOB/$SCAN_ATTEMPT"

say "D4c post-teacher recovery code=$SPEC_CODE new_teacher_searches=0 strength_games=0"

# Authenticate the failed 1870 bundle, then recover the already-computed teacher events.
python3 jobs/tools/fetch_result_files.py --prefix "$SRC_ROOT" --expected-state failed --inventory-only \
  --out-dir "$IN" --report "$ART/verified-1870-inventory.json" >"$W/inventory-1870.log" 2>&1
"$PY" - "$ART/verified-1870-inventory.json" "$SRC_JOB" "$SRC_ATTEMPT" "$SRC_CODE" <<'PY'
import json,sys
p=json.load(open(sys.argv[1])); job,attempt,code=sys.argv[2:]
if (p.get('job_id'),p.get('attempt_id'),p.get('code_sha'),p.get('result_state'))!=(job,attempt,code,'failed'):
    raise SystemExit('1870 source identity drift')
paths={x['path'] for x in p.get('files',[])}
need={'artefacts/d4c-teacher-aggregate.json'}|{f'work/teacher/s{i:02d}-events.jsonl' for i in range(8)}
missing=sorted(need-paths)
if missing: raise SystemExit('1870 teacher payload not recoverable: '+','.join(missing))
PY
teacher_fetch=(--file artefacts/d4c-teacher-aggregate.json=d4c-teacher-aggregate.json)
for i in 00 01 02 03 04 05 06 07; do teacher_fetch+=(--file "work/teacher/s${i}-events.jsonl=teacher/s${i}-events.jsonl"); done
python3 jobs/tools/fetch_result_files.py --prefix "$SRC_ROOT" --expected-state failed "${teacher_fetch[@]}" \
  --out-dir "$IN" --report "$ART/verified-1870-teacher.json" >"$W/fetch-1870-teacher.log" 2>&1

# Prepare must validate selected events against the sealed 4000-root D4 manifest, not the 512-root D4b subset.
python3 jobs/tools/fetch_result_files.py --prefix "$D4_ROOT" --expected-state failed \
  --file artefacts/d4-search-utility-roots.tsv=d4-roots-4000.tsv \
  --out-dir "$IN" --report "$ART/verified-d4-roots-4000.json" >"$W/fetch-d4-roots.log" 2>&1
"$PY" - "$ART/verified-d4-roots-4000.json" "$D4_JOB" "$D4_ATTEMPT" "$D4_CODE" <<'PY'
import json,sys
p=json.load(open(sys.argv[1])); job,attempt,code=sys.argv[2:]
if (p.get('job_id'),p.get('attempt_id'),p.get('code_sha'),p.get('result_state'))!=(job,attempt,code,'failed'):
    raise SystemExit('D4 root source identity drift')
PY
teachers=(); for i in 00 01 02 03 04 05 06 07; do teachers+=(--teacher "$IN/teacher/s${i}-events.jsonl"); done
set +e
if "$PY" jobs/tools/d4b_search_utility_micro.py prepare --roots "$IN/d4-roots-4000.tsv" "${teachers[@]}" \
  --train "$W/train.jsonl" --valid "$W/valid.jsonl" --test "$W/test.jsonl" --report "$ART/d4c-prepare.json" >"$W/prepare.log" 2>&1; then prep_rc=0; else prep_rc=$?; fi
set -e
if [ "$prep_rc" -eq 4 ]; then
  "$PY" - "$ART/d4c-prepare.json" "$SPEC_CODE" "$ART/scientific-summary.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1])); out={'schema':'jass.d4c.micro_terminal.v1','verdict':'D4C_RANK_BREAKER_OFFLINE_INVALID_V1','code_sha':sys.argv[2],'prepare':p,'teacher_searches_reused':512,'new_teacher_searches':0,'new_scan_searches':0,'fits':0,'strength_games':0,'selfplay_games':0,'strength_authorized':False,'next_stage':'STOP_D4C_INVALID'}
open(sys.argv[3],'w').write(json.dumps(out,indent=2,sort_keys=True)+'\n')
PY
  printf 'D4C_RANK_BREAKER_OFFLINE_INVALID_V1\n' >"$ART/VERDICT__D4C_RANK_BREAKER_OFFLINE_INVALID_V1"; say "D4c support invalid after corrected root validation"; exit 0
fi
[ "$prep_rc" -eq 0 ] || die "D4c prepare technical rc=$prep_rc"

"$PY" jobs/tools/d4c_rank_breaker.py fit --train "$W/train.jsonl" --model "$ART/D4C_MODEL.npy" --report "$ART/d4c-fit.json" >"$W/fit.log" 2>&1
"$PY" jobs/tools/d4c_rank_breaker.py readout --model "$ART/D4C_MODEL.npy" --valid "$W/valid.jsonl" --test "$W/test.jsonl" \
  --prepare-report "$ART/d4c-prepare.json" --fit-report "$ART/d4c-fit.json" --teacher-report "$IN/d4c-teacher-aggregate.json" \
  --report "$ART/d4c-offline-readout.json" >"$W/offline-readout.log" 2>&1
OFFLINE=$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/d4c-offline-readout.json")
if [ "$OFFLINE" != D4C_RANK_BREAKER_OFFLINE_SUPPORTED_V1 ]; then
  "$PY" - "$ART/d4c-offline-readout.json" "$SPEC_CODE" "$ART/scientific-summary.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1])); out={'schema':'jass.d4c.micro_terminal.v1','verdict':p['verdict'],'code_sha':sys.argv[2],'offline':p,'teacher_searches_reused':512,'new_teacher_searches':0,'new_scan_searches':0,'fits':1,'strength_games':0,'selfplay_games':0,'strength_authorized':False,'next_stage':'STOP_D4C_OFFLINE'}
open(sys.argv[3],'w').write(json.dumps(out,indent=2,sort_keys=True)+'\n')
PY
  printf '%s\n' "$OFFLINE" >"$ART/VERDICT__${OFFLINE}"; say "$OFFLINE; stop before Scan Gate0"; exit 0
fi

# Offline survived: run only the candidate side of the already-frozen Scan Gate0.
python3 jobs/tools/fetch_result_files.py --prefix "$D1_ROOT" --expected-state completed --file artefacts/WDL_CONTROL.pjtw.gz=WDL_CONTROL.pjtw.gz --out-dir "$IN" --report "$ART/verified-d1.json" >"$W/fetch-d1.log" 2>&1
gunzip -c "$IN/WDL_CONTROL.pjtw.gz" >"$W/WDL_CONTROL.pjtw"; [ "$(sha256sum "$W/WDL_CONTROL.pjtw"|awk '{print $1}')" = "$MODEL_SHA" ] || die "WDL_CONTROL drift"
python3 jobs/tools/fetch_result_files.py --prefix "$G0_ROOT" --expected-state completed --file artefacts/gate0-parent-ids.txt=gate0-parent-ids.txt --file artefacts/gate0-control.tsv=gate0-control.tsv --out-dir "$IN" --report "$ART/verified-gate0-1864.json" >"$W/fetch-gate0.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$SEL_ROOT" --expected-state completed --file artefacts/parents.jnnw.gz=parents.jnnw.gz --file artefacts/siblings.tsv=siblings.tsv --out-dir "$IN" --report "$ART/verified-scan-selection.json" >"$W/fetch-selection.log" 2>&1
scan_fetch=(); for i in $(seq -w 0 15); do scan_fetch+=(--file "artefacts/scores/scan-base-shard-${i}-scores.tsv.gz=scan-${i}.tsv.gz"); done
python3 jobs/tools/fetch_result_files.py --prefix "$SCAN_ROOT" --expected-state completed "${scan_fetch[@]}" --out-dir "$IN" --report "$ART/verified-scan-oracle.json" >"$W/fetch-scan.log" 2>&1
gunzip -c "$IN/parents.jnnw.gz" >"$W/parents.jnnw"

mkdir -p "$W/gate0-src"; git archive HEAD | tar -x -C "$W/gate0-src"
"$PY" "$W/gate0-src/jobs/tools/d4c_gate0_render.py" --root "$W/gate0-src" >"$W/gate0-render.log" 2>&1
cmake -S "$W/gate0-src" -B "$W/gate0-build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/gate0-cmake.log" 2>&1
cmake --build "$W/gate0-build" -j16 --target jass_scan_oracle_gate0_runtime >"$W/gate0-build.log" 2>&1
unset JASS_D3_RUNTIME_ADAPTER JASS_D3_RUNTIME_BASE_MODEL JASS_D4B_RUNTIME_MODEL JASS_DSSD_MOVE_ORDER_POLICY JASS_TB_MOVE_ORDER_POLICY JASS_T3_F6_MODEL || true
export JASS_D4C_RUNTIME_MODEL="$ART/D4C_MODEL.npy"
timeout 1200s "$W/gate0-build/jass_scan_oracle_gate0_runtime" "$W/parents.jnnw" "$IN/gate0-parent-ids.txt" "$ART/d4c-gate0-candidate.tsv" "$ART/d4c-gate0-runtime-report.json" "$W/WDL_CONTROL.pjtw" - 20000 D4C >"$W/gate0-candidate.log" 2>&1
unset JASS_D4C_RUNTIME_MODEL
scan_read=(); for i in $(seq -w 0 15); do scan_read+=(--scan-score "$IN/scan-${i}.tsv.gz"); done
"$PY" jobs/tools/scan_oracle_gate0_readout.py --groups "$IN/siblings.tsv" --ids "$IN/gate0-parent-ids.txt" "${scan_read[@]}" --control "$IN/gate0-control.tsv" --candidate "$ART/d4c-gate0-candidate.tsv" --candidate-name D4C --out "$ART/d4c-gate0-readout.json" >"$W/gate0-readout.log" 2>&1
"$PY" - "$ART/d4c-offline-readout.json" "$ART/d4c-gate0-readout.json" "$ART/d4c-gate0-runtime-report.json" "$SPEC_CODE" "$ART/scientific-summary.json" <<'PY'
import json,sys
o,g,r=map(lambda p:json.load(open(p)),sys.argv[1:4]); code,out=sys.argv[4:]
elig=int(r.get('d4c_eligible_nodes',0)); hoists=int(r.get('d4c_hoists',-1)); ranks=[int(r.get(f'd4c_predicted_rank{i}',-1)) for i in range(1,5)]
if elig<=0 or sum(ranks)!=elig or sum(ranks[1:])!=hoists: raise SystemExit(f'D4c runtime diagnostic drift elig={elig} hoists={hoists} ranks={ranks}')
supported=g.get('gate',{}).get('verdict')=='GATE0_SUPPORTED'
verdict='D4C_RANK_BREAKER_GATE0_SUPPORTED_V1' if supported else 'D4C_RANK_BREAKER_GATE0_NOT_SUPPORTED_V1'
res={'schema':'jass.d4c.micro_terminal.v1','verdict':verdict,'code_sha':code,'offline':o,'scan_gate0':g,'runtime':r,'teacher_searches_reused':512,'new_teacher_searches':0,'new_scan_searches':0,'fits':1,'strength_games':0,'selfplay_games':0,'strength_authorized':False,'fresh_confirmation_required_before_strength':True,'next_stage':'D4C_FRESH_CONFIRMATION_PREREG' if supported else 'STOP_D4C_MICRO'}
open(out,'w').write(json.dumps(res,indent=2,sort_keys=True)+'\n')
print(verdict)
PY
VERDICT=$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/scientific-summary.json")
printf '%s\n' "$VERDICT" >"$ART/VERDICT__${VERDICT}"
printf 'false\n' >"$ART/STRENGTH_AUTHORIZED__FALSE"; printf '0\n' >"$ART/STRENGTH_GAMES__0"
say "$VERDICT new_teacher_searches=0 new_scan_searches=0 strength_games=0"
