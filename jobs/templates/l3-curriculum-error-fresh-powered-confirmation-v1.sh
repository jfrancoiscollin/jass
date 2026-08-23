#!/usr/bin/env bash
# Exact first-300 fresh-pair labelling and frozen-rule powered confirmation.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${AVAILABILITY_SOURCE_JOB:?}"; : "${AVAILABILITY_SOURCE_ATTEMPT:?}"; : "${AVAILABILITY_SOURCE_CODE:?}"
: "${PREREG_SOURCE_JOB:?}"; : "${PREREG_SOURCE_ATTEMPT:?}"; : "${PREREG_SOURCE_CODE:?}"
: "${TRAINING_SOURCE_JOB:?}"; : "${TRAINING_SOURCE_ATTEMPT:?}"; : "${TRAINING_SOURCE_CODE:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
PROFILE="$IN/fresh-profile-shards"; GAMES="$IN/source-games"; TARGETS="$ART/exact-target-batches"
FINAL_SHARDS="$ART/fresh-confirmation-atlas-shards"
mkdir -p "$W" "$IN" "$ART" "$PROFILE" "$GAMES" "$TARGETS" "$FINAL_SHARDS"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

AVAILABILITY_ROOT="r2:jass-data/runs/$AVAILABILITY_SOURCE_JOB/$AVAILABILITY_SOURCE_ATTEMPT"
PREREG_ROOT="r2:jass-data/runs/$PREREG_SOURCE_JOB/$PREREG_SOURCE_ATTEMPT"
TRAINING_ROOT="r2:jass-data/runs/$TRAINING_SOURCE_JOB/$TRAINING_SOURCE_ATTEMPT"
CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE="18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
CURRICULUM_ROOT="r2:jass-data/runs/$CURRICULUM_JOB/$CURRICULUM_ATTEMPT"
NSH=16; MAX_ROUNDS=32; TARGET_STATES_PER_ROUND=256; CACHE_MB=128

MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        printf 'exact_batches=%s\n' "$(find "$TARGETS" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)"
        if [ -s "$W/current-cache.json" ]; then
          python3 - "$W/current-cache.json" <<'PY_PROGRESS'
import json,sys
row=json.load(open(sys.argv[1])); print(f"judged_states={len(row.get('judgments',{}))}"); print(f"target_batch_receipts={len(row.get('batch_receipts',[]))}")
PY_PROGRESS
        fi
      } >"$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 120
    done ) & MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -s "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$TARGETS" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-fresh-powered-confirmation-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree contract mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "${EXACT_FRESH_CONFIRMATION_ONLY:-0}" = 1 ] && [ "${FIRST_VALID_300_ONLY:-0}" = 1 ] || die "fresh confirmation guards missing"
[ "${FIT_IMMUTABLE_1508_ONLY:-0}" = 1 ] && [ "${NO_FIT_ON_FRESH:-0}" = 1 ] || die "fit isolation guards missing"
[ "${NO_PATTERNEVAL_FIT:-0}" = 1 ] && [ "${NO_STRENGTH_GAMES:-0}" = 1 ] && [ "${NO_NEW_SELFPLAY:-0}" = 1 ] || die "forbidden compute guards missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] && [ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"
say "experiment=CURRICULUM_ERROR_FRESH_POWERED_CONFIRMATION pairs=300 alpha=300 cap=100 mode=strict_both_change threshold=10"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/fetch_result_subset.py jobs/tools/l3_curriculum_error_fresh_powered_confirmation.py
python3 -m unittest \
  jobs.tests.test_fetch_result_subset \
  jobs.tests.test_l3_curriculum_error_fresh_powered_confirmation \
  jobs.tests.test_l3_curriculum_error_fresh_powered_confirmation_template \
  jobs.tests.test_l3_curriculum_error_residual_power_extension_preregistration \
  jobs.tests.test_l3_curriculum_search_error_atlas >"$W/tests.log" 2>&1

stage fetch-authenticate-immutable-sources
availability_args=()
for shard in $(seq 0 15); do availability_args+=(--file "artefacts/profile-shards/shard-$shard.json=fresh-profile-$shard.json"); done
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$AVAILABILITY_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=availability.json \
  --file artefacts/fresh-pair-lattice.json=fresh-pair-lattice.json \
  --file artefacts/fresh-error-selection.json=fresh-error-selection.json \
  --file artefacts/fresh-profile-selection.json=fresh-profile-selection.json \
  --file artefacts/search-params.txt=search-params.txt \
  "${availability_args[@]}" --out-dir "$IN" --report "$ART/verified-availability-source.json" \
  --expected-state completed >"$W/fetch-availability.log" 2>&1
