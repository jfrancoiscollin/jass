#!/usr/bin/env bash
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"; : "${JASS_STAGE_SPEC:?}"
: "${JASS_JOB_ID:?}"; : "${SCAN_ORACLE_VARIANTS_GO:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART" "$ART/variants"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
phase(){ echo "$1" >"$STAGE"; say "phase=$1"; }
MON=""
monitor(){ (t0=$(date +%s); while true; do
  done_n=$(find "$ART/variants" -name '*-readout.json' -type f 2>/dev/null | wc -l)
  { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')";
    printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)";
    printf 'elapsed_min=%d\n' "$((($(date +%s)-t0)/60))";
    printf 'variants_done=%s/6\n' "$done_n";
    printf 'scan_searches_planned=0\nparents=512\nnodes_per_candidate_parent=20000\nstrength_games=0\n';
  } >"$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120;
done) & MON="$!"; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt" 2>/dev/null || true
  (cd "$W" && find . -maxdepth 2 -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/src" "$W/build" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "TECHNICAL_ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"; PY="$VENV/bin/python"
[ -x "$PY" ] || die "numeric venv missing"
SPEC_CODE=$("$PY" - "$JASS_STAGE_SPEC" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['code_sha'])
PY
)
[ "$(git rev-parse HEAD)" = "$SPEC_CODE" ] || die "stage spec / HEAD mismatch"
[ "$(hostname)" = cpx62 ] || die "Gate0 variants must run on cpx62"
[ "$(nproc)" -eq 16 ] || die "cpx62 nproc drift"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree must be detached and clean"
[ "$SCAN_ORACLE_VARIANTS_GO" = 1 ] || die "variant screen GO missing"
unset JASS_D3_RUNTIME_ADAPTER JASS_D3_RUNTIME_BASE_MODEL JASS_DSSD_MOVE_ORDER_POLICY JASS_TB_MOVE_ORDER_POLICY JASS_T3_F6_MODEL JASS_SEARCH_PARAMS || true

G0_JOB="cpx62-1864-l3-scan-oracle-gate0-d3-retrospective-v1"
G0_ATTEMPT="20260907T195559Z-8782aed3"
G0_CODE="8782aed342938ecaa9cee10fc51a875fad55ffee"
G0_ROOT="r2:jass-data/runs/$G0_JOB/$G0_ATTEMPT"
SEL_JOB="home-1651-l3-scan-ceiling-selection-v1"
SEL_ATTEMPT="20260829T133348Z-28e12fba"
SEL_CODE="28e12fba0ead14def244ffc442b15937f65edc0e"
SEL_ROOT="r2:jass-data/runs/$SEL_JOB/$SEL_ATTEMPT"
SCAN_JOB="home-1657-l3-scan-ceiling-scan-base-v1"
SCAN_ATTEMPT="20260829T144418Z-46623b26"
SCAN_CODE="46623b26b8d684f5685475d81fbb36f215ba4ac2"
SCAN_ROOT="r2:jass-data/runs/$SCAN_JOB/$SCAN_ATTEMPT"
D1_JOB="cpx62-1849-l3-decision-math-d1-wdl-listwise-fit-stage-env-recovery-requeue-v1"
D1_ATTEMPT="20260906T222203Z-08fd187a"
D1_CODE="08fd187aa187f26bd7179df2c68056a74e28355d"
D1_ROOT="r2:jass-data/runs/$D1_JOB/$D1_ATTEMPT"
MODEL_SHA="e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0"

