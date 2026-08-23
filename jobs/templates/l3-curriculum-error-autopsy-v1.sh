#!/usr/bin/env bash
# Fresh paired CURRICULUM self-campaign followed by a sealed read-only error autopsy.
# Two disjoint pools are dumped completely.  A deeper copy of the byte-identical
# champion diagnoses every historical champion decision.  No corpus generation,
# fit, frozen read, force gate or promotion occurs in this job.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GAMES1="$ART/games-pool1"; GAMES2="$ART/games-pool2"; SHARDS="$ART/autopsy-shards"
mkdir -p "$W" "$IN" "$ART" "$GAMES1" "$GAMES2" "$SHARDS"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE="18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_ROOT="r2:jass-data/runs/$CURRICULUM_JOB/$CURRICULUM_ATTEMPT"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
NOPEN="${NOPEN:-384}"
CANDIDATES="${CANDIDATES:-12000}"
POOL_SEED_1="${POOL_SEED_1:-2026082213}"
POOL_SEED_2="${POOL_SEED_2:-2026082214}"
SPLIT_SEED="${SPLIT_SEED:-2026082215}"
MATCH_SEED="${MATCH_SEED:-2026082216}"
ACTION_SOURCE_ONLY="${ACTION_SOURCE_ONLY:-0}"
LOSS_FIRST_SOURCE_ONLY="${LOSS_FIRST_SOURCE_ONLY:-0}"
NSH=16
PAR=16
MOVETIME=0.1
TEACHER_DEPTH=10
JUDGE_DEPTH=12
PREFLIGHT_ROWS_PER_SHARD=4
MAX_PROJECTED_MINUTES=480
CACHE_MB=128
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

EXCLUDE_SPECS="pool-replay-b-promotion-1454-pool1|r2:jass-data/runs/cpx62-1454-l3-replay-b-vs-curriculum-promotion-v1/20260821T155257Z-9e79c9d4|artefacts/replay-b-promotion-pool1-openings.fen
pool-replay-b-promotion-1454-pool2|r2:jass-data/runs/cpx62-1454-l3-replay-b-vs-curriculum-promotion-v1/20260821T155257Z-9e79c9d4|artefacts/replay-b-promotion-pool2-openings.fen
pool-replay-context30-1464-pool1|r2:jass-data/runs/cpx62-1464-l3-replay-context30-target-gate-v1/20260822T080732Z-cfd7b7b2|artefacts/replay-context30-target-pool1-openings.fen
pool-replay-context30-1464-pool2|r2:jass-data/runs/cpx62-1464-l3-replay-context30-target-gate-v1/20260822T080732Z-cfd7b7b2|artefacts/replay-context30-target-pool2-openings.fen
pool-curriculum-error-1468-pool1|r2:jass-data/runs/cpx62-1468-l3-curriculum-error-autopsy-v1/20260822T134756Z-746421c7|artefacts/curriculum-error-pool1-openings.fen|failed
pool-curriculum-error-1468-pool2|r2:jass-data/runs/cpx62-1468-l3-curriculum-error-autopsy-v1/20260822T134756Z-746421c7|artefacts/curriculum-error-pool2-openings.fen|failed
pool-curriculum-error-1492-pool1|r2:jass-data/runs/cpx62-1492-l3-curriculum-error-autopsy-v1/20260822T212256Z-454b3862|artefacts/curriculum-error-pool1-openings.fen
pool-curriculum-error-1492-pool2|r2:jass-data/runs/cpx62-1492-l3-curriculum-error-autopsy-v1/20260822T212256Z-454b3862|artefacts/curriculum-error-pool2-openings.fen"

