#!/usr/bin/env bash
# Exact-label the sealed 300+300 OOS pairs and audit the anchored local refit.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${AVAILABILITY_SOURCE_JOB:?}"; : "${AVAILABILITY_SOURCE_ATTEMPT:?}"; : "${AVAILABILITY_SOURCE_CODE:?}"
: "${PREREG_SOURCE_JOB:?}"; : "${PREREG_SOURCE_ATTEMPT:?}"; : "${PREREG_SOURCE_CODE:?}"
: "${FIT_SOURCE_JOB:?}"; : "${FIT_SOURCE_ATTEMPT:?}"; : "${FIT_SOURCE_CODE:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
PROFILE="$IN/profile-shards"; GAMES="$IN/source-games"; TARGETS="$ART/exact-target-batches"; FINAL_SHARDS="$ART/oos-atlas-shards"
mkdir -p "$W" "$IN" "$ART" "$PROFILE" "$GAMES" "$TARGETS" "$FINAL_SHARDS"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

AVAILABILITY_ROOT="r2:jass-data/runs/$AVAILABILITY_SOURCE_JOB/$AVAILABILITY_SOURCE_ATTEMPT"
PREREG_ROOT="r2:jass-data/runs/$PREREG_SOURCE_JOB/$PREREG_SOURCE_ATTEMPT"
FIT_ROOT="r2:jass-data/runs/$FIT_SOURCE_JOB/$FIT_SOURCE_ATTEMPT"
CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE="18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
CURRICULUM_ROOT="r2:jass-data/runs/$CURRICULUM_JOB/$CURRICULUM_ATTEMPT"
MODULE=jobs.tools.l3_curriculum_error_anchored_local_refit_oos_campaign
PAIRS=600; NSH=16; MAX_ROUNDS="${OOS_MAX_ROUNDS:-64}"; TARGET_STATES_PER_ROUND=256; CACHE_MB=128

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
row=json.load(open(sys.argv[1])); print(f"judged_states={len(row.get('judgments',{}))}")
PY_PROGRESS
        fi
      } >"$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120
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

[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-anchored-local-refit-oos-audit-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree contract mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "${SEALED_OOS_ONLY:-0}" = 1 ] && [ "${FIRST_300_PER_POOL_FROZEN_ONLY:-0}" = 1 ] || die "sealed OOS guards missing"
[ "${NO_FIT:-0}" = 1 ] && [ "${NO_STRENGTH_GAMES:-0}" = 1 ] && [ "${NO_NEW_SELFPLAY:-0}" = 1 ] || die "forbidden compute guards missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] && [ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_curriculum_error_anchored_local_refit_oos_campaign.py jobs/tools/l3_curriculum_error_anchored_local_refit_oos_audit.py
python3 -m unittest \
  jobs.tests.test_l3_curriculum_error_anchored_local_refit_oos_campaign \
  jobs.tests.test_l3_curriculum_error_anchored_local_refit_oos_audit \
  jobs.tests.test_l3_curriculum_error_fresh_powered_confirmation >"$W/tests.log" 2>&1

stage fetch-authenticate-sealed-sources
profile_args=(); for shard in $(seq 0 15); do profile_args+=(--file "artefacts/profile-shards/shard-$shard.json=profile-$shard.json"); done
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$AVAILABILITY_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=availability.json \
  --file artefacts/fresh-pair-lattice.json=lattice.json \
  --file artefacts/fresh-error-selection.json=source-selection.json \
  --file artefacts/fresh-profile-selection.json=profile-selection.json \
  --file artefacts/search-params.txt=search-params.txt "${profile_args[@]}" \
  --out-dir "$IN" --report "$ART/verified-availability.json" --expected-state completed >"$W/fetch-availability.log" 2>&1
for shard in $(seq 0 15); do mv "$IN/profile-$shard.json" "$PROFILE/shard-$shard.json"; done
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$PREREG_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=preregistration.json \
  --out-dir "$IN" --report "$ART/verified-preregistration.json" --expected-state completed >"$W/fetch-preregistration.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$FIT_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=fit-report.json \
  --file artefacts/anchored-local-residual-model.json=fit-model.json \
  --out-dir "$IN" --report "$ART/verified-fit.json" --expected-state completed >"$W/fetch-fit.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" --expected-state completed >"$W/fetch-curriculum.log" 2>&1
gunzip -t "$IN/curriculum.pjtw.gz"; gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
python3 - "$ART" "$AVAILABILITY_SOURCE_JOB" "$AVAILABILITY_SOURCE_ATTEMPT" "$AVAILABILITY_SOURCE_CODE" \
  "$PREREG_SOURCE_JOB" "$PREREG_SOURCE_ATTEMPT" "$PREREG_SOURCE_CODE" \
  "$FIT_SOURCE_JOB" "$FIT_SOURCE_ATTEMPT" "$FIT_SOURCE_CODE" \
  "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" "$CURRICULUM_CODE" <<'PY_AUTH'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); wants=[tuple(sys.argv[i:i+3]) for i in (2,5,8,11)]