say "Gate0 search variants start job=$JASS_JOB_ID code=$SPEC_CODE variants=6 scan_searches=0 games=0"
monitor
phase authenticate-frozen-gate0-and-oracle
python3 jobs/tools/fetch_result_files.py --prefix "$G0_ROOT" --expected-state completed \
  --file artefacts/gate0-parent-ids.txt=gate0-parent-ids.txt \
  --file artefacts/gate0-control.tsv=gate0-control.tsv \
  --file artefacts/gate0-control-report.json=gate0-control-report.json \
  --file artefacts/scan-oracle-gate0-readout.json=d3-gate0-readout.json \
  --file artefacts/gate0-selection.json=gate0-selection.json \
  --out-dir "$IN" --report "$ART/verified-gate0-1864.json" >"$W/fetch-gate0.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$SEL_ROOT" --expected-state completed \
  --file artefacts/parents.jnnw.gz=parents.jnnw.gz \
  --file artefacts/siblings.tsv=siblings.tsv \
  --out-dir "$IN" --report "$ART/verified-selection.json" >"$W/fetch-selection.log" 2>&1
scan_fetch=()
for i in $(seq -w 0 15); do scan_fetch+=(--file "artefacts/scores/scan-base-shard-${i}-scores.tsv.gz=scan-${i}.tsv.gz"); done
python3 jobs/tools/fetch_result_files.py --prefix "$SCAN_ROOT" --expected-state completed \
  "${scan_fetch[@]}" --out-dir "$IN" --report "$ART/verified-scan.json" >"$W/fetch-scan.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$D1_ROOT" --expected-state completed \
  --file artefacts/WDL_CONTROL.pjtw.gz=WDL_CONTROL.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-d1.json" >"$W/fetch-d1.log" 2>&1

gunzip -c "$IN/parents.jnnw.gz" >"$W/parents.jnnw"
gunzip -c "$IN/WDL_CONTROL.pjtw.gz" >"$W/WDL_CONTROL.pjtw"
[ "$(sha256sum "$W/WDL_CONTROL.pjtw" | awk '{print $1}')" = "$MODEL_SHA" ] || die "WDL_CONTROL byte drift"
"$PY" - "$ART/verified-gate0-1864.json" "$ART/verified-selection.json" "$ART/verified-scan.json" "$ART/verified-d1.json" \
 "$G0_JOB" "$G0_ATTEMPT" "$G0_CODE" "$SEL_JOB" "$SEL_ATTEMPT" "$SEL_CODE" \
 "$SCAN_JOB" "$SCAN_ATTEMPT" "$SCAN_CODE" "$D1_JOB" "$D1_ATTEMPT" "$D1_CODE" <<'PY'
import json,sys
reports=[json.load(open(p)) for p in sys.argv[1:5]]; ids=sys.argv[5:]
expected=[tuple(ids[i:i+3]) for i in range(0,len(ids),3)]
for r,e in zip(reports,expected):
 got=(r.get('job_id'),r.get('attempt_id'),r.get('code_sha'),r.get('result_state'))
 if got != (*e,'completed'): raise SystemExit(f'provenance drift {got} != {e}')
d3=json.load(open(sys.argv[1].replace('verified-gate0-1864.json','../inputs/d3-gate0-readout.json'))) if False else None
PY
"$PY" - "$IN/d3-gate0-readout.json" "$IN/gate0-parent-ids.txt" <<'PY'
import json,sys
p=json.load(open(sys.argv[1])); ids=[x for x in open(sys.argv[2]) if x.strip()]
if p.get('gate',{}).get('verdict')!='GATE0_NOT_SUPPORTED' or p.get('parents')!=512 or len(ids)!=512:
 raise SystemExit('1864 Gate0 baseline drift')
if p.get('guards',{}).get('scan_searches')!=0 or p.get('guards',{}).get('strength_games')!=0:
 raise SystemExit('1864 guard drift')
PY

phase isolated-build
mkdir -p "$W/src"
git archive HEAD | tar -x -C "$W/src"
"$PY" "$W/src/jobs/tools/scan_oracle_gate0_render.py" --cmake "$W/src/CMakeLists.txt"
cmake -S "$W/src" -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass_scan_oracle_gate0_search_variants >"$W/build.log" 2>&1