LOSS_FIRST_LEGACY_EXCLUDE_SPECS="pool-context2-curriculum-alpha30-first3000|r2:jass-data/runs/cpx62-1398-l3-context2-curriculum-alpha30-fresh3000-pool1-v1/20260818T061513Z-f60336ca|artefacts/context2-curriculum-alpha30-pool1-openings.fen
pool-context2-curriculum-alpha30-second3000|r2:jass-data/runs/cpx62-1401-l3-context2-curriculum-alpha30-fresh3000-pool2-v1/20260818T073556Z-f60336ca|artefacts/context2-curriculum-alpha30-pool2-openings.fen
pool-context2-alpha100-first3000|r2:jass-data/runs/cpx62-1386-l3-context2-alpha100-fresh3000-pool1-v1/20260817T145036Z-05554755|artefacts/context2-alpha100-pool1-openings.fen
pool-context2-primary-first3000|r2:jass-data/runs/cpx62-1375-l3-context2-primary-pool1-v1/20260817T025306Z-3393763d|artefacts/context2-primary-pool1-openings.fen
pool-context2-primary-second3000|r2:jass-data/runs/cpx62-1377-l3-context2-primary-pool2-v1/20260817T030349Z-3393763d|artefacts/context2-primary-pool2-openings.fen
pool-context30-causal-first3000|r2:jass-data/runs/cpx62-1360-l3-context30-causal-pool1-v1/20260816T075225Z-196d5e1d|artefacts/context30-causal-pool1-openings.fen
pool-context30-causal-second3000|r2:jass-data/runs/cpx62-1361-l3-context30-causal-pool2-v1/20260816T080325Z-196d5e1d|artefacts/context30-causal-pool2-openings.fen
pool-d-champion-first3000|r2:jass-data/runs/cpx62-1348-jass-d-champion-fresh3000-pool-v1/20260815T065455Z-18c38a33|artefacts/d-champion-fresh3000-openings.fen
pool-d-champion-replication3000|r2:jass-data/runs/cpx62-1351-jass-d-champion-replication3000-pool-v1/20260815T083517Z-18c38a33|artefacts/d-champion-replication3000-openings.fen
pool-abcd-highn1500|r2:jass-data/runs/home-1108-l3-pure-reverse-seed-scale4m-independent-readout-v1/20260731T034759Z-3351b160|artefacts/reverse-seed-scale4m-readout-openings.fen
pool-abcd-source500|r2:jass-data/runs/home-0984bis-l3-pure-turnover-l2-preflight-v2/20260726T122615Z-5ef14ffe|artefacts/turnover-l2-eval-openings.fen
pool-big3000|r2:jass-data/runs/cpx62-1154-l3-big-opening-pool-v1/20260802T120251Z-9b57e0aa|artefacts/big3000-openings.fen
pool-big3000b|r2:jass-data/runs/cpx62-1183-l3-second-big-opening-pool/20260805T155017Z-cd9064f9|artefacts/big3000b-openings.fen
pool-vol8m|r2:jass-data/runs/home-1004-l3-pure-volume8m-preflight-v2/20260727T211936Z-90d3aad1|artefacts/vol8m-eval-openings.fen
pool-succession|r2:jass-data/runs/home-0995-l3-pure-turnover-succession-preflight-v2/20260727T054246Z-f20e59d0|artefacts/turnover-succession-openings.fen
pool-context3-1419-force-pool1|r2:jass-data/runs/cpx62-1419-l3-context3-two-pool-force-v1/20260819T112556Z-8adc506a|artefacts/ctx3-force-pool1-openings.fen
pool-context3-1419-force-pool2|r2:jass-data/runs/cpx62-1419-l3-context3-two-pool-force-v1/20260819T112556Z-8adc506a|artefacts/ctx3-force-pool2-openings.fen
pool-context3-1428-force-pool1|r2:jass-data/runs/cpx62-1428-l3-context3-two-pool-force-exact-extras-v2/20260820T005123Z-17517b38|artefacts/ctx3-force-pool1-openings.fen
pool-context3-1428-force-pool2|r2:jass-data/runs/cpx62-1428-l3-context3-two-pool-force-exact-extras-v2/20260820T005123Z-17517b38|artefacts/ctx3-force-pool2-openings.fen
pool-replay-doe-1451-pool1|r2:jass-data/runs/cpx62-1451-l3-exploratory-replay-force-resume-v3/20260821T063856Z-b9b6d9ad|artefacts/replay-doe-pool1-openings.fen
pool-replay-doe-1451-pool2|r2:jass-data/runs/cpx62-1451-l3-exploratory-replay-force-resume-v3/20260821T063856Z-b9b6d9ad|artefacts/replay-doe-pool2-openings.fen"

