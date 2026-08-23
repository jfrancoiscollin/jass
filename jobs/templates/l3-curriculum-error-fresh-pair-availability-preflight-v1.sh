#!/usr/bin/env bash
# Fresh target-free CURRICULUM trajectory campaign and 300-pair capacity screen.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${PREREG_SOURCE_JOB:?}"; : "${PREREG_SOURCE_ATTEMPT:?}"; : "${PREREG_SOURCE_CODE:?}"
: "${TRAINING_SOURCE_JOB:?}"; : "${TRAINING_SOURCE_ATTEMPT:?}"; : "${TRAINING_SOURCE_CODE:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GAMES1="$ART/games-pool1"; GAMES2="$ART/games-pool2"; PROFILES="$ART/profile-shards"
mkdir -p "$W" "$IN" "$ART" "$GAMES1" "$GAMES2" "$PROFILES"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE="18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
CURRICULUM_ROOT="r2:jass-data/runs/$CURRICULUM_JOB/$CURRICULUM_ATTEMPT"
PREREG_ROOT="r2:jass-data/runs/$PREREG_SOURCE_JOB/$PREREG_SOURCE_ATTEMPT"
TRAINING_ROOT="r2:jass-data/runs/$TRAINING_SOURCE_JOB/$TRAINING_SOURCE_ATTEMPT"
NOPEN=1920
CANDIDATES=60000
POOL_SEED_1=2026082264
POOL_SEED_2=2026082265
SPLIT_SEED=2026082266
NSH=16
PAR=16
MOVETIME=0.1
PROFILE_PREFLIGHT_ROWS=1
MAX_PROFILE_MINUTES=180
CACHE_MB=128

EXCLUDE_SPECS="pool-curriculum-error-1492-pool1|r2:jass-data/runs/cpx62-1492-l3-curriculum-error-autopsy-v1/20260822T212256Z-454b3862|artefacts/curriculum-error-pool1-openings.fen
pool-curriculum-error-1492-pool2|r2:jass-data/runs/cpx62-1492-l3-curriculum-error-autopsy-v1/20260822T212256Z-454b3862|artefacts/curriculum-error-pool2-openings.fen
pool-curriculum-error-1504-pool1|r2:jass-data/runs/cpx62-1504-l3-curriculum-error-autopsy-v1/20260823T000356Z-ca1b91e1|artefacts/curriculum-error-pool1-openings.fen
pool-curriculum-error-1504-pool2|r2:jass-data/runs/cpx62-1504-l3-curriculum-error-autopsy-v1/20260823T000356Z-ca1b91e1|artefacts/curriculum-error-pool2-openings.fen"

MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        printf 'games_dumped=%s/7680\n' "$(find "$GAMES1" "$GAMES2" -name 'game-*.json' 2>/dev/null | wc -l)"
        printf 'profile_shards=%s/16\n' "$(find "$PROFILES" -name 'shard-*.json' 2>/dev/null | wc -l)"
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
  rm -rf "$W/build" "$IN" "$W/gate-"* "$W/profile-preflight" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-fresh-pair-availability-preflight-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree contract mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "${FRESH_TRAJECTORY_MINING_ONLY:-0}" = 1 ] && [ "${NO_EXACT_ACTION_TARGETS:-0}" = 1 ] || die "target-free mining guards missing"
[ "${NO_FIT:-0}" = 1 ] && [ "${NO_PATTERNEVAL_FIT:-0}" = 1 ] && [ "${NO_STRENGTH_GAMES:-0}" = 1 ] || die "fit/force guards missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] && [ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"
say "experiment=CURRICULUM_ERROR_FRESH_PAIR_AVAILABILITY games=7680 pools=2 targets=0 fits=0"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_curriculum_error_fresh_pair_availability_preflight.py
python3 -m unittest \
  jobs.tests.test_l3_curriculum_error_fresh_pair_availability_preflight \
  jobs.tests.test_l3_curriculum_error_fresh_pair_availability_preflight_template \
  jobs.tests.test_l3_curriculum_error_residual_power_extension_preregistration \
  jobs.tests.test_l3_curriculum_search_error_atlas >"$W/tests.log" 2>&1

