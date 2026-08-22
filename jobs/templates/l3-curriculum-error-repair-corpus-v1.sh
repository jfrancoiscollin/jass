#!/usr/bin/env bash
# Build the preregistered 500k CURRICULUM error-repair corpus after a sealed PASS.
# This job performs generation only: no PatternEval fit, force game, frozen read
# or promotion.  A scientifically insufficient seed catalogue exits cleanly
# before the engine is built or any self-play is generated.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN/shards" "$ART"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; cp "$STAGE" "$ART/STAGE.txt"; }

SOURCE_JOB="cpx62-1474-l3-curriculum-error-autopsy-resume-v1"
SOURCE_ATTEMPT="20260822T153126Z-0be76565"
SOURCE_CODE="0be76565de1882c4d410995603217aa64ea09d70"
SOURCE_ROOT="r2:jass-data/runs/$SOURCE_JOB/$SOURCE_ATTEMPT"
CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE="18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_ROOT="r2:jass-data/runs/$CURRICULUM_JOB/$CURRICULUM_ATTEMPT"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
TARGET=500000; LABEL_DEPTH=4; PLAY_DEPTH=8; MAXPLIES=200
GEN_SEED=2026082219; SELECTION_SEED=2026082218
EXPLORE_EPS=8; EXPLORE_DECAY=60; EXPLORE_TOPK=3; EXPLORE_MARGIN=30
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        printf 'data_bytes=%s\n' "$(stat -c %s "$W/repair-500k.jnnw" 2>/dev/null || echo 0)"
      } >"$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 120
    done ) & MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$W"/*.jnnw "$W"/*.jsm 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-repair-corpus-v1$ ]] || die "invalid job nomenclature"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "${TARGETED_SELFPLAY_AUTHORIZED:-0}" = 1 ] || die "targeted self-play authorization missing"
[ "${NO_FIT:-0}" = 1 ] && [ "${NO_FORCE:-0}" = 1 ] || die "fit/force guards missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] && [ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] || die "frozen/promotion guards missing"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "persistent numeric runtime absent"
PY="$VENV/bin/python"; "$PY" -c 'import numpy; assert numpy.__version__'
say "experiment=CURRICULUM_ERROR_REPAIR_CORPUS source=$SOURCE_JOB/$SOURCE_ATTEMPT target=$TARGET"
say "parent=CURRICULUM seed_frac=100 without_replacement=true pair_openings=true fit=0 force=0 frozen=0 promotion=false"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_curriculum_error_learning.py \
  jobs/tools/l3_curriculum_repair_corpus_audit.py
python3 -m unittest jobs.tests.test_l3_curriculum_error_learning \
  jobs.tests.test_curriculum_error_seed_schedule \
  jobs.tests.test_l3_curriculum_repair_corpus_audit >"$W/tests.log" 2>&1

stage fetch-and-authenticate-confirmed-region
SOURCE_ARGS=(
  --file artefacts/error-selection.json=error-selection.json
  --file artefacts/error-region.json=error-region.json
  --file artefacts/error-autopsy.json=error-autopsy.json
  --file artefacts/JASS_CONTROL_SUMMARY.json=source-summary.json
)
for shard in $(seq 0 15); do SOURCE_ARGS+=(--file "artefacts/autopsy-shards/shard-$shard.json=shard-$shard.json"); done
timeout 3600s python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_ROOT" \
  "${SOURCE_ARGS[@]}" --out-dir "$IN" --report "$ART/verified-error-region.json" \
  --expected-state completed >"$W/fetch-region.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" --expected-state completed \
  >"$W/fetch-curriculum.log" 2>&1
"$PY" - "$ART" "$IN" "$SOURCE_JOB" "$SOURCE_ATTEMPT" "$SOURCE_CODE" \
  "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" "$CURRICULUM_CODE" "$CURRICULUM_SHA" <<'PY_AUTH'
import gzip,hashlib,json,sys
from pathlib import Path
art,src=map(Path,sys.argv[1:3]); sj,sa,sc,cj,ca,cc,champ=sys.argv[3:]
for name,expected in (('verified-error-region.json',(sj,sa,sc)),('verified-curriculum.json',(cj,ca,cc))):
 report=json.load(open(art/name)); got=(report.get('job_id'),report.get('attempt_id'),report.get('code_sha'))
 if got!=expected or report.get('result_state')!='completed' or report.get('exit_code')!=0:
  raise SystemExit(f'{name}: immutable source identity/state drift {got}')
summary=json.load(open(src/'source-summary.json')); autopsy=json.load(open(src/'error-autopsy.json'))
region=json.load(open(src/'error-region.json'))
if summary.get('verdict')!='JASS_CURRICULUM_ERROR_REGION_CONFIRMED' or summary.get('next_stage_authorized') is not True:
 raise SystemExit('source did not authorize repair seed catalogue')
if autopsy.get('fit_authorized') is not True or region.get('fit_authorized') is not True:
 raise SystemExit('confirmed region authorization drift')
if autopsy.get('champion_sha256')!=champ or region.get('champion_sha256')!=champ:
 raise SystemExit('confirmed region champion drift')
raw=gzip.decompress((src/'curriculum.pjtw.gz').read_bytes())
if hashlib.sha256(raw).hexdigest()!=champ: raise SystemExit('CURRICULUM hash drift')
(src/'curriculum.pjtw').write_bytes(raw)
PY_AUTH