EXPECTED_EXCLUSION_COUNT=9
if [ "$LOSS_FIRST_SOURCE_ONLY" = 1 ]; then
  EXCLUDE_SPECS="$LOSS_FIRST_LEGACY_EXCLUDE_SPECS"$'\n'"$EXCLUDE_SPECS"
  EXPECTED_EXCLUSION_COUNT=30
fi

MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        printf 'games_dumped=%s/1536\n' "$(find "$GAMES1" "$GAMES2" -name 'game-*.json' 2>/dev/null | wc -l)"
        printf 'autopsy_shards=%s/16\n' "$(find "$SHARDS" -name 'shard-*.json' 2>/dev/null | wc -l)"
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
  rm -rf "$W/build" "$IN" "$W/gate-"* "$W/preflight" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
if [ "$LOSS_FIRST_SOURCE_ONLY" = 1 ]; then
  [[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-loss-first-source-v1$ ]] || die "invalid loss-first job nomenclature"
  : "${PREREG_SOURCE_JOB:?}"; : "${PREREG_SOURCE_ATTEMPT:?}"; : "${PREREG_SOURCE_CODE:?}"
  [ "$ACTION_SOURCE_ONLY" = 0 ] || die "loss-first/action-source modes are mutually exclusive"
else
  [[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-autopsy-v1$ ]] || die "invalid job nomenclature"
fi
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] || die "frozen-read guard missing"
[ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] || die "promotion guard missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guard missing"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
say "experiment=CURRICULUM_ERROR_AUTOPSY all_games=true pools=2 openings_per_pool=$NOPEN"
say "campaign=byte_identical_CURRICULUM_self_match native=0.1 teacher=d10 judge=d12 fit=0 promotion=false"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/jass_vs_jass_arch.py jobs/tools/run_jass_gate_bounded.py \
  jobs/tools/l3_curriculum_error_learning.py
python3 -m unittest jobs.tests.test_run_jass_gate jobs.tests.test_l3_curriculum_error_learning \
  >"$W/tests.log" 2>&1

stage fetch-authenticate-byte-identical-curriculum
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=curriculum-summary.json \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" --expected-state completed \
  >"$W/fetch-curriculum.log" 2>&1
gunzip -t "$IN/curriculum.pjtw.gz"
gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
printf '%s\n' "$Q00" >"$ART/search-params.txt"
python3 - "$ART" "$IN" "$W" "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" \
  "$CURRICULUM_CODE" "$CURRICULUM_SHA" <<'PY_AUTH'
import hashlib,json,sys
from pathlib import Path
art,src,work=map(Path,sys.argv[1:4]); want=tuple(sys.argv[4:8])
receipt=json.load(open(art/'verified-curriculum.json'))
got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'))
if got!=want[:3] or receipt.get('result_state')!='completed' or receipt.get('exit_code')!=0:
 raise SystemExit(f'CURRICULUM source drift: {got}')
summary=json.load(open(src/'curriculum-summary.json'))
if summary.get('verdict')!='JASS_MEGACORPUS_ARM_D_FIT_READY': raise SystemExit('CURRICULUM certificate drift')
sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
actual=sha(work/'curriculum.pjtw')
if actual!=want[3]: raise SystemExit(f'CURRICULUM raw hash drift: {actual}')
(art/'champion-certificate.json').write_text(json.dumps({
 'schema':'jass.curriculum_error_champion.v1','verdict':'JASS_CURRICULUM_BYTE_AUTHENTICATED',
 'job_id':want[0],'attempt_id':want[1],'code_sha':want[2],'model_raw_sha256':actual,
 'same_model_both_sides':True,'promotion_authorized':False},indent=2,sort_keys=True)+'\n')
PY_AUTH

