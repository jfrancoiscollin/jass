#!/usr/bin/env bash
# Paired-seed CTX2 self-play knob attribution. Diagnostic only.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$IN" "$ART/cells" "$GEOM"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

CURRICULUM_ROOT="r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/20260814T191555Z-18c38a33"
CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE_SHA="18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
RECORDS_PER_CELL="${RECORDS_PER_CELL:-250000}"; PRODUCERS="${PRODUCERS:-8}"
LABEL_DEPTH=4; MAXPLIES=260; BASE_SEED=1618033; REPLICATE_SEED=2718281
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
VENV_READY="$VENV/.jass-runtime-ready-v1"
REUSE_PREFIX="${REUSE_PREFIX:-}"
REUSE_CELLS="${REUSE_CELLS:-}"
REUSE_EXPECTED_JOB="${REUSE_EXPECTED_JOB:-}"
REUSE_EXPECTED_ATTEMPT="${REUSE_EXPECTED_ATTEMPT:-}"
REUSE_EXPECTED_CODE_SHA="${REUSE_EXPECTED_CODE_SHA:-}"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

# name       rop eps decay topk margin depth seed
CELLS="${CELLS:-\
BASE          8   8    60    0      0     8 $BASE_SEED
BASEBIS       8   8    60    0      0     8 $REPLICATE_SEED
ROP16        16   8    60    0      0     8 $BASE_SEED
EPS16         8  16    60    0      0     8 $BASE_SEED
DECAY120      8   8   120    0      0     8 $BASE_SEED
NODECAY       8   8     0    0      0     8 $BASE_SEED
TOPK3M30      8   8    60    3     30     8 $BASE_SEED
DEPTH10       8   8    60    0      0    10 $BASE_SEED}"

MON=""
monitor(){
  ( t0=$(date +%s)
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        printf 'cells_done=%s\n' "$(find "$ART/cells" -name '*-activation.json' 2>/dev/null | wc -l || true)"
      } >"$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 120
    done ) &
  MON="$!"
}
finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$W/cells" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^home-([0-9]+)-l3-context2-knob-attribution-v1$ ]] || die "invalid job nomenclature"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "explicit execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" != cpx62 ] && [ "$(nproc)" -eq 16 ] || die "Home 16-CPU contract mismatch"
[ "$PRODUCERS" -ge 1 ] && [ "$PRODUCERS" -le 12 ] || die "producer count outside [1,12]"
[ "$RECORDS_PER_CELL" -ge 100000 ] || die "attribution cells too small"
[ -f "$VENV_READY" ] || die "persistent numeric runtime absent; do not reinstall"
PY="$VENV/bin/python"; "$PY" -c 'import numpy; assert numpy.__version__'
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 10240 ] || die "less than 10 GiB free ($DFA MiB)"
say "host=$(hostname) records_per_cell=$RECORDS_PER_CELL producers=$PRODUCERS cells=8"
monitor

stage repository-contracts-and-champion
python3 -m py_compile jobs/tools/l3_context2_activation_census.py tools/selfplay_frontier.py
"$PY" -m unittest jobs.tests.test_l3_context2_activation_census \
  jobs.tests.test_l3_context2_knob_attribution_template >"$W/tests.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=curriculum-summary.json \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" >"$W/fetch.log" 2>&1
"$PY" - "$ART/verified-curriculum.json" "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" "$CURRICULUM_CODE_SHA" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
if (r.get('job_id'),r.get('attempt_id'),r.get('code_sha')) != tuple(sys.argv[2:5]):
 raise SystemExit('CURRICULUM identity drift')
