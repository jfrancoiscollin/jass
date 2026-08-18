#!/usr/bin/env bash
# Generate the preregistered fresh 2M CTX2-Intervention-v1 corpus.
# Generation only: no mapper, PatternEval fit, force game, frozen read or promotion.
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
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; cp "$STAGE" "$ART/STAGE.txt"; }

PLAN_ROOT="r2:jass-data/runs/cpx62-1408-l3-context2-intervention-plan-v1/20260818T182226Z-20fd6621"
PLAN_JOB="cpx62-1408-l3-context2-intervention-plan-v1"
PLAN_ATTEMPT="20260818T182226Z-20fd6621"
PLAN_CODE_SHA="20fd66216dc28c14a8d3e4b258e9fe65bad52351"
CURRICULUM_ROOT="r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/20260814T191555Z-18c38a33"
CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE_SHA="18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
PRODUCERS=12; PREFLIGHT_RECORDS=300; CONTENTION=1.174; MAX_BUDGET_MIN=75
LABEL_DEPTH=4; MAXPLIES=260; FRESH_SEED=2026081805
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

MON=""
monitor(){
  ( t0=$(date +%s)
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        printf 'cells_done=%s\n' "$(find "$ART/cells" -name '*-merge.json' 2>/dev/null | wc -l || true)"
        printf 'current_shards_written=%s\n' "$(find "$W/cells" -name 's*.jnnw' 2>/dev/null | wc -l || true)"
      } >"$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 120
    done ) &
  MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$W/cells" "$W"/*.jnnw "$W"/*.jsm 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-([0-9]+)-l3-context2-intervention-corpus-v1$ ]] || die "invalid job nomenclature"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "explicit execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "persistent numeric runtime absent; do not reinstall"
PY="$VENV/bin/python"; "$PY" -c 'import numpy; assert numpy.__version__'

stage disk-and-repository-contracts
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 10240 ] || die "less than 10 GiB free ($DFA MiB)"
python3 -m py_compile tools/selfplay_frontier.py jobs/tools/assert_corpus_wdl.py \
  jobs/tools/l3_context2_intervention_corpus_audit.py
"$PY" -m unittest jobs.tests.test_l3_context2_intervention_corpus_audit \
  jobs.tests.test_l3_context2_intervention_corpus_template >"$W/tests.log" 2>&1
say "host=cpx62 nproc=16 producers=$PRODUCERS target_records=2000000 eta_preregistered_min=30..75"
monitor

stage fetch-and-authenticate-plan-and-curriculum
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$PLAN_ROOT" \
  --file artefacts/context2-intervention-plan.json=plan.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=plan-summary.json \
  --out-dir "$IN" --report "$ART/verified-plan.json" --expected-state completed >"$W/fetch-plan.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" --expected-state completed >"$W/fetch-curriculum.log" 2>&1
"$PY" - "$ART" "$IN" "$PLAN_JOB" "$PLAN_ATTEMPT" "$PLAN_CODE_SHA" \
  "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" "$CURRICULUM_CODE_SHA" <<'PY'
import json,sys
from pathlib import Path
art,src=map(Path,sys.argv[1:3]); ids=sys.argv[3:]
for name,expected in (
 ('verified-plan.json',tuple(ids[:3])),('verified-curriculum.json',tuple(ids[3:6]))):
 r=json.load(open(art/name)); got=(r.get('job_id'),r.get('attempt_id'),r.get('code_sha'))
 if got!=expected or r.get('result_state')!='completed' or r.get('exit_code')!=0:
  raise SystemExit(f'{name}: source identity/state drift {got}')