if [ "$LOSS_FIRST_SOURCE_ONLY" = 1 ]; then
  stage fetch-authenticate-loss-first-preregistration
  timeout 1800s python3 jobs/tools/fetch_result_files.py \
    --prefix "r2:jass-data/runs/$PREREG_SOURCE_JOB/$PREREG_SOURCE_ATTEMPT" \
    --file artefacts/JASS_CONTROL_SUMMARY.json=loss-first-prereg.json \
    --out-dir "$IN" --report "$ART/verified-loss-first-prereg.json" --expected-state completed \
    >"$W/fetch-loss-first-prereg.log" 2>&1
  python3 - "$ART/verified-loss-first-prereg.json" "$IN/loss-first-prereg.json" \
    "$PREREG_SOURCE_JOB" "$PREREG_SOURCE_ATTEMPT" "$PREREG_SOURCE_CODE" \
    "$POOL_SEED_1" "$POOL_SEED_2" "$SPLIT_SEED" "$MATCH_SEED" >"$W/auth-loss-first-prereg.log" 2>&1 <<'PY_LOSS_FIRST_AUTH'
import json,sys
receipt=json.load(open(sys.argv[1])); plan=json.load(open(sys.argv[2])); want=tuple(sys.argv[3:6])
got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'))
if got!=want or receipt.get('result_state')!='completed' or receipt.get('exit_code')!=0:
 raise SystemExit(f'loss-first prereg identity/state drift got={got} want={want}')
if plan.get('verdict')!='JASS_CURRICULUM_ERROR_LOSS_FIRST_SIBLING_RANK_PREREGISTERED' or plan.get('passed') is not True:
 raise SystemExit('loss-first prereg verdict drift')
seeds=plan.get('seeds',{}); actual=tuple(map(int,sys.argv[6:10])); expected=tuple(int(seeds[k]) for k in ('pool1','pool2','split','match'))
if actual!=expected: raise SystemExit(f'loss-first seed drift got={actual} want={expected}')
campaign=plan.get('source_campaign',{})
if campaign.get('pools')!=2 or campaign.get('openings_per_pool')!=384 or campaign.get('total_games')!=1536 or campaign.get('source_stage_has_no_deep_targets') is not True:
 raise SystemExit('loss-first source campaign contract drift')
PY_LOSS_FIRST_AUTH
fi

stage build-current-exact-fold-tempo-engine
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON \
  -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests >"$W/build.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB ctest --test-dir "$W/build" --output-on-failure >"$W/ctest.log" 2>&1
J="$W/build/jass"
printf 'hello\nquit\n' | timeout 60 "$J" --pattern "$W/curriculum.pjtw" --search-params "$Q00" >"$W/load.log" 2>&1
grep -q '^ready' "$W/load.log" || die "CURRICULUM does not load"

stage fetch-recent-pool-exclusions
EXCL_ARGS=(--exclude data/dilf_combinations.fen); EXCL_NAMES=(dilf_combinations)
while IFS='|' read -r label prefix remote_path expected_state; do
  [ -n "${label:-}" ] || continue
  expected_state="${expected_state:-completed}"
  timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$prefix" \
    --file "$remote_path=$label.fen" --out-dir "$IN" \
    --report "$ART/verified-exclude-$label.json" --expected-state "$expected_state" \
    >"$W/fetch-$label.log" 2>&1 || die "historical pool fetch failed: $label"
  EXCL_ARGS+=(--exclude "$IN/$label.fen"); EXCL_NAMES+=("$label")
done <<<"$EXCLUDE_SPECS"
[ "${#EXCL_NAMES[@]}" -eq "$EXPECTED_EXCLUSION_COUNT" ] || die "exclusion count drift"