scan_read=(); for i in $(seq -w 0 15); do scan_read+=(--scan-score "$IN/scan-${i}.tsv.gz"); done
ARMS=(J1_SCAN_VERIFY J2_SCAN_THREAT_REENTRY J3_SCAN_SINGLE_REPLY J4_SCAN_LMR J5_SCAN_ORDERING J6_NO_NULL_MOVE)
for arm in "${ARMS[@]}"; do
  phase "score-$arm"
  timeout 1200s "$W/build/jass_scan_oracle_gate0_search_variants" \
    "$W/parents.jnnw" "$IN/gate0-parent-ids.txt" "$ART/variants/$arm.tsv" \
    "$ART/variants/$arm-report.json" "$W/WDL_CONTROL.pjtw" "$arm" 20000 \
    >"$W/$arm.log" 2>&1
  phase "readout-$arm"
  "$PY" jobs/tools/scan_oracle_gate0_readout.py --groups "$IN/siblings.tsv" --ids "$IN/gate0-parent-ids.txt" \
    "${scan_read[@]}" --control "$IN/gate0-control.tsv" --candidate "$ART/variants/$arm.tsv" \
    --candidate-name "$arm" --out "$ART/variants/$arm-readout.json" >"$W/$arm-readout.log" 2>&1
done

phase aggregate
"$PY" - "$IN/d3-gate0-readout.json" "$ART" "$SPEC_CODE" <<'PY'
import json,sys
from pathlib import Path
baseline_path=Path(sys.argv[1]); art=Path(sys.argv[2]); code=sys.argv[3]
arms=['J1_SCAN_VERIFY','J2_SCAN_THREAT_REENTRY','J3_SCAN_SINGLE_REPLY','J4_SCAN_LMR','J5_SCAN_ORDERING','J6_NO_NULL_MOVE']
baseline=json.load(open(baseline_path))
rows={}; survivors=[]; actual_nodes=0
for arm in arms:
 r=json.load(open(art/'variants'/f'{arm}-readout.json'))
 rep=json.load(open(art/'variants'/f'{arm}-report.json'))
 if r.get('parents')!=512 or r.get('scan_reference_nodes')!=200000:
  raise SystemExit(f'{arm} readout contract drift')
 if rep.get('processed_rows')!=512 or rep.get('scan_searches')!=0 or rep.get('strength_games')!=0:
  raise SystemExit(f'{arm} report guard drift')
 actual_nodes += int(rep['nodes'])
 rows[arm]={'gate':r['gate'],'paired':r['paired'],'control':r['control'],'candidate':r['candidate'],'runtime_report':rep}
 if r['gate']['verdict']=='GATE0_SUPPORTED': survivors.append(arm)
 elif r['gate']['verdict']!='GATE0_NOT_SUPPORTED': raise SystemExit(f'{arm} unknown verdict')
out={
 'schema':'jass.scan_oracle_gate0_search_variants_terminal.v1',
 'verdict':'GATE0_VARIANT_SURVIVORS_FOUND' if survivors else 'GATE0_NO_VARIANT_SURVIVORS',
 'code_sha':code,'parents':512,'candidate_arms':arms,'survivors':survivors,
 'exploratory_screen_only':True,'multiple_comparisons':6,
 'fresh_confirmation_required_before_strength':True,'strength_authorized':False,
 'd3_retrospective_baseline':baseline,'variants':rows,
 'planned_candidate_nodes':6*512*20000,'actual_candidate_nodes':actual_nodes,
 'guards':{'new_scan_searches':0,'fits':0,'strength_games':0,'selfplay_games':0,'promotions':0,'bakes':0}
}
(art/'scientific-summary.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(json.dumps({'verdict':out['verdict'],'survivors':survivors,'actual_candidate_nodes':actual_nodes},sort_keys=True))
PY
VERDICT=$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/scientific-summary.json")
printf '%s\n' "$VERDICT" >"$ART/VERDICT__${VERDICT}"
printf '0\n' >"$ART/SCAN_SEARCHES__0"; printf '0\n' >"$ART/STRENGTH_GAMES__0"
printf 'false\n' >"$ART/STRENGTH_AUTHORIZED__FALSE"; printf 'false\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"
phase complete
say "Gate0 search variants complete verdict=$VERDICT scan_searches=0 strength_games=0"