if r.get('result_state')!='completed' or r.get('exit_code')!=0: raise SystemExit('CURRICULUM state drift')
PY
gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
[ "$(sha256sum "$W/curriculum.pjtw" | awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM hash drift"

if [ -n "$REUSE_PREFIX" ]; then
  stage fetch-authenticated-completed-cells
  [ -n "$REUSE_CELLS" ] && [ -n "$REUSE_EXPECTED_JOB" ] && \
    [ -n "$REUSE_EXPECTED_ATTEMPT" ] && [ -n "$REUSE_EXPECTED_CODE_SHA" ] ||
    die "incomplete reused-cell identity contract"
  reuse_args=()
  for NAME in $REUSE_CELLS; do
    reuse_args+=(--file "artefacts/cells/$NAME-activation.json=$NAME-activation.json")
    reuse_args+=(--file "artefacts/cells/$NAME-activation.csv=$NAME-activation.csv")
    reuse_args+=(--file "artefacts/cells/$NAME-activation.md=$NAME-activation.md")
    reuse_args+=(--file "artefacts/cells/$NAME-merge.json=$NAME-merge.json")
  done
  timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$REUSE_PREFIX" \
    "${reuse_args[@]}" --out-dir "$IN/reused-cells" \
    --expected-state failed \
    --report "$ART/verified-reused-cells.json" >"$W/fetch-reused-cells.log" 2>&1
  "$PY" - "$ART/verified-reused-cells.json" "$REUSE_EXPECTED_JOB" \
    "$REUSE_EXPECTED_ATTEMPT" "$REUSE_EXPECTED_CODE_SHA" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
if (r.get('job_id'),r.get('attempt_id'),r.get('code_sha')) != tuple(sys.argv[2:5]):
 raise SystemExit('reused-cell source identity drift')
if r.get('result_state')!='failed' or r.get('exit_code')!=6:
 raise SystemExit('reused-cell source state drift')
PY
  for NAME in $REUSE_CELLS; do
    cp "$IN/reused-cells/$NAME-activation.json" "$ART/cells/$NAME-activation.json"
    cp "$IN/reused-cells/$NAME-activation.csv" "$ART/cells/$NAME-activation.csv"
    cp "$IN/reused-cells/$NAME-activation.md" "$ART/cells/$NAME-activation.md"
    cp "$IN/reused-cells/$NAME-merge.json" "$ART/cells/$NAME-merge.json"
  done
fi

stage build-identical-exact-fold-tempo-engine
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
  -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass jass_tests >"$W/build.log" 2>&1
"$W/build/jass_tests" >"$W/cpp-tests.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "missing jass binary"
printf 'hello\nquit\n' | timeout 60s "$J" --pattern "$W/curriculum.pjtw" >"$W/load.log" 2>&1
grep -q '^ready' "$W/load.log" || die "CURRICULUM cannot be loaded"

stage matched-one-factor-selfplay-cells
mkdir -p "$W/cells"
: >"$W/cell-specs.tsv"
while read -r NAME ROP EPS DECAY TOPK MARGIN DEPTH SEED; do
  [ -n "${NAME:-}" ] || continue
  echo "cell-$NAME" >"$STAGE"
  if [ -f "$ART/cells/$NAME-activation.json" ]; then
    "$PY" - "$ART/cells/$NAME-activation.json" "$RECORDS_PER_CELL" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); expected=int(sys.argv[2])
if r['population']['positions']!=expected: raise SystemExit('reused cell record count drift')
if r['phase']['recomposition_max_absolute_error']>1e-5: raise SystemExit('reused phase recomposition drift')
PY
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$NAME" "$ROP" "$EPS" "$DECAY" "$TOPK" "$MARGIN" "$DEPTH" "$SEED" >>"$W/cell-specs.tsv"
    say "cell=$NAME reused from authenticated failed source before its NODECAY abort"
    continue
  fi
  CELL="$W/cells/$NAME"; mkdir -p "$CELL"
  base=$((RECORDS_PER_CELL / PRODUCERS)); rem=$((RECORDS_PER_CELL % PRODUCERS))
  pids=(); pairs=()
  for shard in $(seq 0 $((PRODUCERS-1))); do
    count="$base"; [ "$shard" -lt "$rem" ] && count=$((count+1))
    data="$CELL/s$shard.jnnw"; meta="$CELL/s$shard.jsm"
    ( timeout 3600s "$J" --gen-data-wdl "$count" "$data" \
        "$LABEL_DEPTH" "$DEPTH" "$MAXPLIES" $((SEED+shard)) \
        --nnue "$W/curriculum.pjtw" --search-params-play "$Q00" --wdl-zero-score \
        --random-open-plies "$ROP" --explore-eps "$EPS" --explore-decay-plies "$DECAY" \
        --explore-topk "$TOPK" --explore-margin "$MARGIN" --split-selfplay-rngs \
        --pair-openings --drop-plycap --sample-meta-out "$meta" --sample-meta-format jsm2 \
        >"$CELL/s$shard.log" 2>&1 < /dev/null ) &
    pids+=("$!"); pairs+=(--pair "$data" "$meta")
  done
  bad=0
  for pid in "${pids[@]}"; do if ! wait "$pid"; then bad=$((bad+1)); fi; done
  [ "$bad" -eq 0 ] || die "$NAME: $bad producer failures"
  for log in "$CELL"/s*.log; do
    grep -q 'label_score_searches=0' "$log" || die "$NAME: score-label search in $log"
    grep -q 'split_selfplay_rngs=1' "$log" || die "$NAME: split RNGs inactive in $log"
  done
  "$PY" tools/selfplay_frontier.py merge "${pairs[@]}" --renamespace-nested \
    --no-wdl-check \
    --out-data "$CELL/cell.jnnw" --out-meta "$CELL/cell.jsm" \
    --manifest "$ART/cells/$NAME-merge.json" >"$CELL/merge.log" 2>&1
  timeout 3600s "$J" --dump-conditional-context-v2 \
    "$CELL/cell.jnnw" "$CELL/cell.ctx2.feat" >"$CELL/dump.log" 2>&1
  timeout 3600s "$PY" jobs/tools/l3_context2_activation_census.py analyze \
    --data "$CELL/cell.jnnw" --meta "$CELL/cell.jsm" --feat "$CELL/cell.ctx2.feat" \
    --material-threshold 1e-6 --rare-threshold 1e-3 --rank-rows 100000 \
    --report "$ART/cells/$NAME-activation.json" \
    --csv "$ART/cells/$NAME-activation.csv" \
    --markdown "$ART/cells/$NAME-activation.md" >"$CELL/analyse.log" 2>&1
  "$PY" - "$ART/cells/$NAME-activation.json" "$RECORDS_PER_CELL" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); expected=int(sys.argv[2])