generate_pool(){
  local index="$1" seed="$2" out="curriculum-error-pool${1}-openings"
  local extra=("${EXCL_ARGS[@]}")
  [ "$index" -eq 2 ] && extra+=(--exclude "$ART/curriculum-error-pool1-openings.fen")
  for pass in a b; do
    "$J" --gen-opening-pool "$CANDIDATES" "$W/pool${index}-cand-$pass.fen" 8 32 20 "$seed" \
      >"$W/pool${index}-gen-$pass.log" 2>&1
  done
  cmp -s "$W/pool${index}-cand-a.fen" "$W/pool${index}-cand-b.fen" || die "pool$index nondeterministic"
  python3 jobs/tools/select_independent_opening_pool.py --candidates "$W/pool${index}-cand-a.fen" \
    --expected "$NOPEN" "${extra[@]}" --generator-seed "$seed" \
    --out "$ART/$out.fen" --manifest "$ART/$out.json" >"$W/pool${index}-select.log" 2>&1
  python3 jobs/tools/validate_opening_pool.py --pool "$ART/$out.fen" --expected "$NOPEN" \
    --generator-seed "$seed" "${extra[@]}" --out "$ART/$out-provenance.json" \
    >"$W/pool${index}-validate.log" 2>&1
}
stage generate-two-fresh-disjoint-campaign-pools
generate_pool 1 "$POOL_SEED_1"; generate_pool 2 "$POOL_SEED_2"
[ "$(grep -Fx -f "$ART/curriculum-error-pool1-openings.fen" "$ART/curriculum-error-pool2-openings.fen" | grep -c . || true)" -eq 0 ] || die "campaign pools overlap"

stage play-and-dump-all-games-pool1
python3 jobs/tools/run_jass_gate_bounded.py --jass "$J" \
  --pattern-a "$W/curriculum.pjtw" --pattern-b "$W/curriculum.pjtw" \
  --search-params-a "$Q00" --search-params-b "$Q00" \
  --openings-file "$ART/curriculum-error-pool1-openings.fen" --movetime "$MOVETIME" \
  --pairs 1 --max-plies 160 --nshards "$NSH" --max-parallel "$PAR" --timeout 21600 \
  --game-timeout 180 --dump-games-dir "$GAMES1" --work-dir "$W/gate-pool1" \
  --out "$ART/campaign-pool1.json" >"$W/campaign-pool1.log" 2>&1
stage play-and-dump-all-games-pool2
python3 jobs/tools/run_jass_gate_bounded.py --jass "$J" \
  --pattern-a "$W/curriculum.pjtw" --pattern-b "$W/curriculum.pjtw" \
  --search-params-a "$Q00" --search-params-b "$Q00" \
  --openings-file "$ART/curriculum-error-pool2-openings.fen" --movetime "$MOVETIME" \
  --pairs 1 --max-plies 160 --nshards "$NSH" --max-parallel "$PAR" --timeout 21600 \
  --game-timeout 180 --dump-games-dir "$GAMES2" --work-dir "$W/gate-pool2" \
  --out "$ART/campaign-pool2.json" >"$W/campaign-pool2.log" 2>&1
[ "$(find "$GAMES1" "$GAMES2" -name 'game-*.json' | wc -l)" -eq 1536 ] || die "complete game count drift"

stage seal-opening-split-and-prepare-every-champion-decision
python3 jobs/tools/l3_curriculum_error_learning.py prepare --games-dir "$GAMES1" --games-dir "$GAMES2" \
  --split-seed "$SPLIT_SEED" --out "$ART/error-selection.json" >"$W/prepare.log" 2>&1
python3 jobs/tools/l3_curriculum_error_learning.py transitions --selection "$ART/error-selection.json" \
  --games-dir "$GAMES1" --games-dir "$GAMES2" --out "$ART/error-transitions.json" \
  >"$W/transitions.log" 2>&1

if [ "$LOSS_FIRST_SOURCE_ONLY" = 1 ]; then
  stage authenticate-and-publish-loss-first-source
  python3 - "$ART" "$IN/loss-first-prereg.json" "$CURRICULUM_SHA" "$EXPECTED_CODE_SHA" \
    "$POOL_SEED_1" "$POOL_SEED_2" "$SPLIT_SEED" "$MATCH_SEED" \
    "$PREREG_SOURCE_JOB" "$PREREG_SOURCE_ATTEMPT" "$PREREG_SOURCE_CODE" <<'PY_LOSS_FIRST_SOURCE'