p=json.load(open(src/'plan.json'))
expected={'BASE':300000,'ROP16':600000,'EPS16':500000,'DECAY120':100000,'TOPK3M30':100000,'DEPTH10':400000}
if p.get('verdict')!='JASS_CONTEXT2_INTERVENTION_PLAN_READY': raise SystemExit('plan verdict drift')
if p['corpus']['record_quotas']!=expected or sum(expected.values())!=2000000: raise SystemExit('plan quota drift')
if not p.get('generation_authorized_by_design'): raise SystemExit('plan did not authorize generation')
PY
gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
[ "$(sha256sum "$W/curriculum.pjtw" | awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM hash drift"

stage build-authenticated-exact-fold-tempo-engine
for file in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/movegen.cpp src/movegen.hpp; do
  git show "$EXPECTED_CODE_SHA:$file" >"$W/$(basename "$file").expected"
  cmp -s "$file" "$W/$(basename "$file").expected" || die "architecture source drift: $file"
done
grep -q "g_emasks" src/scan_eval.cpp || die "archi: scan_eval without g_emasks"
grep -q "has_any_capture" src/search.cpp || die "archi: search without has_any_capture"
grep -q "has_any_capture" src/movegen.cpp || die "archi: movegen without has_any_capture"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
timeout 1800s cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
  -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
timeout 3600s cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "missing jass binary"
printf 'hello\nquit\n' | timeout 60s "$J" --pattern "$W/curriculum.pjtw" >"$W/load.log" 2>&1
grep -q '^ready' "$W/load.log" || die "CURRICULUM cannot be loaded"

# name quota rop eps decay topk margin depth
cat >"$W/cell-specs.tsv" <<'EOF'
BASE 300000 8 8 60 0 0 8
ROP16 600000 16 8 60 0 0 8
EPS16 500000 8 16 60 0 0 8
DECAY120 100000 8 8 120 0 0 8
TOPK3M30 100000 8 8 60 3 30 8
DEPTH10 400000 8 8 60 0 0 10
EOF

gen_one(){ # name out count seed log rop eps decay topk margin depth timeout
  local name="$1" out="$2" count="$3" seed="$4" log="$5"
  local rop="$6" eps="$7" decay="$8" topk="$9" margin="${10}" depth="${11}" limit="${12}"
  timeout -k 30s "${limit}s" "$J" --gen-data-wdl "$count" "$out" \
    "$LABEL_DEPTH" "$depth" "$MAXPLIES" "$seed" \
    --nnue "$W/curriculum.pjtw" --search-params-play "$Q00" --wdl-zero-score \
    --random-open-plies "$rop" --explore-eps "$eps" --explore-decay-plies "$decay" \
    --explore-topk "$topk" --explore-margin "$margin" --split-selfplay-rngs \
    --pair-openings --drop-plycap --sample-meta-out "${out%.jnnw}.jsm" --sample-meta-format jsm2 \
    >"$log" 2>&1 < /dev/null
}

stage exact-six-cell-rate-preflight
: >"$W/preflight-rates.tsv"
while read -r NAME QUOTA ROP EPS DECAY TOPK MARGIN DEPTH; do
  t0=$(date +%s)
  gen_one "$NAME" "$W/pf-$NAME.jnnw" "$PREFLIGHT_RECORDS" \
    $((FRESH_SEED-1000)) "$W/pf-$NAME.log" "$ROP" "$EPS" "$DECAY" "$TOPK" "$MARGIN" "$DEPTH" 600 ||
    die "$NAME preflight failed"
  t1=$(date +%s); [ -s "$W/pf-$NAME.jnnw" ] || die "$NAME preflight produced no data"
  printf '%s\t%s\t%s\n' "$NAME" "$QUOTA" "$((t1-t0))" >>"$W/preflight-rates.tsv"
done <"$W/cell-specs.tsv"
"$PY" - "$W/preflight-rates.tsv" "$PREFLIGHT_RECORDS" "$PRODUCERS" "$CONTENTION" \
  "$MAX_BUDGET_MIN" "$ART/preflight-budget.json" "$W/runtime-limits.tsv" <<'PY' | tee -a "$RES"
import json,math,sys
rates,per,producers,contention,budget,out,limits=sys.argv[1:]
per,producers,contention,budget=int(per),int(producers),float(contention),float(budget)
rows=[]; total=0.0
for raw in open(rates):
 name,quota,seconds=raw.split(); quota,seconds=int(quota),max(1,int(seconds))
 solo=per/(seconds/60); parallel=solo/contention*producers; minutes=quota/parallel
 timeout_s=min(1800,max(300,int(math.ceil(minutes*60*1.30+60))))
 rows.append({'cell':name,'quota':quota,'preflight_seconds':seconds,'solo_per_min':solo,
              'projected_total_per_min':parallel,'projected_minutes':minutes,'shard_timeout_seconds':timeout_s})
 total+=minutes
with open(limits,'w') as handle:
 for row in rows: handle.write(f"{row['cell']}\t{row['shard_timeout_seconds']}\n")
payload={'schema':'jass.l3_context2_intervention_preflight.v1','nproc':16,'producers':producers,
 'contention_factor_from_cpx62_1356':contention,'projected_generation_minutes':total,
 'budget_minutes':budget,'within_budget':total<=budget,'cells':rows}
json.dump(payload,open(out,'w'),indent=2,sort_keys=True)
for row in sorted(rows,key=lambda r:-r['projected_minutes']):
 print(f"  {row['cell']}: {row['projected_minutes']:.1f} min, timeout {row['shard_timeout_seconds']} s")
print(f"  total generation projection: {total:.1f} min (budget {budget:.0f})")
if total>budget: raise SystemExit(f'preflight budget exceeded: {total:.1f}>{budget:.1f} min')
PY

stage generate-fresh-preregistered-cells
mkdir -p "$W/cells"
while read -r NAME QUOTA ROP EPS DECAY TOPK MARGIN DEPTH; do
  echo "cell-$NAME" >"$STAGE"
  CELL="$W/cells/$NAME"; mkdir -p "$CELL"
  LIMIT=$(awk -v n="$NAME" '$1==n{print $2}' "$W/runtime-limits.tsv")
  [ -n "$LIMIT" ] || die "$NAME missing calibrated timeout"
  base=$((QUOTA/PRODUCERS)); rem=$((QUOTA%PRODUCERS)); pids=(); pairs=()
  for shard in $(seq 0 $((PRODUCERS-1))); do
    count="$base"; [ "$shard" -lt "$rem" ] && count=$((count+1))
    data="$CELL/s$shard.jnnw"; meta="$CELL/s$shard.jsm"
    gen_one "$NAME" "$data" "$count" $((FRESH_SEED+shard)) "$CELL/s$shard.log" \
      "$ROP" "$EPS" "$DECAY" "$TOPK" "$MARGIN" "$DEPTH" "$LIMIT" &
    pids+=("$!"); pairs+=(--pair "$data" "$meta")
  done
  bad=0; for pid in "${pids[@]}"; do wait "$pid" || bad=$((bad+1)); done
  [ "$bad" -eq 0 ] || die "$NAME: $bad producer failures"
  for shard in $(seq 0 $((PRODUCERS-1))); do
    [ -s "$CELL/s$shard.jnnw" ] && [ -s "$CELL/s$shard.jsm" ] || die "$NAME: shard $shard absent"
    grep -q 'label_score_searches=0' "$CELL/s$shard.log" || die "$NAME: score-label search active"
    grep -q 'split_selfplay_rngs=1' "$CELL/s$shard.log" || die "$NAME: split RNG inactive"
  done
  "$PY" tools/selfplay_frontier.py merge "${pairs[@]}" --renamespace-nested --no-wdl-check \
    --out-data "$CELL/cell.jnnw" --out-meta "$CELL/cell.jsm" \
    --manifest "$ART/cells/$NAME-merge.json" >"$CELL/merge.log" 2>&1
  "$PY" jobs/tools/assert_corpus_wdl.py --data "$CELL/cell.jnnw" >"$CELL/wdl.log" 2>&1
  gzip -n -c "$CELL/cell.jnnw" >"$ART/cells/$NAME.jnnw.gz"
  gzip -n -c "$CELL/cell.jsm" >"$ART/cells/$NAME.jsm.gz"
  say "cell=$NAME records=$QUOTA ready"
done <"$W/cell-specs.tsv"

stage merge-and-audit-two-million-corpus
all_pairs=()
while read -r NAME _; do all_pairs+=(--pair "$W/cells/$NAME/cell.jnnw" "$W/cells/$NAME/cell.jsm"); done <"$W/cell-specs.tsv"
"$PY" tools/selfplay_frontier.py merge "${all_pairs[@]}" --renamespace-nested --no-wdl-check \
  --out-data "$W/context2-intervention-2m.jnnw" --out-meta "$W/context2-intervention-2m.jsm" \
  --manifest "$ART/context2-intervention-2m-merge.json" >"$W/unified-merge.log" 2>&1
"$PY" jobs/tools/assert_corpus_wdl.py --data "$W/context2-intervention-2m.jnnw" >"$W/unified-wdl.log" 2>&1
cell_args=()
while read -r NAME _; do cell_args+=(--cell "$NAME=$W/cells/$NAME/cell.jnnw"); done <"$W/cell-specs.tsv"
"$PY" jobs/tools/l3_context2_intervention_corpus_audit.py "${cell_args[@]}" \
  --unified "$W/context2-intervention-2m.jnnw" --code-sha "$EXPECTED_CODE_SHA" \
  --fresh-seed "$FRESH_SEED" --out "$ART/JASS_CONTROL_SUMMARY.json" | tee -a "$RES"
touch "$ART/VERDICT__JASS_CONTEXT2_INTERVENTION_CORPUS_READY"
touch "$ART/SELFPLAY_GENERATED__TRUE" "$ART/FITS_RUN__0" "$ART/FORCE_GAMES_PLAYED__0"
touch "$ART/FROZEN_READ__FALSE" "$ART/PROMOTION_AUTHORIZED__FALSE" "$ART/AUTOMATIC_NEXT_JOB__NULL"
gzip -n -c "$W/context2-intervention-2m.jnnw" >"$ART/context2-intervention-2m.jnnw.gz"
gzip -n -c "$W/context2-intervention-2m.jsm" >"$ART/context2-intervention-2m.jsm.gz"
say "JASS_CONTEXT2_INTERVENTION_CORPUS_READY records=2000000 fresh=true fits=0 promotion=false"