for shard in $(seq 0 15); do mv "$IN/fresh-profile-$shard.json" "$PROFILE/shard-$shard.json"; done
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$PREREG_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=preregistration.json \
  --out-dir "$IN" --report "$ART/verified-preregistration.json" --expected-state completed \
  >"$W/fetch-preregistration.log" 2>&1
training_args=()
for shard in $(seq 0 15); do training_args+=(--file "artefacts/gate-fit-atlas-shards/shard-$shard.json=training-atlas-$shard.json"); done
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$TRAINING_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=training-summary.json \
  --file artefacts/trace-residual-training.json=training-report.json \
  --file artefacts/trace-residual-model.json=failed-model.json \
  --file artefacts/gate-fit-pairs.json=training-pairs.json \
  "${training_args[@]}" --out-dir "$IN" --report "$ART/verified-training-source.json" \
  --expected-state completed >"$W/fetch-training.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" --expected-state completed \
  >"$W/fetch-curriculum.log" 2>&1
gunzip -t "$IN/curriculum.pjtw.gz"; gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
python3 - "$ART" "$AVAILABILITY_SOURCE_JOB" "$AVAILABILITY_SOURCE_ATTEMPT" "$AVAILABILITY_SOURCE_CODE" \
  "$PREREG_SOURCE_JOB" "$PREREG_SOURCE_ATTEMPT" "$PREREG_SOURCE_CODE" \
  "$TRAINING_SOURCE_JOB" "$TRAINING_SOURCE_ATTEMPT" "$TRAINING_SOURCE_CODE" \
  "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" "$CURRICULUM_CODE" <<'PY_AUTH'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); wants=[tuple(sys.argv[i:i+3]) for i in (2,5,8,11)]
for name,want in zip(('verified-availability-source.json','verified-preregistration.json','verified-training-source.json','verified-curriculum.json'),wants):
 row=json.load(open(art/name)); got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha'))
 if got!=want or row.get('result_state')!='completed' or row.get('exit_code')!=0: raise SystemExit(f'{name} identity/state drift got={got} want={want}')
PY_AUTH
[ "$(sha256sum "$W/curriculum.pjtw" | awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM raw hash drift"

stage build-byte-identical-1508-exact-fold-tempo-engine
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }; done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON \
  -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests >"$W/build.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB ctest --test-dir "$W/build" --output-on-failure >"$W/ctest.log" 2>&1
J="$W/build/jass"
python3 - "$IN/training-report.json" "$J" "$W/curriculum.pjtw" "$IN/search-params.txt" <<'PY_ENGINE'
import hashlib,json,sys
sha=lambda p:hashlib.sha256(open(p,'rb').read()).hexdigest(); report=json.load(open(sys.argv[1]))
got={'jass_sha256':sha(sys.argv[2]),'champion_sha256':sha(sys.argv[3]),'search_params_sha256':sha(sys.argv[4])}
for key,value in got.items():
 if report.get(key)!=value: raise SystemExit(f'1508 byte identity drift {key}: {value} != {report.get(key)}')
PY_ENGINE
printf 'hello\nquit\n' | timeout 60 "$J" --pattern "$W/curriculum.pjtw" --search-params "$(cat "$IN/search-params.txt")" >"$W/load.log" 2>&1
grep -q '^ready' "$W/load.log" || die "CURRICULUM does not load"

stage derive-candidate-game-subset-before-exact-targets
profile_args=(); for shard in $(seq 0 15); do profile_args+=(--profile-shard "$PROFILE/shard-$shard.json"); done
python3 -m jobs.tools.l3_curriculum_error_fresh_powered_confirmation prepare \
  --preregistration "$IN/preregistration.json" --availability "$IN/availability.json" \
  --lattice "$IN/fresh-pair-lattice.json" --source-selection "$IN/fresh-error-selection.json" \
  --profile-selection "$IN/fresh-profile-selection.json" "${profile_args[@]}" \
  --prepared "$ART/fresh-confirmation-prepared.json" --paths "$W/required-games.txt" >"$W/prepare.log" 2>&1

stage bulk-fetch-and-byte-authenticate-only-candidate-games
timeout 3600s python3 jobs/tools/fetch_result_subset.py --prefix "$AVAILABILITY_ROOT" \
  --paths-file "$W/required-games.txt" --out-dir "$GAMES" \
  --report "$ART/verified-candidate-games.json" --expected-state completed >"$W/fetch-candidate-games.log" 2>&1