for name,want in zip(('verified-availability.json','verified-preregistration.json','verified-fit.json','verified-curriculum.json'),wants):
 row=json.load(open(art/name)); got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha'))
 if got!=want or row.get('result_state')!='completed' or row.get('exit_code')!=0: raise SystemExit(f'{name} identity/state drift got={got} want={want}')
PY_AUTH
[ "$(sha256sum "$W/curriculum.pjtw" | awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM hash drift"

stage build-byte-identical-exact-fold-tempo-engine
EGDIR=""; for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }; done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests >"$W/build.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB ctest --test-dir "$W/build" --output-on-failure >"$W/ctest.log" 2>&1
J="$W/build/jass"
python3 - "$IN/fit-report.json" "$J" "$W/curriculum.pjtw" "$IN/search-params.txt" <<'PY_ENGINE'
import hashlib,json,sys
sha=lambda p:hashlib.sha256(open(p,'rb').read()).hexdigest(); report=json.load(open(sys.argv[1])); identities=report['identities']
got={'jass_sha256':sha(sys.argv[2]),'champion_sha256':sha(sys.argv[3]),'search_params_sha256':sha(sys.argv[4])}
if got!=identities: raise SystemExit(f'OOS engine/model identity drift got={got} want={identities}')
PY_ENGINE

stage derive-candidate-game-subset-before-exact-targets
profile_cli=(); for shard in $(seq 0 15); do profile_cli+=(--profile-shard "$PROFILE/shard-$shard.json"); done
python3 -m "$MODULE" prepare --preregistration "$IN/preregistration.json" --availability "$IN/availability.json" \
  --lattice "$IN/lattice.json" --source-selection "$IN/source-selection.json" --profile-selection "$IN/profile-selection.json" \
  "${profile_cli[@]}" --prepared "$ART/oos-prepared.json" --paths "$W/required-games.txt" >"$W/prepare.log" 2>&1

stage fetch-and-authenticate-only-candidate-games
timeout 3600s python3 jobs/tools/fetch_result_subset.py --prefix "$AVAILABILITY_ROOT" --paths-file "$W/required-games.txt" \
  --out-dir "$GAMES" --report "$ART/verified-candidate-games.json" --expected-state completed >"$W/fetch-games.log" 2>&1
python3 - "$ART/verified-candidate-games.json" "$AVAILABILITY_SOURCE_JOB" "$AVAILABILITY_SOURCE_ATTEMPT" "$AVAILABILITY_SOURCE_CODE" <<'PY_GAMES'
import json,sys
row=json.load(open(sys.argv[1])); got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha')); want=tuple(sys.argv[2:5])
if got!=want or row.get('state')!='verified' or int(row.get('requested_files',0))<=0: raise SystemExit(f'candidate-game receipt drift got={got} want={want}')
PY_GAMES

stage normalize-historical-moves
python3 -m "$MODULE" normalize --prepared "$ART/oos-prepared.json" --lattice "$IN/lattice.json" \
  --profile-selection "$IN/profile-selection.json" "${profile_cli[@]}" \
  --games-dir "$GAMES/artefacts/games-pool1" --games-dir "$GAMES/artefacts/games-pool2" \
  --jass "$J" --catalog "$ART/oos-catalog.json" >"$W/normalize.log" 2>&1

stage exact-label-first-300-valid-pairs-per-pool-in-frozen-orders
CACHE=""; COMPLETE=0
for round in $(seq 0 $((MAX_ROUNDS-1))); do
  R="$TARGETS/round-$round"; mkdir -p "$R/shards"
  args=(--lattice "$IN/lattice.json" --catalog "$ART/oos-catalog.json" --max-states "$TARGET_STATES_PER_ROUND" --plan "$R/plan.json" --batch "$R/batch.json")
  if [ -n "$CACHE" ]; then args+=(--cache "$CACHE"); else args+=(--cache-output "$R/cache-in.json"); CACHE="$R/cache-in.json"; fi
  python3 -m "$MODULE" plan "${args[@]}" >"$W/plan-$round.log" 2>&1
  status=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["status"])' "$R/plan.json")
  if [ "$status" = complete ]; then
    COMPLETE=1; cp "$CACHE" "$W/current-cache.json"; cp "$CACHE" "$ART/oos-target-cache.json"; cp "$R/plan.json" "$ART/oos-selection-plan.json"; break
  fi
  [ "$status" = needs_targets ] || die "unknown target-plan status $status"
  pids=()
  for shard in $(seq 0 15); do
    timeout 43200s python3 jobs/tools/l3_curriculum_search_error_atlas.py atlas --pairs "$R/batch.json" \
      --jass "$J" --champion "$W/curriculum.pjtw" --search-params "$IN/search-params.txt" \
      --judge-depth 12 --shard "$shard" --nshards 16 --out "$R/shards/shard-$shard.json" >"$W/exact-r${round}-s${shard}.log" 2>&1 & pids+=("$!")
  done
  for pid in "${pids[@]}"; do wait "$pid"; done
  shard_cli=(); for shard in $(seq 0 15); do shard_cli+=(--atlas-shard "$R/shards/shard-$shard.json"); done
  python3 -m "$MODULE" ingest --cache "$CACHE" --catalog "$ART/oos-catalog.json" --batch "$R/batch.json" \
    "${shard_cli[@]}" --output "$R/cache-out.json" >"$W/ingest-$round.log" 2>&1
  CACHE="$R/cache-out.json"; cp "$CACHE" "$W/current-cache.json"