import hashlib,json,sys
from pathlib import Path
art=Path(sys.argv[1]); prereg_path=Path(sys.argv[2]); model_sha=sys.argv[3]; code=sys.argv[4]
pool_seeds=[int(sys.argv[5]),int(sys.argv[6])]; split_seed=int(sys.argv[7]); match_seed=int(sys.argv[8]); prereg_identity=tuple(sys.argv[9:12])
selection=json.load(open(art/'error-selection.json')); transitions=json.load(open(art/'error-transitions.json')); prereg=json.load(open(prereg_path))
if selection.get('games')!=1536 or selection.get('decisions',0)<50000: raise SystemExit('loss-first source cardinality drift')
if len(transitions.get('transitions',[]))!=selection['decisions']: raise SystemExit('loss-first transition coverage drift')
payload={'schema':'jass.curriculum_error_loss_first_source_terminal.v1','verdict':'JASS_CURRICULUM_ERROR_LOSS_FIRST_SOURCE_READY','passed':True,
 'source_code_sha':code,'champion_sha256':model_sha,
 'preregistration':dict(zip(('job','attempt','code_sha'),prereg_identity)),
 'preregistration_sha256':hashlib.sha256(prereg_path.read_bytes()).hexdigest(),
 'selection_sha256':hashlib.sha256((art/'error-selection.json').read_bytes()).hexdigest(),
 'transitions_sha256':hashlib.sha256((art/'error-transitions.json').read_bytes()).hexdigest(),
 'campaign':{'pools':2,'openings_per_pool':384,'games':1536,'native_movetime_seconds':.1,'pool_seeds':pool_seeds,'split_seed':split_seed,'match_seed':match_seed,'same_byte_identical_champion_both_sides':True,'all_trajectories_dumped':True,'disjoint_from_authenticated_historical_pools':True},
 'decisions':selection['decisions'],'deep_target_computations':0,'autopsy_shards':0,'pattern_bucket_aggregate_reads':0,'pattern_eval_fits':0,'production_model_fits':0,'new_selfplay_games':1536,'strength_games':0,'frozen_reads':0,'promotion_authorized':False,'automatic_continuation':False,'next_stage':'loss_first_all_legal_sibling_labeling'}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_LOSS_FIRST_SOURCE
  : >"$ART/JASS_CURRICULUM_ERROR_LOSS_FIRST_SOURCE_READY"
  : >"$ART/DEEP_TARGET_COMPUTATIONS__0"; : >"$ART/AUTOPSY_SHARDS__0"
  : >"$ART/PATTERN_BUCKET_AGGREGATE_READS__0"; : >"$ART/PATTERNEVAL_FITS__0"
  : >"$ART/STRENGTH_GAMES__0"; : >"$ART/FROZEN_READS__0"; : >"$ART/PROMOTION_AUTHORIZED__FALSE"
  stage completed
  say "JASS_CURRICULUM_ERROR_LOSS_FIRST_SOURCE_READY games=1536 deep_targets=0 fits=0 force=0"
  exit 0
fi

stage depth10-depth12-cost-preflight
mkdir -p "$W/preflight"
T0=$(date +%s)
pids=()
for shard in $(seq 0 $((NSH-1))); do
  python3 jobs/tools/l3_curriculum_error_learning.py worker --selection "$ART/error-selection.json" \
    --transitions "$ART/error-transitions.json" \
    --jass "$J" --champion "$W/curriculum.pjtw" --search-params "$ART/search-params.txt" \
    --teacher-depth "$TEACHER_DEPTH" --judge-depth "$JUDGE_DEPTH" --symmetry-rows 32 \
    --max-rows "$PREFLIGHT_ROWS_PER_SHARD" --shard "$shard" --nshards "$NSH" \
    --out "$W/preflight/shard-$shard.json" >"$W/preflight-$shard.log" 2>&1 & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done
T1=$(date +%s)
python3 - "$ART/error-selection.json" "$W/preflight" "$ART/cost-preflight.json" "$((T1-T0))" \
  "$MAX_PROJECTED_MINUTES" <<'PY_COST'