python3 - "$ART/verified-candidate-games.json" "$AVAILABILITY_SOURCE_JOB" "$AVAILABILITY_SOURCE_ATTEMPT" "$AVAILABILITY_SOURCE_CODE" <<'PY_GAMES'
import json,sys
row=json.load(open(sys.argv[1])); want=tuple(sys.argv[2:5]); got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha'))
if got!=want or row.get('state')!='verified' or int(row.get('requested_files',0))<=0: raise SystemExit(f'candidate-game receipt drift got={got} want={want}')
PY_GAMES

stage lossless-historical-move-normalization
python3 -m jobs.tools.l3_curriculum_error_fresh_powered_confirmation normalize \
  --prepared "$ART/fresh-confirmation-prepared.json" --lattice "$IN/fresh-pair-lattice.json" \
  --profile-selection "$IN/fresh-profile-selection.json" "${profile_args[@]}" \
  --games-dir "$GAMES/artefacts/games-pool1" --games-dir "$GAMES/artefacts/games-pool2" \
  --jass "$J" --catalog "$ART/fresh-confirmation-catalog.json" >"$W/normalize.log" 2>&1

stage exact-label-first-300-valid-pairs-in-frozen-order
CACHE=""
COMPLETE=0
for round in $(seq 0 $((MAX_ROUNDS-1))); do
  R="$TARGETS/round-$round"; mkdir -p "$R/shards"
  args=(--lattice "$IN/fresh-pair-lattice.json" --catalog "$ART/fresh-confirmation-catalog.json" \
        --max-states "$TARGET_STATES_PER_ROUND" --plan "$R/plan.json" --batch "$R/batch-pairs.json")
  if [ -n "$CACHE" ]; then args+=(--cache "$CACHE"); else args+=(--cache-output "$R/cache-in.json"); CACHE="$R/cache-in.json"; fi
  python3 -m jobs.tools.l3_curriculum_error_fresh_powered_confirmation plan "${args[@]}" >"$W/plan-$round.log" 2>&1
  status=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["status"])' "$R/plan.json")
  if [ "$status" = complete ]; then
    COMPLETE=1
    cp "$CACHE" "$W/current-cache.json"
    cp "$CACHE" "$ART/fresh-target-cache.json"
    cp "$R/plan.json" "$ART/fresh-target-selection-plan.json"
    break
  fi
  [ "$status" = needs_targets ] || die "unknown target-plan status $status"
  pids=()
  for shard in $(seq 0 15); do
    timeout 43200s python3 jobs/tools/l3_curriculum_search_error_atlas.py atlas \
      --pairs "$R/batch-pairs.json" --jass "$J" --champion "$W/curriculum.pjtw" \
      --search-params "$IN/search-params.txt" --judge-depth 12 --shard "$shard" --nshards 16 \
      --out "$R/shards/shard-$shard.json" >"$W/exact-r${round}-s${shard}.log" 2>&1 & pids+=("$!")
  done
  for pid in "${pids[@]}"; do wait "$pid"; done
  shard_args=(); for shard in $(seq 0 15); do shard_args+=(--atlas-shard "$R/shards/shard-$shard.json"); done
  python3 -m jobs.tools.l3_curriculum_error_fresh_powered_confirmation ingest \
    --cache "$CACHE" --catalog "$ART/fresh-confirmation-catalog.json" --batch "$R/batch-pairs.json" \
    "${shard_args[@]}" --output "$R/cache-out.json" >"$W/ingest-$round.log" 2>&1
  CACHE="$R/cache-out.json"; cp "$CACHE" "$W/current-cache.json"
done
[ "$COMPLETE" -eq 1 ] || die "first-300 exact pair selection exceeded $MAX_ROUNDS batches"

stage finalize-repacked-authenticated-fresh-atlas
python3 -m jobs.tools.l3_curriculum_error_fresh_powered_confirmation finalize \
  --lattice "$IN/fresh-pair-lattice.json" --catalog "$ART/fresh-confirmation-catalog.json" \
  --cache "$ART/fresh-target-cache.json" --pairs "$ART/fresh-confirmation-pairs.json" --shards-dir "$FINAL_SHARDS" >"$W/finalize-pairs.log" 2>&1
[ "$(find "$FINAL_SHARDS" -name 'shard-*.json' | wc -l)" -eq 16 ] || die "fresh final atlas shard count drift"