stage build-fail-closed-repair-seed-catalogue
shard_args=(); for shard in $(seq 0 15); do shard_args+=(--shard "$IN/shard-$shard.json"); done
python3 jobs/tools/l3_curriculum_error_learning.py repair-seeds \
  --selection "$IN/error-selection.json" "${shard_args[@]}" --error-region "$IN/error-region.json" \
  --min-regret-cp 50 --max-per-opening 64 --min-ply-gap 2 \
  --selection-seed "$SELECTION_SEED" --target-positions "$TARGET" --max-plies "$MAXPLIES" \
  --min-source-openings 64 --max-opening-share 0.02 \
  --report "$ART/repair-seeds.json" --lineage "$ART/repair-seed-lineage.json" \
  --seeds "$W/repair-seeds.jnnw" >"$W/repair-seeds.log" 2>&1
SEED_VERDICT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/repair-seeds.json")
if [ "$SEED_VERDICT" != JASS_CURRICULUM_REPAIR_SEEDS_READY ]; then
  cp "$W/repair-seeds.jnnw" "$ART/repair-seeds.jnnw"
  "$PY" - "$ART" "$SOURCE_JOB" "$SOURCE_ATTEMPT" "$SOURCE_CODE" <<'PY_STOP'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); report=json.load(open(art/'repair-seeds.json'))
summary={**report,'schema':'jass.curriculum_error_repair_corpus_terminal.v1',
 'source':{'job_id':sys.argv[2],'attempt_id':sys.argv[3],'code_sha':sys.argv[4]},
 'new_selfplay_positions':0,'fits':0,'strength_games':0,'frozen_reads':0,
 'promotion_authorized':False,'automatic_promotion':False,'next_stage':None}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
PY_STOP
  : >"$ART/VERDICT__$SEED_VERDICT"; : >"$ART/NEW_SELFPLAY_POSITIONS__0"
  : >"$ART/FITS__0"; : >"$ART/STRENGTH_GAMES__0"; : >"$ART/FROZEN_READS__0"
  : >"$ART/PROMOTION_AUTHORIZED__FALSE"
  stage completed-scientific-stop
  say "$SEED_VERDICT generation=false new_selfplay=0"
  exit 0
fi

stage build-authenticated-exact-fold-tempo-engine
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
timeout 1800s cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
  -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
timeout 3600s cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "missing jass binary"
printf 'hello\nquit\n' | timeout 60s "$J" --pattern "$IN/curriculum.pjtw" >"$W/load.log" 2>&1
grep -q '^ready' "$W/load.log" || die "CURRICULUM cannot be loaded"

stage generate-exactly-500k-targeted-positions
timeout -k 60s 28800s "$J" --gen-data-wdl "$TARGET" "$W/repair-500k.jnnw" \
  "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" "$GEN_SEED" \
  --nnue "$IN/curriculum.pjtw" --search-params-play "$Q00" --wdl-zero-score \
  --explore-eps "$EXPLORE_EPS" --explore-decay-plies "$EXPLORE_DECAY" \
  --explore-topk "$EXPLORE_TOPK" --explore-margin "$EXPLORE_MARGIN" \
  --split-selfplay-rngs --seed-file "$W/repair-seeds.jnnw" --seed-frac 100 \
  --seed-without-replacement --seed-usage-out "$W/repair-seed-usage.tsv" \
  --pair-openings --drop-plycap --sample-meta-out "$W/repair-500k.jsm" \
  --sample-meta-format jsm2 >"$W/generate.log" 2>&1 < /dev/null

stage audit-corpus-lineage-distribution-and-guards
python3 jobs/tools/l3_curriculum_repair_corpus_audit.py \
  --data "$W/repair-500k.jnnw" --meta "$W/repair-500k.jsm" \
  --seed-usage "$W/repair-seed-usage.tsv" --seed-report "$ART/repair-seeds.json" \
  --lineage "$ART/repair-seed-lineage.json" --generator-log "$W/generate.log" \
  --champion-sha256 "$CURRICULUM_SHA" --source-job "$SOURCE_JOB" \
  --source-attempt "$SOURCE_ATTEMPT" --source-code-sha "$SOURCE_CODE" \
  --out "$ART/JASS_CONTROL_SUMMARY.json" | tee -a "$RES"
gzip -n -c "$W/repair-500k.jnnw" >"$ART/repair-500k.jnnw.gz"
gzip -n -c "$W/repair-500k.jsm" >"$ART/repair-500k.jsm.gz"
cp "$W/repair-seed-usage.tsv" "$ART/repair-seed-usage.tsv"
gzip -n -c "$W/repair-seeds.jnnw" >"$ART/repair-seeds.jnnw.gz"
: >"$ART/VERDICT__JASS_CURRICULUM_REPAIR_CORPUS_READY"
: >"$ART/NEW_SELFPLAY_POSITIONS__500000"; : >"$ART/FITS__0"; : >"$ART/STRENGTH_GAMES__0"
: >"$ART/FROZEN_READS__0"; : >"$ART/PROMOTION_AUTHORIZED__FALSE"
stage completed
say "JASS_CURRICULUM_REPAIR_CORPUS_READY records=500000 seed_reuses=0 fits=0 force=0 frozen=0 promotion=false"