import json,sys
from pathlib import Path
selection=Path(sys.argv[1]); root=Path(sys.argv[2]); out=Path(sys.argv[3])
elapsed=max(int(sys.argv[4]),1); maximum=int(sys.argv[5]); total=json.load(open(selection))['decisions']
rows=sum(len(json.load(open(p))['rows']) for p in root.glob('shard-*.json'))
if rows<=0: raise SystemExit('cost preflight produced zero rows')
projected=elapsed*total/rows/60
payload={'schema':'jass.curriculum_error_cost_preflight.v1','sample_rows':rows,'total_decisions':total,
 'elapsed_seconds':elapsed,'projected_minutes':projected,'maximum_minutes':maximum,'passed':projected<=maximum}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
if projected>maximum: raise SystemExit(f'projected autopsy {projected:.1f} min exceeds {maximum}')
PY_COST

stage analyse-every-decision-depth10-depth12
pids=()
for shard in $(seq 0 $((NSH-1))); do
  python3 jobs/tools/l3_curriculum_error_learning.py worker --selection "$ART/error-selection.json" \
    --transitions "$ART/error-transitions.json" \
    --jass "$J" --champion "$W/curriculum.pjtw" --search-params "$ART/search-params.txt" \
    --teacher-depth "$TEACHER_DEPTH" --judge-depth "$JUDGE_DEPTH" --symmetry-rows 32 \
    --shard "$shard" --nshards "$NSH" --out "$SHARDS/shard-$shard.json" \
    >"$W/autopsy-$shard.log" 2>&1 & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done
[ "$(find "$SHARDS" -name 'shard-*.json' | wc -l)" -eq "$NSH" ] || die "autopsy shard count drift"

if [ "$ACTION_SOURCE_ONLY" = 1 ]; then
  stage authenticate-and-publish-fresh-action-source
  python3 - "$ART" "$CURRICULUM_SHA" "$EXPECTED_CODE_SHA" "$POOL_SEED_1" \
    "$POOL_SEED_2" "$SPLIT_SEED" <<'PY_ACTION_SOURCE'
import hashlib,json,sys
from pathlib import Path
art=Path(sys.argv[1]); model_sha=sys.argv[2]; code=sys.argv[3]
pool_seeds=[int(sys.argv[4]),int(sys.argv[5])]; split_seed=int(sys.argv[6])
selection=json.load(open(art/'error-selection.json'))
shards=[json.load(open(art/'autopsy-shards'/f'shard-{i}.json')) for i in range(16)]
if selection.get('games')!=1536 or selection.get('decisions',0)<50000:
 raise SystemExit('fresh action source cardinality drift')
if {int(row.get('shard',-1)) for row in shards}!=set(range(16)):
 raise SystemExit('fresh action source shards incomplete')
rows=[item for shard in shards for item in shard.get('rows',[])]
if len(rows)!=selection['decisions']:
 raise SystemExit('fresh action source row coverage drift')
identities={}
for key in ('champion_sha256','jass_sha256','search_params_sha256'):
 values={str(row.get(key,'')) for row in shards}
 if len(values)!=1 or not next(iter(values)): raise SystemExit(f'{key} identity drift')
 identities[key]=next(iter(values))