if r['population']['positions']!=expected: raise SystemExit('cell record count drift')
if r['phase']['recomposition_max_absolute_error']>1e-5: raise SystemExit('phase recomposition drift')
PY
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$NAME" "$ROP" "$EPS" "$DECAY" "$TOPK" "$MARGIN" "$DEPTH" "$SEED" >>"$W/cell-specs.tsv"
  rm -f "$CELL"/*.jnnw "$CELL"/*.jsm "$CELL"/*.feat
  say "cell=$NAME ready"
done <<<"$CELLS"

stage attribute-parameter-effects-against-seed-noise
args=()
while read -r NAME _; do args+=(--cell "$NAME=$ART/cells/$NAME-activation.json"); done <"$W/cell-specs.tsv"
"$PY" jobs/tools/l3_context2_activation_census.py compare \
  "${args[@]}" --baseline BASE --replicate BASEBIS \
  --report "$ART/context2-knob-attribution.json" >"$W/compare.log" 2>&1

"$PY" - "$ART" "$W/cell-specs.tsv" "$EXPECTED_CODE_SHA" "$RECORDS_PER_CELL" "$REUSE_CELLS" <<'PY'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); specs=Path(sys.argv[2]); code=sys.argv[3]; records=int(sys.argv[4])
attribution=json.load(open(art/'context2-knob-attribution.json'))
cells={line.split('\t',1)[0]:json.load(open(art/'cells'/(line.split('\t',1)[0]+'-activation.json')))
 for line in specs.read_text().splitlines() if line.strip()}
base=cells['BASE']['population']['wdl_stm_rates']; base_draw=base['0']
guards={}
for name,row in cells.items():
 rates=row['population']['wdl_stm_rates']; skew=abs(rates['1']-rates['-1'])
 draw_shift=abs(rates['0']-base_draw)/base_draw if base_draw else 0.0
 absolute_wdl_pass=0.10<=rates['0']<=0.60 and skew<=0.10
 relative_draw_pass=name in ('BASE','BASEBIS') or draw_shift<=0.30
 guards[name]={'wdl_side_skew':skew,'draw_rate':rates['0'],'relative_draw_shift_vs_base':draw_shift,
  'absolute_wdl_band_passed':absolute_wdl_pass,'relative_draw_shift_passed':relative_draw_pass,
  'passed':absolute_wdl_pass and relative_draw_pass}
effects=[]
for row in attribution['effects']:
 noise=row['baseline_replicate_noise_percentage_points']; delta=row['activation_delta_percentage_points']
 threshold=max(2*noise,0.05)
 effects.append(row|{'influence_threshold_percentage_points':threshold,
  'established_beyond_seed_noise':abs(delta)>threshold and guards[row['cell']]['passed']})
established=[row for row in effects if row['established_beyond_seed_noise']]
payload={'schema':'jass.l3_context2_knob_attribution_job.v1',
 'verdict':'JASS_CONTEXT2_KNOB_ATTRIBUTION_READY','code_sha':code,
 'parent':{'label':'CURRICULUM','raw_sha256':'319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1'},
 'records_per_cell':records,'cells':list(cells),'guards':guards,'effects':effects,
 'reused_cells':sys.argv[5].split() if len(sys.argv)>5 else [],
 'established_parameter_component_effects':established,
 'primary_output':'parameter_x_base_signal_activation_effect_matrix',
 'diagnostic_only':True,'fits_run':0,'force_games_played':0,'frozen_read':False,
 'promotion_authorized':False,'automatic_next_job':None}
open(art/'JASS_CONTROL_SUMMARY.json','w').write(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/'VERDICT__JASS_CONTEXT2_KNOB_ATTRIBUTION_READY').touch()
(art/'PROMOTION_AUTHORIZED__FALSE').write_text('false\n')
(art/'AUTOMATIC_NEXT_JOB__NULL').write_text('null\n')
PY
say "JASS_CONTEXT2_KNOB_ATTRIBUTION_READY cells=8 records_per_cell=$RECORDS_PER_CELL diagnostic=true promotion=false"