stage fetch-authenticate-preregistration-training-cost-and-curriculum
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$PREREG_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=preregistration.json \
  --out-dir "$IN" --report "$ART/verified-preregistration.json" --expected-state completed \
  >"$W/fetch-preregistration.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$TRAINING_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=training-summary.json \
  --file artefacts/atlas-cost-preflight.json=historical-exact-cost.json \
  --file artefacts/search-params.txt=search-params.txt \
  --out-dir "$IN" --report "$ART/verified-training-cost.json" --expected-state completed \
  >"$W/fetch-training-cost.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=curriculum-summary.json \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" --expected-state completed \
  >"$W/fetch-curriculum.log" 2>&1
gunzip -t "$IN/curriculum.pjtw.gz"; gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
python3 - "$IN" "$ART" "$PREREG_SOURCE_JOB" "$PREREG_SOURCE_ATTEMPT" "$PREREG_SOURCE_CODE" \
  "$TRAINING_SOURCE_JOB" "$TRAINING_SOURCE_ATTEMPT" "$TRAINING_SOURCE_CODE" \
  "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" "$CURRICULUM_CODE" "$CURRICULUM_SHA" <<'PY_AUTH'
import hashlib,json,sys
from pathlib import Path
src,art=map(Path,sys.argv[1:3]); prereg=tuple(sys.argv[3:6]); training=tuple(sys.argv[6:9]); curriculum=tuple(sys.argv[9:12]); champion=sys.argv[12]
for name,want in (("verified-preregistration.json",prereg),("verified-training-cost.json",training),("verified-curriculum.json",curriculum)):
 receipt=json.load(open(art/name)); got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'))
 if got!=want or receipt.get('result_state')!='completed' or receipt.get('exit_code')!=0: raise SystemExit(f'{name} identity/state drift got={got} want={want}')