stage fit-only-immutable-1508-and-powered-fresh-confirmation
training_shards=(); fresh_shards=()
for shard in $(seq 0 15); do
  training_shards+=(--training-shard "$IN/training-atlas-$shard.json")
  fresh_shards+=(--fresh-shard "$FINAL_SHARDS/shard-$shard.json")
done
python3 -m jobs.tools.l3_curriculum_error_fresh_powered_confirmation confirm \
  --preregistration "$IN/preregistration.json" --training-report "$IN/training-report.json" \
  --failed-model "$IN/failed-model.json" --training-pairs "$IN/training-pairs.json" \
  "${training_shards[@]}" --fresh-pairs "$ART/fresh-confirmation-pairs.json" \
  "${fresh_shards[@]}" --target-cache "$ART/fresh-target-cache.json" \
  --report "$ART/fresh-powered-confirmation.json" >"$W/confirm.log" 2>&1

stage authenticate-and-publish-terminal-verdict
python3 - "$ART" "$EXPECTED_CODE_SHA" "$AVAILABILITY_SOURCE_JOB" "$AVAILABILITY_SOURCE_ATTEMPT" "$AVAILABILITY_SOURCE_CODE" \
  "$PREREG_SOURCE_JOB" "$PREREG_SOURCE_ATTEMPT" "$PREREG_SOURCE_CODE" \
  "$TRAINING_SOURCE_JOB" "$TRAINING_SOURCE_ATTEMPT" "$TRAINING_SOURCE_CODE" <<'PY_FINAL'
import json,re,sys
from pathlib import Path
art=Path(sys.argv[1]); code=sys.argv[2]; availability=tuple(sys.argv[3:6]); prereg=tuple(sys.argv[6:9]); training=tuple(sys.argv[9:12])
report=json.load(open(art/'fresh-powered-confirmation.json'))
if report.get('verdict') not in {'JASS_CURRICULUM_ERROR_FRESH_POWERED_CONFIRMATION_READY','JASS_CURRICULUM_ERROR_FRESH_POWERED_CONFIRMATION_NOT_ESTABLISHED'}: raise SystemExit('fresh confirmation verdict drift')
if report.get('fresh_extension_labels_used_for_fit') is not False or report.get('fresh_pairs')!=300: raise SystemExit('fresh isolation/cardinality drift')
for key in ('pattern_eval_fits','production_model_fits','strength_games','new_selfplay_games','frozen_reads'):
 if int(report.get(key,-1))!=0: raise SystemExit(f'forbidden counter drift {key}')
payload={**report,'schema':'jass.curriculum_error_fresh_powered_confirmation_terminal.v1','code_sha':code,
 'availability_source':{'job':availability[0],'attempt':availability[1],'code_sha':availability[2]},
 'preregistration_source':{'job':prereg[0],'attempt':prereg[1],'code_sha':prereg[2]},
 'training_source':{'job':training[0],'attempt':training[1],'code_sha':training[2]},
 'automatic_continuation':False,'promotion_authorized':False}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n'); (art/report['verdict']).touch()
clean=lambda value:re.sub(r'[^A-Za-z0-9.+-]+','_',str(value)).strip('_')
m=report['metrics']; sham=report['sham']
(art/f"PAIRS__300__POOL1_{report['fresh_pairs_by_pool'].get('pool1',0)}__POOL2_{report['fresh_pairs_by_pool'].get('pool2',0)}").touch()
(art/f"INTERVENTIONS__ERROR_{m['error_interventions']}__CONTROL_{m['control_interventions']}").touch()
(art/f"EFFECT__ERR_{clean(round(m['error_improvement']['mean'],3))}__ERRLO_{clean(round(m['error_improvement']['ci95'][0],3))}__PAIR_{clean(round(m['paired_error_minus_control']['mean'],3))}__PAIRLO_{clean(round(m['paired_error_minus_control']['ci95'][0],3))}").touch()
(art/f"SHAM__REAL_{clean(round(sham['real_paired_mean_cp'],3))}__Q99_{clean(round(sham['paired_mean_q99_cp'],3))}__PASS_{str(sham['real_exceeds_sham_q99']).upper()}").touch()
for name in ('FRESH_EXTENSION_LABELS_USED_FOR_FIT__FALSE','PATTERNEVAL_FITS__0','PRODUCTION_MODEL_FITS__0','STRENGTH_GAMES__0','NEW_SELFPLAY__0','FROZEN_READS__0','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_CONTINUATION__FALSE'): (art/name).touch()
PY_FINAL
VERDICT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
stage completed
say "$VERDICT pairs=300 fit_source=1508 fresh_fit=0 strength=0 frozen=0 promotion=false"