if identities['champion_sha256']!=model_sha: raise SystemExit('champion hash drift')
diff=sum(bool(row.get('move_differs')) for row in rows)
loss_errors=sum(row.get('outcome')=='loss' and float(row.get('regret_cp',0))>=50 for row in rows)
payload={'schema':'jass.curriculum_error_action_source_terminal.v1',
 'verdict':'JASS_CURRICULUM_ERROR_ACTION_SOURCE_READY','source_code_sha':code,
 **identities,'selection_sha256':hashlib.sha256((art/'error-selection.json').read_bytes()).hexdigest(),
 'transitions_sha256':hashlib.sha256((art/'error-transitions.json').read_bytes()).hexdigest(),
 'campaign':{'pools':2,'openings_per_pool':384,'games':1536,'native_movetime_seconds':.1,
  'pool_seeds':pool_seeds,'split_seed':split_seed,'same_byte_identical_champion_both_sides':True,
  'all_trajectories_dumped':True,'disjoint_from_1468_and_prior_force_pools':True},
 'decisions':selection['decisions'],'deep_action_differences':diff,
 'raw_loss_errors_ge_50cp':loss_errors,'autopsy_shards':16,
 'pattern_bucket_aggregate_reads':0,'pattern_eval_fits':0,'production_model_fits':0,
 'new_selfplay_games':1536,'strength_games':0,'frozen_reads':0,
 'promotion_authorized':False,'automatic_continuation':False,
 'next_stage':'fresh_action_pairing_and_ranker_screen'}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_ACTION_SOURCE
  : >"$ART/JASS_CURRICULUM_ERROR_ACTION_SOURCE_READY"
  : >"$ART/PATTERN_BUCKET_AGGREGATE_READS__0"
  : >"$ART/PATTERNEVAL_FITS__0"; : >"$ART/STRENGTH_GAMES__0"
  : >"$ART/FROZEN_READS__0"; : >"$ART/PROMOTION_AUTHORIZED__FALSE"
  stage completed
  say "JASS_CURRICULUM_ERROR_ACTION_SOURCE_READY games=1536 bucket_aggregate=0 fits=0 force=0"
  exit 0
fi

stage aggregate-discovery-confirmation-and-publish-verdict
shard_args=(); for shard in $(seq 0 $((NSH-1))); do shard_args+=(--shard "$SHARDS/shard-$shard.json"); done
python3 jobs/tools/l3_curriculum_error_learning.py aggregate --selection "$ART/error-selection.json" \
  "${shard_args[@]}" --min-regret-cp 50 --max-control-regret-cp 10 \
  --min-error-openings 64 --min-discovery-hits 4 --discovery-risk-ratio 1.5 \
  --confirm-risk-ratio 1.5 --min-confirmed-buckets 8 --max-region-buckets 512 \
  --match-seed "$MATCH_SEED" --report "$ART/error-autopsy.json" \
  --region "$ART/error-region.json" --seeds "$ART/error-seeds.jnnw" >"$W/aggregate.log" 2>&1

python3 - "$ART" "$CURRICULUM_SHA" "$EXPECTED_CODE_SHA" <<'PY_FINAL'
import hashlib,json,sys
from pathlib import Path
art=Path(sys.argv[1]); model_sha=sys.argv[2]; code=sys.argv[3]
report=json.load(open(art/'error-autopsy.json')); region=json.load(open(art/'error-region.json'))
if report['champion_sha256']!=model_sha or region['champion_sha256']!=model_sha: raise SystemExit('champion identity drift')
if report['verdict'] not in {'JASS_CURRICULUM_ERROR_REGION_CONFIRMED','JASS_CURRICULUM_ERROR_REGION_NOT_ESTABLISHED'}: raise SystemExit('verdict drift')
if report['fits']!=0 or report['strength_games']!=0 or report['frozen_reads']!=0: raise SystemExit('scope drift')
payload={**report,'schema':'jass.curriculum_error_autopsy_terminal.v1','source_code_sha':code,
 'campaign':{'pools':2,'openings_per_pool':384,'games':1536,'native_movetime_seconds':.1,
             'same_byte_identical_champion_both_sides':True,'all_trajectories_dumped':True},
 'next_stage_authorized':bool(report['fit_authorized']),'next_stage':'repair_corpus_500k' if report['fit_authorized'] else None,
 'new_selfplay_games':1536,'new_fits':0,'new_strength_games':0,'frozen_cohorts_read':0,
 'promotion_authorized':False,'automatic_promotion':False}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_FINAL
VERDICT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
: >"$ART/VERDICT__$VERDICT"; : >"$ART/ALL_GAMES_DUMPED__1536"; : >"$ART/FITS__0"
: >"$ART/STRENGTH_GAMES__0"; : >"$ART/FROZEN_COHORTS_READ__0"; : >"$ART/PROMOTION_AUTHORIZED__FALSE"
stage completed
say "$VERDICT games=1536 all_trajectories=true fits=0 frozen=0 promotion=false"