registration=json.load(open(src/'preregistration.json')); training_summary=json.load(open(src/'training-summary.json')); cost=json.load(open(src/'historical-exact-cost.json'))
if registration.get('verdict')!='JASS_CURRICULUM_ERROR_RESIDUAL_POWER_EXTENSION_PREREGISTERED' or registration.get('passed') is not True: raise SystemExit('1514 preregistration drift')
if registration.get('fresh_pair_mining_authorized') is not True or registration.get('fresh_target_reconstruction_authorized') is not False: raise SystemExit('1514 authorization drift')
if training_summary.get('verdict')!='JASS_CURRICULUM_ERROR_TRACE_RESIDUAL_TRAINING_NOT_ESTABLISHED': raise SystemExit('1508 training verdict drift')
if cost.get('passed') is not True or int(cost.get('total_pairs',0))<=0: raise SystemExit('1508 exact cost drift')
(art/'source-chain.json').write_text(json.dumps({'preregistration':{'job':prereg[0],'attempt':prereg[1],'code_sha':prereg[2]},'training_cost':{'job':training[0],'attempt':training[1],'code_sha':training[2]},'curriculum':{'job':curriculum[0],'attempt':curriculum[1],'code_sha':curriculum[2],'model_raw_sha256':champion}},indent=2,sort_keys=True)+'\n')
PY_AUTH
[ "$(sha256sum "$W/curriculum.pjtw" | awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM raw hash drift"
[ "$(tr ',' '\n' <"$IN/search-params.txt" | wc -l)" -eq 63 ] || die "Q00 key count drift"
cp "$IN/search-params.txt" "$ART/search-params.txt"

stage build-current-exact-fold-tempo-engine-with-root-trace
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
printf 'hello\nquit\n' | timeout 60 "$J" --pattern "$W/curriculum.pjtw" --search-params "$(cat "$ART/search-params.txt")" >"$W/load.log" 2>&1
grep -q '^ready' "$W/load.log" || die "CURRICULUM does not load"

stage fetch-historical-opening-exclusions
EXCL_ARGS=(--exclude data/dilf_combinations.fen); EXCL_NAMES=(dilf_combinations)
while IFS='|' read -r label prefix remote_path; do
  [ -n "${label:-}" ] || continue
  timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$prefix" \
    --file "$remote_path=$label.fen" --out-dir "$IN" \
    --report "$ART/verified-exclude-$label.json" --expected-state completed \
    >"$W/fetch-$label.log" 2>&1 || die "historical pool fetch failed: $label"
  EXCL_ARGS+=(--exclude "$IN/$label.fen"); EXCL_NAMES+=("$label")
done <<<"$EXCLUDE_SPECS"
[ "${#EXCL_NAMES[@]}" -eq 5 ] || die "exclusion count drift"

generate_pool(){
  local index="$1" seed="$2" out="fresh-pair-pool${1}-openings"
  local extra=("${EXCL_ARGS[@]}")
  [ "$index" -eq 2 ] && extra+=(--exclude "$ART/fresh-pair-pool1-openings.fen")
  for pass in a b; do
    "$J" --gen-opening-pool "$CANDIDATES" "$W/pool${index}-cand-$pass.fen" 8 32 20 "$seed" >"$W/pool${index}-gen-$pass.log" 2>&1
  done
  cmp -s "$W/pool${index}-cand-a.fen" "$W/pool${index}-cand-b.fen" || die "pool$index nondeterministic"
  python3 jobs/tools/select_independent_opening_pool.py --candidates "$W/pool${index}-cand-a.fen" \
    --expected "$NOPEN" "${extra[@]}" --generator-seed "$seed" \
    --out "$ART/$out.fen" --manifest "$ART/$out.json" >"$W/pool${index}-select.log" 2>&1
  python3 jobs/tools/validate_opening_pool.py --pool "$ART/$out.fen" --expected "$NOPEN" \
    --generator-seed "$seed" "${extra[@]}" --out "$ART/$out-provenance.json" >"$W/pool${index}-validate.log" 2>&1
}
stage generate-two-fresh-disjoint-trajectory-pools
generate_pool 1 "$POOL_SEED_1"; generate_pool 2 "$POOL_SEED_2"
[ "$(grep -Fx -f "$ART/fresh-pair-pool1-openings.fen" "$ART/fresh-pair-pool2-openings.fen" | grep -c . || true)" -eq 0 ] || die "fresh pools overlap"

stage play-and-dump-target-free-curriculum-trajectories-pool1
python3 jobs/tools/run_jass_gate_bounded.py --jass "$J" --pattern-a "$W/curriculum.pjtw" --pattern-b "$W/curriculum.pjtw" \
  --search-params-a "$(cat "$ART/search-params.txt")" --search-params-b "$(cat "$ART/search-params.txt")" \
  --openings-file "$ART/fresh-pair-pool1-openings.fen" --movetime "$MOVETIME" --pairs 1 --max-plies 160 \
  --nshards "$NSH" --max-parallel "$PAR" --timeout 21600 --game-timeout 180 \
  --dump-games-dir "$GAMES1" --work-dir "$W/gate-pool1" --out "$ART/campaign-pool1.json" >"$W/campaign-pool1.log" 2>&1
stage play-and-dump-target-free-curriculum-trajectories-pool2
python3 jobs/tools/run_jass_gate_bounded.py --jass "$J" --pattern-a "$W/curriculum.pjtw" --pattern-b "$W/curriculum.pjtw" \
  --search-params-a "$(cat "$ART/search-params.txt")" --search-params-b "$(cat "$ART/search-params.txt")" \
  --openings-file "$ART/fresh-pair-pool2-openings.fen" --movetime "$MOVETIME" --pairs 1 --max-plies 160 \
  --nshards "$NSH" --max-parallel "$PAR" --timeout 21600 --game-timeout 180 \
  --dump-games-dir "$GAMES2" --work-dir "$W/gate-pool2" --out "$ART/campaign-pool2.json" >"$W/campaign-pool2.log" 2>&1
[ "$(find "$GAMES1" "$GAMES2" -name 'game-*.json' | wc -l)" -eq 7680 ] || die "fresh game count drift"
python3 - "$ART/campaign-pool1.json" "$ART/campaign-pool2.json" <<'PY_CAMPAIGN'
import json,sys
for path in sys.argv[1:]:
 row=json.load(open(path))
 if row.get('complete') is not True or int(row.get('n',-1))!=3840:
  raise SystemExit(f'incomplete fresh campaign: {path} {row}')
 dumps=row.get('complete_game_dumps',{})
 if dumps.get('trajectory_contract_valid') is not True or int(dumps.get('games',-1))!=3840:
  raise SystemExit(f'fresh dump contract drift: {path} {dumps}')
PY_CAMPAIGN

stage prepare-loss-trajectories-without-action-targets
python3 jobs/tools/l3_curriculum_error_learning.py prepare --games-dir "$GAMES1" --games-dir "$GAMES2" \
  --split-seed "$SPLIT_SEED" --out "$ART/fresh-error-selection.json" >"$W/prepare-games.log" 2>&1
python3 -m jobs.tools.l3_curriculum_error_fresh_pair_availability_preflight prepare \
  --selection "$ART/fresh-error-selection.json" --output "$ART/fresh-profile-selection.json" >"$W/prepare-profiles.log" 2>&1

stage root-trace-profile-cost-preflight
mkdir -p "$W/profile-preflight"; T0=$(date +%s); pids=()
for shard in $(seq 0 $((NSH-1))); do
  python3 jobs/tools/l3_curriculum_search_error_atlas.py profile --selection "$ART/fresh-profile-selection.json" \
    --jass "$J" --champion "$W/curriculum.pjtw" --search-params "$ART/search-params.txt" \
    --max-rows "$PROFILE_PREFLIGHT_ROWS" --shard "$shard" --nshards "$NSH" \
    --out "$W/profile-preflight/shard-$shard.json" >"$W/profile-preflight-$shard.log" 2>&1 & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done; T1=$(date +%s)
python3 - "$ART/fresh-profile-selection.json" "$W/profile-preflight" "$ART/profile-cost-preflight.json" "$((T1-T0))" "$MAX_PROFILE_MINUTES" <<'PY_COST'
import json,sys
from pathlib import Path
selection=json.load(open(sys.argv[1])); root=Path(sys.argv[2]); elapsed=max(int(sys.argv[4]),1); maximum=int(sys.argv[5])
files=list(root.glob('shard-*.json')); rows=sum(len(json.load(open(path))['rows']) for path in files); total=len(selection['rows']); projected=elapsed*total/max(rows,1)/60
payload={'schema':'jass.curriculum_error_fresh_profile_cost.v1','sample_shards':len(files),'sample_rows':rows,'total_rows':total,'elapsed_seconds':elapsed,'projected_minutes':projected,'maximum_minutes':maximum,'passed':len(files)==16 and rows>0 and projected<=maximum}
Path(sys.argv[3]).write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
if not payload['passed']: raise SystemExit(f'fresh profile cost failed: {payload}')
PY_COST

stage profile-all-fresh-loss-states-target-free
pids=()
for shard in $(seq 0 $((NSH-1))); do
  python3 jobs/tools/l3_curriculum_search_error_atlas.py profile --selection "$ART/fresh-profile-selection.json" \
    --jass "$J" --champion "$W/curriculum.pjtw" --search-params "$ART/search-params.txt" \
    --shard "$shard" --nshards "$NSH" --out "$PROFILES/shard-$shard.json" \
    >"$W/profile-$shard.log" 2>&1 & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done
[ "$(find "$PROFILES" -name 'shard-*.json' | wc -l)" -eq "$NSH" ] || die "profile shard count drift"

stage audit-availability-lattice-and-cost-without-targets
profile_args=(); for shard in $(seq 0 $((NSH-1))); do profile_args+=(--profile-shard "$PROFILES/shard-$shard.json"); done
python3 -m jobs.tools.l3_curriculum_error_fresh_pair_availability_preflight audit \
  --preregistration "$IN/preregistration.json" --selection "$ART/fresh-profile-selection.json" \
  "${profile_args[@]}" --profile-cost "$ART/profile-cost-preflight.json" \
  --historical-exact-cost "$IN/historical-exact-cost.json" \
  --report "$ART/fresh-pair-availability.json" --lattice "$ART/fresh-pair-lattice.json" >"$W/audit.log" 2>&1

stage authenticate-and-publish-terminal-verdict
python3 - "$ART" "$EXPECTED_CODE_SHA" "$PREREG_SOURCE_JOB" "$PREREG_SOURCE_ATTEMPT" "$PREREG_SOURCE_CODE" \
  "$CURRICULUM_SHA" "$POOL_SEED_1" "$POOL_SEED_2" "$SPLIT_SEED" <<'PY_FINAL'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); code=sys.argv[2]; prereg=tuple(sys.argv[3:6]); champion=sys.argv[6]; seeds=list(map(int,sys.argv[7:10]))
