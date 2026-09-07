#!/usr/bin/env bash
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"; : "${JASS_STAGE_SPEC:?}"
: "${JASS_JOB_ID:?}"; : "${D4B_MICRO_GO:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART" "$W/teacher" "$W/roots" "$ART/teacher-reports"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"; : >"$RES"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }; phase(){ echo "$1" >"$STAGE"; say "phase=$1"; }
MON=""
monitor(){ (t0=$(date +%s); while true; do
  done_shards=$(find "$W/teacher" -name 's*-report.json' -type f 2>/dev/null | wc -l)
  { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"; printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)";
    printf 'elapsed_min=%d\nteacher_shards_done=%s/8\nroots=512\nteacher_nodes_per_root=20000\nfits_max=1\nnew_scan_searches=0\nstrength_games=0\n' "$((($(date +%s)-t0)/60))" "$done_shards";
  } >"$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 60; done) & MON="$!"; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt" 2>/dev/null || true; (cd "$W" && find . -maxdepth 2 -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true; exit "$rc"; }
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
[ "$D4B_MICRO_GO" = 1 ] || die "D4b GO missing"

D4_JOB="cpx62-1862-l3-decision-math-d4-search-utility-offline-cardinality-recovery-requeue-v1"; D4_ATTEMPT="20260907T182914Z-1c779cc8"; D4_CODE="1c779cc87608a12b26432cad6a23872aeb5eabe8"; D4_ROOT="r2:jass-data/runs/$D4_JOB/$D4_ATTEMPT"
D1_JOB="cpx62-1849-l3-decision-math-d1-wdl-listwise-fit-stage-env-recovery-requeue-v1"; D1_ATTEMPT="20260906T222203Z-08fd187a"; D1_CODE="08fd187aa187f26bd7179df2c68056a74e28355d"; D1_ROOT="r2:jass-data/runs/$D1_JOB/$D1_ATTEMPT"
MODEL_SHA="e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0"
G0_JOB="cpx62-1864-l3-scan-oracle-gate0-d3-retrospective-v1"; G0_ATTEMPT="20260907T195559Z-8782aed3"; G0_CODE="8782aed342938ecaa9cee10fc51a875fad55ffee"; G0_ROOT="r2:jass-data/runs/$G0_JOB/$G0_ATTEMPT"
SEL_JOB="home-1651-l3-scan-ceiling-selection-v1"; SEL_ATTEMPT="20260829T133348Z-28e12fba"; SEL_CODE="28e12fba0ead14def244ffc442b15937f65edc0e"; SEL_ROOT="r2:jass-data/runs/$SEL_JOB/$SEL_ATTEMPT"
SCAN_JOB="home-1657-l3-scan-ceiling-scan-base-v1"; SCAN_ATTEMPT="20260829T144418Z-46623b26"; SCAN_CODE="46623b26b8d684f5685475d81fbb36f215ba4ac2"; SCAN_ROOT="r2:jass-data/runs/$SCAN_JOB/$SCAN_ATTEMPT"

monitor; say "D4b micro start code=$SPEC_CODE max_teacher_nodes=10240000 max_gate0_candidate_nodes=10240000 strength_games=0"
phase authenticate
python3 jobs/tools/fetch_result_files.py --prefix "$D4_ROOT" --expected-state failed --file artefacts/d4-search-utility-roots.tsv=d4-roots.tsv --file artefacts/d4-root-pool-provenance.json=d4-roots-provenance.json --out-dir "$IN" --report "$ART/verified-d4-roots.json" >"$W/fetch-d4.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$D1_ROOT" --expected-state completed --file artefacts/WDL_CONTROL.pjtw.gz=WDL_CONTROL.pjtw.gz --out-dir "$IN" --report "$ART/verified-d1.json" >"$W/fetch-d1.log" 2>&1
gunzip -c "$IN/WDL_CONTROL.pjtw.gz" >"$W/WDL_CONTROL.pjtw"; [ "$(sha256sum "$W/WDL_CONTROL.pjtw"|awk '{print $1}')" = "$MODEL_SHA" ] || die "WDL_CONTROL drift"
"$PY" - "$ART/verified-d4-roots.json" "$ART/verified-d1.json" "$IN/d4-roots-provenance.json" "$D4_JOB" "$D4_ATTEMPT" "$D4_CODE" "$D1_JOB" "$D1_ATTEMPT" "$D1_CODE" <<'PY'
import json,sys
r1=json.load(open(sys.argv[1]));r2=json.load(open(sys.argv[2]));p=json.load(open(sys.argv[3]));vals=sys.argv[4:]
if (r1.get('job_id'),r1.get('attempt_id'),r1.get('code_sha'),r1.get('result_state'))!=(vals[0],vals[1],vals[2],'failed'): raise SystemExit('D4 source drift')
if (r2.get('job_id'),r2.get('attempt_id'),r2.get('code_sha'),r2.get('result_state'))!=(vals[3],vals[4],vals[5],'completed'): raise SystemExit('D1 source drift')
if p.get('selected_roots')!=4000: raise SystemExit('D4 root provenance drift')
PY

phase select-roots
"$PY" jobs/tools/d4b_search_utility_micro.py select --roots "$IN/d4-roots.tsv" --out "$ART/d4b-roots.tsv" --report "$ART/d4b-root-selection.json" >"$W/select.log" 2>&1
"$PY" jobs/tools/d4b_search_utility_micro.py shard --roots "$ART/d4b-roots.tsv" --shards 8 --out-dir "$W/roots" >"$W/shard.log" 2>&1

phase teacher-build
mkdir -p "$W/teacher-src"; git archive HEAD | tar -x -C "$W/teacher-src"
"$PY" "$W/teacher-src/jobs/tools/d4b_search_utility_trace_render.py" --root "$W/teacher-src" >"$W/render-teacher.log" 2>&1
cmake -S "$W/teacher-src" -B "$W/teacher-build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/teacher-cmake.log" 2>&1
cmake --build "$W/teacher-build" -j16 --target d4_search_utility_trace_export >"$W/teacher-build.log" 2>&1

phase teacher
pids=()
for i in 00 01 02 03 04 05 06 07; do
  (unset JASS_D3_RUNTIME_ADAPTER JASS_D3_RUNTIME_BASE_MODEL JASS_D4B_RUNTIME_MODEL JASS_DENSE_REMAP JASS_DSSD_MOVE_ORDER_POLICY JASS_EGDB_CACHE_MB JASS_EGDB_MTC_PATH JASS_EGDB_PATH JASS_NO_SCAN_ACC JASS_SEARCH_PARAMS JASS_T3_F6_MODEL JASS_TB_MOVE_ORDER_POLICY JASS_TRACE_ROOT || true
   timeout 1200s "$W/teacher-build/d4_search_utility_trace_export" "$W/roots/s${i}-roots.tsv" "$W/teacher/s${i}-events.jsonl" "$W/teacher/s${i}-report.json" "$W/WDL_CONTROL.pjtw" "$SPEC_CODE" "$MODEL_SHA" >"$W/teacher-s${i}.log" 2>&1) & pids+=("$!")
done
for p in "${pids[@]}"; do wait "$p"; done
reports=(); teachers=(); for i in 00 01 02 03 04 05 06 07; do reports+=(--report-in "$W/teacher/s${i}-report.json"); teachers+=(--teacher "$W/teacher/s${i}-events.jsonl"); cp "$W/teacher/s${i}-report.json" "$ART/teacher-reports/s${i}-report.json"; done
"$PY" jobs/tools/d4b_search_utility_micro.py aggregate "${reports[@]}" --code-sha "$SPEC_CODE" --model-sha256 "$MODEL_SHA" --out "$ART/d4b-teacher-aggregate.json" >"$W/aggregate.log" 2>&1

phase prepare
set +e
if "$PY" jobs/tools/d4b_search_utility_micro.py prepare --roots "$IN/d4-roots.tsv" "${teachers[@]}" --train "$W/train.jsonl" --valid "$W/valid.jsonl" --test "$W/test.jsonl" --report "$ART/d4b-prepare.json" >"$W/prepare.log" 2>&1; then prep_rc=0; else prep_rc=$?; fi
set -e
if [ "$prep_rc" -eq 4 ]; then
  "$PY" - "$ART/d4b-prepare.json" "$SPEC_CODE" "$ART/scientific-summary.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1])); out={'schema':'jass.d4b.micro_terminal.v1','verdict':'D4B_MICRO_OFFLINE_INVALID_V1','code_sha':sys.argv[2],'prepare':p,'teacher_searches':512,'new_scan_searches':0,'fits':0,'strength_games':0,'selfplay_games':0,'strength_authorized':False,'next_stage':'STOP_D4B_MICRO_INVALID'}
open(sys.argv[3],'w').write(json.dumps(out,indent=2,sort_keys=True)+'\n')
PY
  printf 'D4B_MICRO_OFFLINE_INVALID_V1\n' >"$ART/VERDICT__D4B_MICRO_OFFLINE_INVALID_V1"; say "D4b support invalid; stop before fit"; exit 0
fi
[ "$prep_rc" -eq 0 ] || die "D4b prepare technical rc=$prep_rc"

phase fit
"$PY" jobs/tools/d4b_search_utility_micro.py fit --train "$W/train.jsonl" --model "$ART/D4B_MODEL.npy" --report "$ART/d4b-fit.json" >"$W/fit.log" 2>&1
phase offline-readout
"$PY" jobs/tools/d4b_search_utility_micro.py readout --model "$ART/D4B_MODEL.npy" --valid "$W/valid.jsonl" --test "$W/test.jsonl" --prepare-report "$ART/d4b-prepare.json" --fit-report "$ART/d4b-fit.json" --teacher-report "$ART/d4b-teacher-aggregate.json" --wdl-sha256 "$MODEL_SHA" --report "$ART/d4b-offline-readout.json" >"$W/offline-readout.log" 2>&1
OFFLINE=$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/d4b-offline-readout.json")
if [ "$OFFLINE" != D4B_MICRO_OFFLINE_SUPPORTED_V1 ]; then
  "$PY" - "$ART/d4b-offline-readout.json" "$SPEC_CODE" "$ART/scientific-summary.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1])); out={'schema':'jass.d4b.micro_terminal.v1','verdict':p['verdict'],'code_sha':sys.argv[2],'offline':p,'teacher_searches':512,'new_scan_searches':0,'fits':1,'strength_games':0,'selfplay_games':0,'strength_authorized':False,'next_stage':'STOP_D4B_MICRO'}
open(sys.argv[3],'w').write(json.dumps(out,indent=2,sort_keys=True)+'\n')
PY
  printf '%s\n' "$OFFLINE" >"$ART/VERDICT__${OFFLINE}"; say "$OFFLINE; stop before Scan Gate0"; exit 0
fi

phase gate0-authenticate
python3 jobs/tools/fetch_result_files.py --prefix "$G0_ROOT" --expected-state completed --file artefacts/gate0-parent-ids.txt=gate0-parent-ids.txt --file artefacts/gate0-control.tsv=gate0-control.tsv --out-dir "$IN" --report "$ART/verified-gate0-1864.json" >"$W/fetch-gate0.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$SEL_ROOT" --expected-state completed --file artefacts/parents.jnnw.gz=parents.jnnw.gz --file artefacts/siblings.tsv=siblings.tsv --out-dir "$IN" --report "$ART/verified-scan-selection.json" >"$W/fetch-selection.log" 2>&1
scan_fetch=(); for i in $(seq -w 0 15); do scan_fetch+=(--file "artefacts/scores/scan-base-shard-${i}-scores.tsv.gz=scan-${i}.tsv.gz"); done
python3 jobs/tools/fetch_result_files.py --prefix "$SCAN_ROOT" --expected-state completed "${scan_fetch[@]}" --out-dir "$IN" --report "$ART/verified-scan-oracle.json" >"$W/fetch-scan.log" 2>&1
gunzip -c "$IN/parents.jnnw.gz" >"$W/parents.jnnw"

phase gate0-build
mkdir -p "$W/gate0-src"; git archive HEAD | tar -x -C "$W/gate0-src"
"$PY" "$W/gate0-src/jobs/tools/d4b_gate0_render.py" --root "$W/gate0-src" >"$W/gate0-render.log" 2>&1
cmake -S "$W/gate0-src" -B "$W/gate0-build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/gate0-cmake.log" 2>&1
cmake --build "$W/gate0-build" -j16 --target jass_scan_oracle_gate0_runtime >"$W/gate0-build.log" 2>&1

phase gate0-candidate
unset JASS_D3_RUNTIME_ADAPTER JASS_D3_RUNTIME_BASE_MODEL JASS_DSSD_MOVE_ORDER_POLICY JASS_TB_MOVE_ORDER_POLICY JASS_T3_F6_MODEL || true
export JASS_D4B_RUNTIME_MODEL="$ART/D4B_MODEL.npy"
timeout 1200s "$W/gate0-build/jass_scan_oracle_gate0_runtime" "$W/parents.jnnw" "$IN/gate0-parent-ids.txt" "$ART/d4b-gate0-candidate.tsv" "$ART/d4b-gate0-runtime-report.json" "$W/WDL_CONTROL.pjtw" - 20000 D4B >"$W/gate0-candidate.log" 2>&1
unset JASS_D4B_RUNTIME_MODEL
scan_read=(); for i in $(seq -w 0 15); do scan_read+=(--scan-score "$IN/scan-${i}.tsv.gz"); done
"$PY" jobs/tools/scan_oracle_gate0_readout.py --groups "$IN/siblings.tsv" --ids "$IN/gate0-parent-ids.txt" "${scan_read[@]}" --control "$IN/gate0-control.tsv" --candidate "$ART/d4b-gate0-candidate.tsv" --candidate-name D4B --out "$ART/d4b-gate0-readout.json" >"$W/gate0-readout.log" 2>&1

phase terminal
"$PY" - "$ART/d4b-offline-readout.json" "$ART/d4b-gate0-readout.json" "$ART/d4b-gate0-runtime-report.json" "$SPEC_CODE" "$ART/scientific-summary.json" <<'PY'
import json,sys
o,g,r=map(lambda p:json.load(open(p)),sys.argv[1:4]); code,out=sys.argv[4:]
if o.get('verdict')!='D4B_MICRO_OFFLINE_SUPPORTED_V1': raise SystemExit('offline authorization drift')
if int(r.get('d4b_eligible_nodes',0))<=0: raise SystemExit('D4b runtime not exercised')
supported=g.get('gate',{}).get('verdict')=='GATE0_SUPPORTED'
verdict='D4B_MICRO_GATE0_SUPPORTED_V1' if supported else 'D4B_MICRO_GATE0_NOT_SUPPORTED_V1'
res={'schema':'jass.d4b.micro_terminal.v1','verdict':verdict,'code_sha':code,'offline':o,'scan_gate0':g,'runtime':r,'teacher_searches':512,'teacher_nodes_per_root':20000,'new_scan_searches':0,'fits':1,'strength_games':0,'selfplay_games':0,'strength_authorized':False,'fresh_confirmation_required_before_strength':True,'next_stage':'D4B_FRESH_GATE0_CONFIRMATION' if supported else 'STOP_D4B_MICRO'}
open(out,'w').write(json.dumps(res,indent=2,sort_keys=True)+'\n')
print(verdict)
PY
VERDICT=$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/scientific-summary.json")
printf '%s\n' "$VERDICT" >"$ART/VERDICT__${VERDICT}"; printf '0\n' >"$ART/STRENGTH_GAMES__0"; printf 'false\n' >"$ART/STRENGTH_AUTHORIZED__FALSE"
say "D4b complete verdict=$VERDICT new_scan_searches=0 strength_games=0"