done
[ "$COMPLETE" -eq 1 ] || die "300+300 OOS pair selection exceeded $MAX_ROUNDS batches"

stage finalize-repacked-authenticated-oos-atlas
python3 -m "$MODULE" finalize --lattice "$IN/lattice.json" --catalog "$ART/oos-catalog.json" \
  --cache "$ART/oos-target-cache.json" --pairs "$ART/oos-pairs.json" --shards-dir "$FINAL_SHARDS" >"$W/finalize.log" 2>&1
[ "$(find "$FINAL_SHARDS" -name 'shard-*.json' | wc -l)" -eq 16 ] || die "OOS atlas shard count drift"

stage audit-anchored-model-without-refit
fresh_cli=(); for shard in $(seq 0 15); do fresh_cli+=(--fresh-shard "$FINAL_SHARDS/shard-$shard.json"); done
python3 -m "$MODULE" audit --fit-report "$IN/fit-report.json" --fit-model "$IN/fit-model.json" \
  --fresh-pairs "$ART/oos-pairs.json" "${fresh_cli[@]}" --target-cache "$ART/oos-target-cache.json" \
  --champion "$W/curriculum.pjtw" --report "$ART/anchored-local-refit-oos-audit.json" >"$W/audit.log" 2>&1

stage publish-terminal-verdict
python3 - "$ART/anchored-local-refit-oos-audit.json" "$ART/JASS_CONTROL_SUMMARY.json" "$EXPECTED_CODE_SHA" \
  "$AVAILABILITY_SOURCE_JOB" "$AVAILABILITY_SOURCE_ATTEMPT" "$AVAILABILITY_SOURCE_CODE" \
  "$PREREG_SOURCE_JOB" "$PREREG_SOURCE_ATTEMPT" "$PREREG_SOURCE_CODE" \
  "$FIT_SOURCE_JOB" "$FIT_SOURCE_ATTEMPT" "$FIT_SOURCE_CODE" <<'PY_FINAL'
import json,sys
from pathlib import Path
src,out=map(Path,sys.argv[1:3]); row=json.load(open(src)); code=sys.argv[3]
if row.get('verdict') not in {'JASS_CURRICULUM_ERROR_ANCHORED_LOCAL_REFIT_OOS_PASSED','JASS_CURRICULUM_ERROR_ANCHORED_LOCAL_REFIT_OOS_NOT_ESTABLISHED'}: raise SystemExit('OOS verdict drift')
if row.get('pairs')!=600 or row.get('pairs_by_pool')!={'pool1':300,'pool2':300}: raise SystemExit('OOS 300+300 cardinality drift')
if row.get('oos_labels_used_for_fit_or_selection') is not False or row.get('candidate_order_fixed_before_targets') is not True: raise SystemExit('OOS isolation drift')
for key in ('diagnostic_fits','pattern_eval_fits','strength_games','new_selfplay_games','frozen_reads'):
 if int(row.get(key,-1))!=0: raise SystemExit(f'forbidden counter drift {key}')
payload={**row,'schema':'jass.curriculum_error_anchored_local_refit_oos_audit_terminal.v1','code_sha':code,
 'availability_source':{'job':sys.argv[4],'attempt':sys.argv[5],'code_sha':sys.argv[6]},
 'preregistration_source':{'job':sys.argv[7],'attempt':sys.argv[8],'code_sha':sys.argv[9]},
 'fit_source':{'job':sys.argv[10],'attempt':sys.argv[11],'code_sha':sys.argv[12]},
 'automatic_continuation':False,'promotion_authorized':False}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n'); (out.parent/row['verdict']).touch()
for name in ('OOS_LABELS_USED_FOR_FIT_OR_SELECTION__FALSE','CANDIDATE_ORDER_FIXED_BEFORE_TARGETS__TRUE','PAIRS__600__POOL1_300__POOL2_300','FITS__0','STRENGTH_GAMES__0','NEW_SELFPLAY__0','FROZEN_READS__0','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_CONTINUATION__FALSE'): (out.parent/name).touch()
PY_FINAL
VERDICT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
say "$VERDICT pairs=600 pool1=300 pool2=300 fit=0 strength=0 frozen=0 promotion=false"