report=json.load(open(art/'fresh-pair-availability.json')); lattice=json.load(open(art/'fresh-pair-lattice.json'))
if report.get('verdict') not in {'JASS_CURRICULUM_ERROR_FRESH_PAIR_AVAILABILITY_READY','JASS_CURRICULUM_ERROR_FRESH_PAIR_AVAILABILITY_NOT_ESTABLISHED'}: raise SystemExit('availability verdict drift')
for key in ('new_targets','exact_action_value_reads','holdout_reads','fits','pattern_eval_fits','production_model_fits','strength_games','frozen_reads'):
 if int(report.get(key,-1))!=0: raise SystemExit(f'forbidden counter drift {key}')
if report.get('new_selfplay_games')!=7680 or lattice.get('exact_action_value_reads')!=0: raise SystemExit('fresh trajectory scope drift')
payload={**report,'schema':'jass.curriculum_error_fresh_pair_availability_terminal.v1','code_sha':code,
 'preregistration_source':{'job':prereg[0],'attempt':prereg[1],'code_sha':prereg[2]},
 'champion_sha256':champion,'campaign':{'pools':2,'openings_per_pool':1920,'games':7680,
 'pool_seeds':seeds[:2],'split_seed':seeds[2],'same_byte_identical_champion_both_sides':True,
 'disjoint_from_1492_1504_and_static_pool':True},'weights_bit_identical':True,
 'automatic_continuation':False,'promotion_authorized':False}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/report['verdict']).touch()
for name in ('NEW_TARGETS__0','EXACT_ACTION_VALUE_READS__0','HOLDOUT_READS__0','FITS__0','PATTERNEVAL_FITS__0','PRODUCTION_MODEL_FITS__0','STRENGTH_GAMES__0','NEW_SELFPLAY__7680','FROZEN_READS__0','PRODUCTION_RULE_AUTHORIZED__FALSE','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_CONTINUATION__FALSE'):
 (art/name).touch()
if report.get('fresh_target_reconstruction_authorized'):
 (art/'FRESH_TARGET_RECONSTRUCTION_AUTHORIZED__TRUE').touch()
PY_FINAL
VERDICT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
stage completed
say "$VERDICT games=7680 targets=0 fits=0 strength=0 frozen=0 promotion=false"
