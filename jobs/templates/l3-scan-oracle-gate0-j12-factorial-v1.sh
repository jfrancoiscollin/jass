#!/usr/bin/env bash
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"; : "${JASS_STAGE_SPEC:?}"
: "${JASS_JOB_ID:?}"; : "${J12_FACTORIAL_GO:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART" "$ART/arms"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"; : >"$RES"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }; phase(){ echo "$1" >"$STAGE"; say "phase=$1"; }
MON=""
monitor(){ (t0=$(date +%s); while true; do
  done_arms=$(find "$ART/arms" -name '*-report.json' -type f 2>/dev/null | wc -l)
  { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"; printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)";
    printf 'elapsed_min=%d\narms_done=%s/4\nparents=512\nphases=128x4\nnodes_per_parent_arm=20000\nmax_jass_nodes=40960000\nnew_scan_searches=0\nstrength_games=0\n' "$((($(date +%s)-t0)/60))" "$done_arms";
  } >"$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 60; done) & MON="$!"; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt" 2>/dev/null || true; (cd "$W" && find . -maxdepth 2 -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "TECHNICAL_ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

PY="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}/bin/python"; [ -x "$PY" ] || die "numeric venv missing"
"$PY" -c 'import numpy' || die "numeric venv lacks numpy"
SPEC_CODE=$("$PY" - "$JASS_STAGE_SPEC" <<'PY'
import json,sys; print(json.load(open(sys.argv[1]))['code_sha'])
PY
)
[ "$(git rev-parse HEAD)" = "$SPEC_CODE" ] || die "stage spec / HEAD mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX62 resource drift"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree must be detached/clean"
[ "$J12_FACTORIAL_GO" = 1 ] || die "J12 GO missing"

G0_JOB="cpx62-1864-l3-scan-oracle-gate0-d3-retrospective-v1"; G0_ATTEMPT="20260907T195559Z-8782aed3"; G0_ROOT="r2:jass-data/runs/$G0_JOB/$G0_ATTEMPT"
SEL_JOB="home-1651-l3-scan-ceiling-selection-v1"; SEL_ATTEMPT="20260829T133348Z-28e12fba"; SEL_ROOT="r2:jass-data/runs/$SEL_JOB/$SEL_ATTEMPT"
SCAN_JOB="home-1657-l3-scan-ceiling-scan-base-v1"; SCAN_ATTEMPT="20260829T144418Z-46623b26"; SCAN_ROOT="r2:jass-data/runs/$SCAN_JOB/$SCAN_ATTEMPT"
D1_JOB="cpx62-1849-l3-decision-math-d1-wdl-listwise-fit-stage-env-recovery-requeue-v1"; D1_ATTEMPT="20260906T222203Z-08fd187a"; D1_ROOT="r2:jass-data/runs/$D1_JOB/$D1_ATTEMPT"
MOT_JOB="cpx62-1867-l3-scan-oracle-gate0-search-variants-recovery-v1"; MOT_ATTEMPT="20260907T204215Z-6f053f56"; MOT_ROOT="r2:jass-data/runs/$MOT_JOB/$MOT_ATTEMPT"
MODEL_SHA="e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0"

monitor; say "J12 factorial start code=$SPEC_CODE max_jass_nodes=40960000 new_scan_searches=0 strength_games=0"

phase fresh-cohort-inputs
python3 jobs/tools/fetch_result_files.py --prefix "$G0_ROOT" --expected-state completed \
  --file artefacts/gate0-parent-ids.txt=prior-gate0-ids.txt \
  --out-dir "$IN" --report "$ART/verified-1864-exclusion.json" >"$W/fetch-1864.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$SEL_ROOT" --expected-state completed \
  --file artefacts/parents.jnnw.gz=parents.jnnw.gz \
  --file artefacts/siblings.tsv=siblings.tsv \
  --out-dir "$IN" --report "$ART/verified-selection.json" >"$W/fetch-selection.log" 2>&1

phase fresh-cohort-select
"$PY" jobs/tools/scan_oracle_gate0_j12_select.py \
  --groups "$IN/siblings.tsv" --exclude-ids "$IN/prior-gate0-ids.txt" \
  --out-ids "$ART/j12-parent-ids.txt" --report "$ART/j12-selection.json" >"$W/select.log" 2>&1

phase authenticate-motivation-and-oracle
python3 jobs/tools/fetch_result_files.py --prefix "$MOT_ROOT" --expected-state completed \
  --file artefacts/scientific-summary.json=1867-summary.json \
  --out-dir "$IN" --report "$ART/verified-1867.json" >"$W/fetch-1867.log" 2>&1
"$PY" - "$IN/1867-summary.json" <<'PY'
import json,sys,math
s=json.load(open(sys.argv[1]))
if s.get('verdict')!='GATE0_NO_VARIANT_SURVIVORS' or s.get('survivors')!=[]: raise SystemExit('1867 motivation verdict drift')
v=s.get('variants',{})
j1=v.get('J1_SCAN_VERIFY',{}); j2=v.get('J2_SCAN_THREAT_REENTRY',{})
checks=[
 (j1.get('paired',{}).get('mean_regret_improvement'),33.6171875),
 (j1.get('paired',{}).get('median_wall_ratio'),0.9868635693235224),
 (j2.get('paired',{}).get('mean_regret_improvement'),49.240234375),
 (j2.get('paired',{}).get('median_wall_ratio'),1.0512344508771674),
]
for got,want in checks:
 if got is None or not math.isclose(float(got),want,rel_tol=0,abs_tol=1e-12): raise SystemExit(f'1867 motivation metric drift got={got} want={want}')
if not j1.get('observed_activation') or not j2.get('observed_activation'): raise SystemExit('1867 motivation activation drift')
PY
python3 jobs/tools/fetch_result_files.py --prefix "$D1_ROOT" --expected-state completed \
  --file artefacts/WDL_CONTROL.pjtw.gz=WDL_CONTROL.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-d1.json" >"$W/fetch-d1.log" 2>&1
gunzip -c "$IN/WDL_CONTROL.pjtw.gz" >"$W/WDL_CONTROL.pjtw"
[ "$(sha256sum "$W/WDL_CONTROL.pjtw" | awk '{print $1}')" = "$MODEL_SHA" ] || die "WDL_CONTROL drift"
scan_fetch=(); for i in $(seq -w 0 15); do scan_fetch+=(--file "artefacts/scores/scan-base-shard-${i}-scores.tsv.gz=scan-${i}.tsv.gz"); done
python3 jobs/tools/fetch_result_files.py --prefix "$SCAN_ROOT" --expected-state completed "${scan_fetch[@]}" \
  --out-dir "$IN" --report "$ART/verified-scan-oracle.json" >"$W/fetch-scan.log" 2>&1
gunzip -c "$IN/parents.jnnw.gz" >"$W/parents.jnnw"

phase build
mkdir -p "$W/src"; git archive HEAD | tar -x -C "$W/src"
"$PY" "$W/src/jobs/tools/scan_oracle_gate0_j12_render.py" --cmake "$W/src/CMakeLists.txt" >"$W/render.log" 2>&1
cmake -S "$W/src" -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass_scan_oracle_gate0_j12_factorial >"$W/build.log" 2>&1

run_arm(){
  local arm="$1"
  local stem="$2"
  phase "arm-$stem"
  unset JASS_D3_RUNTIME_ADAPTER JASS_D3_RUNTIME_BASE_MODEL JASS_D4B_RUNTIME_MODEL JASS_D4C_RUNTIME_MODEL \
    JASS_DENSE_REMAP JASS_DSSD_MOVE_ORDER_POLICY JASS_EGDB_CACHE_MB JASS_EGDB_MTC_PATH JASS_EGDB_PATH \
    JASS_NO_SCAN_ACC JASS_SEARCH_PARAMS JASS_T3_F6_MODEL JASS_TB_MOVE_ORDER_POLICY JASS_TRACE_ROOT || true
  timeout 1200s "$W/build/jass_scan_oracle_gate0_j12_factorial" \
    "$W/parents.jnnw" "$ART/j12-parent-ids.txt" "$ART/arms/${stem}.tsv" "$ART/arms/${stem}-report.json" \
    "$W/WDL_CONTROL.pjtw" "$arm" 20000 >"$W/${stem}.log" 2>&1
}

run_arm CONTROL control
run_arm J1_SCAN_VERIFY j1
run_arm J2_SCAN_THREAT_REENTRY j2
run_arm J12_SCAN_VERIFY_THREAT_REENTRY j12

phase readout
scan_read=(); for i in $(seq -w 0 15); do scan_read+=(--scan-score "$IN/scan-${i}.tsv.gz"); done
"$PY" jobs/tools/scan_oracle_gate0_j12_readout.py \
  --groups "$IN/siblings.tsv" --ids "$ART/j12-parent-ids.txt" "${scan_read[@]}" \
  --control "$ART/arms/control.tsv" --j1 "$ART/arms/j1.tsv" --j2 "$ART/arms/j2.tsv" --j12 "$ART/arms/j12.tsv" \
  --report-control "$ART/arms/control-report.json" --report-j1 "$ART/arms/j1-report.json" \
  --report-j2 "$ART/arms/j2-report.json" --report-j12 "$ART/arms/j12-report.json" \
  --out "$ART/j12-factorial-readout.json" >"$W/readout.log" 2>&1

phase terminal
"$PY" - "$ART/j12-factorial-readout.json" "$ART/j12-selection.json" "$SPEC_CODE" "$ART/scientific-summary.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); sel=json.load(open(sys.argv[2])); code,out=sys.argv[3:]
if sel.get('overlap_with_prior_gate0')!=0 or sel.get('selected_parents')!=512: raise SystemExit('fresh cohort integrity drift')
verdict=r.get('verdict')
if verdict not in ('J12_FACTORIAL_GATE0_SURVIVOR_V1','J12_FACTORIAL_GATE0_NOT_SUPPORTED_V1'): raise SystemExit('J12 verdict drift')
survivor=verdict=='J12_FACTORIAL_GATE0_SURVIVOR_V1'
summary={
 'schema':'jass.j12_factorial_terminal.v1','verdict':verdict,'code_sha':code,
 'selection':sel,'readout':r,'new_jass_nodes':sum(int(r['readout']['runtime_report']['nodes']) if False else 0 for _ in []),
 'new_scan_searches':0,'fits':0,'strength_games':0,'selfplay_games':0,'promotions':0,'bakes':0,
 'strength_authorized':False,'fresh_disjoint_confirmation_required_before_strength':survivor,
 'next_stage':'J12_FRESH_DISJOINT_CONFIRMATION_PREREG' if survivor else 'STOP_J12_FACTORIAL'
}
# Runtime node total is derived from the four authenticated arm reports embedded in readout.
summary['new_jass_nodes']=int(r['control_runtime_report']['nodes']) + sum(int(r['arms'][a]['runtime_report']['nodes']) for a in ('J1_SCAN_VERIFY','J2_SCAN_THREAT_REENTRY','J12_SCAN_VERIFY_THREAT_REENTRY'))
open(out,'w').write(json.dumps(summary,indent=2,sort_keys=True)+'\n')
print(verdict)
PY
VERDICT=$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/scientific-summary.json")
printf '%s\n' "$VERDICT" >"$ART/VERDICT__${VERDICT}"
printf '0\n' >"$ART/STRENGTH_GAMES__0"
printf 'false\n' >"$ART/STRENGTH_AUTHORIZED__FALSE"
printf '0\n' >"$ART/SCAN_SEARCHES__0"
say "J12 factorial terminal verdict=$VERDICT"
exit 0
