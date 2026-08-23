#!/usr/bin/env bash
# Fresh matched root atlas followed by a leakage-safe diagnostic action-ranker fit.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${ACTION_SOURCE_JOB:?}"; : "${ACTION_SOURCE_ATTEMPT:?}"; : "${ACTION_SOURCE_CODE:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
PROFILE="$ART/profile-shards"; ATLAS="$ART/atlas-shards"
mkdir -p "$W" "$IN" "$ART" "$PROFILE" "$ATLAS"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

SOURCE_JOB="$ACTION_SOURCE_JOB"; SOURCE_ATTEMPT="$ACTION_SOURCE_ATTEMPT"; SOURCE_CODE="$ACTION_SOURCE_CODE"
SOURCE_ROOT="r2:jass-data/runs/$SOURCE_JOB/$SOURCE_ATTEMPT"
CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE="18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_ROOT="r2:jass-data/runs/$CURRICULUM_JOB/$CURRICULUM_ATTEMPT"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
NSH=16
MIN_SOURCE_ERRORS=256
PROFILE_PREFLIGHT_ROWS=1
ATLAS_PREFLIGHT_PAIRS=1
MAX_PROFILE_MINUTES=240
MAX_ATLAS_MINUTES=480
BOOTSTRAP=10000
CACHE_MB=128
BUDGET_ROWS_PER_SPLIT="${BUDGET_ROWS_PER_SPLIT:-1024}"
COVERAGE_ONLY="${COVERAGE_ONLY:-0}"
EXPECTED_SOURCE_POOL_SEED_1="${EXPECTED_SOURCE_POOL_SEED_1:-2026082231}"
EXPECTED_SOURCE_POOL_SEED_2="${EXPECTED_SOURCE_POOL_SEED_2:-2026082232}"
EXPECTED_SOURCE_SPLIT_SEED="${EXPECTED_SOURCE_SPLIT_SEED:-2026082233}"

MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        printf 'profile_shards=%s/16\n' "$(find "$PROFILE" -name 'shard-*.json' 2>/dev/null | wc -l)"
        printf 'atlas_shards=%s/16\n' "$(find "$ATLAS" -name 'shard-*.json' 2>/dev/null | wc -l)"
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
  rm -rf "$W/build" "$IN" "$W/profile-preflight" "$W/atlas-preflight" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
if [ "$COVERAGE_ONLY" = 1 ]; then
  [[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-paired-coverage-screen-v1$ ]] || die "invalid coverage job nomenclature"
else
  [[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-action-ranker-screen-v1$ ]] || die "invalid ranker job nomenclature"
fi
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "${NO_SELFPLAY:-0}" = 1 ] || die "self-play guard missing"
[ "${NO_PATTERNEVAL_FIT:-0}" = 1 ] || die "PatternEval-fit guard missing"
[ "${NO_STRENGTH_GAMES:-0}" = 1 ] || die "strength-game guard missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] || die "frozen-read guard missing"
[ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] || die "promotion guard missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guard missing"
say "experiment=CURRICULUM_ERROR_ACTION_RANKER source=$SOURCE_JOB/$SOURCE_ATTEMPT"
say "new_selfplay=0 PatternEval_fit=0 force=0 frozen=0 promotion=false"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_curriculum_search_error_atlas.py \
  jobs/tools/l3_curriculum_error_action_ranker.py \
  jobs/tools/l3_curriculum_error_paired_coverage_screen.py
python3 -m unittest jobs.tests.test_l3_curriculum_search_error_atlas \
  jobs.tests.test_l3_curriculum_error_action_ranker \
  jobs.tests.test_l3_curriculum_error_paired_coverage_screen \
  jobs.tests.test_l3_curriculum_error_learning >"$W/tests.log" 2>&1

stage fetch-authenticate-fresh-action-source-and-champion
SOURCE_ARGS=()
for shard in $(seq 0 $((NSH-1))); do
  SOURCE_ARGS+=(--file "artefacts/autopsy-shards/shard-$shard.json=source-shard-$shard.json")
done
if [ "$COVERAGE_ONLY" = 1 ]; then
  SOURCE_ARGS+=(
    --file "artefacts/verified-exclude-pool-curriculum-error-1492-pool1.json=source-exclude-1492-pool1.json"
    --file "artefacts/verified-exclude-pool-curriculum-error-1492-pool2.json=source-exclude-1492-pool2.json"
  )
fi
timeout 3600s python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_ROOT" \
  --file artefacts/error-selection.json=error-selection.json \
  --file artefacts/search-params.txt=search-params.txt \
  --file artefacts/JASS_CONTROL_SUMMARY.json=source-summary.json \
  "${SOURCE_ARGS[@]}" --out-dir "$IN" --report "$ART/verified-action-source.json" \
  --expected-state completed >"$W/fetch-source.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=curriculum-summary.json \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" --expected-state completed \
  >"$W/fetch-curriculum.log" 2>&1
gunzip -t "$IN/curriculum.pjtw.gz"; gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
python3 - "$IN" "$ART" "$SOURCE_JOB" "$SOURCE_ATTEMPT" "$SOURCE_CODE" \
  "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" "$CURRICULUM_CODE" "$CURRICULUM_SHA" \
  "$EXPECTED_SOURCE_POOL_SEED_1" "$EXPECTED_SOURCE_POOL_SEED_2" \
  "$EXPECTED_SOURCE_SPLIT_SEED" "$COVERAGE_ONLY" <<'PY_AUTH'
import hashlib,json,sys
from pathlib import Path
src,art=map(Path,sys.argv[1:3]); source=tuple(sys.argv[3:6]); curriculum=tuple(sys.argv[6:9]); model_sha=sys.argv[9]
pool_seeds=[int(sys.argv[10]),int(sys.argv[11])]; split_seed=int(sys.argv[12])
coverage_only=bool(int(sys.argv[13]))
for name,want in (("verified-action-source.json",source),("verified-curriculum.json",curriculum)):
 receipt=json.load(open(art/name)); got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'))
 if got!=want or receipt.get('result_state')!='completed' or receipt.get('exit_code')!=0:
  raise SystemExit(f'{name} identity/state drift: {got}')
summary=json.load(open(src/'source-summary.json')); selection=json.load(open(src/'error-selection.json'))
if summary.get('verdict')!='JASS_CURRICULUM_ERROR_ACTION_SOURCE_READY': raise SystemExit('source verdict drift')
campaign=summary.get('campaign',{})
if campaign.get('pool_seeds')!=pool_seeds or campaign.get('split_seed')!=split_seed:
 raise SystemExit('fresh action source seeds drift')
if not campaign.get('disjoint_from_1468_and_prior_force_pools'): raise SystemExit('source disjointness drift')
if summary.get('pattern_bucket_aggregate_reads')!=0 or summary.get('pattern_eval_fits')!=0 or summary.get('strength_games')!=0:
 raise SystemExit('source forbidden-action drift')
if coverage_only:
 expected_1492=('cpx62-1492-l3-curriculum-error-autopsy-v1','20260822T212256Z-454b3862','454b386229810dc5897d1eb955f7c379d536e920')
 for name in ('source-exclude-1492-pool1.json','source-exclude-1492-pool2.json'):
  prior=json.load(open(src/name)); got=(prior.get('job_id'),prior.get('attempt_id'),prior.get('code_sha'))
  if got!=expected_1492 or prior.get('result_state')!='completed' or prior.get('exit_code')!=0:
   raise SystemExit(f'1492 exclusion receipt drift: {name} {got}')
if selection.get('schema')!='jass.l3_curriculum_error_selection.v1' or selection.get('decisions')!=summary.get('decisions'):
 raise SystemExit('source selection drift')
if hashlib.sha256((src/'error-selection.json').read_bytes()).hexdigest()!=summary.get('selection_sha256'):
 raise SystemExit('source selection hash drift')
(art/'fresh-action-source-certificate.json').write_text(json.dumps({
 'schema':'jass.curriculum_error_action_source_certificate.v1','job_id':source[0],'attempt_id':source[1],
 'code_sha':source[2],'decisions':selection['decisions'],'champion_sha256':model_sha,
 'pool_seeds':pool_seeds,'split_seed':split_seed,'disjoint':True,
 'pattern_bucket_aggregate_reads':0,'production_fits':0,'promotion_authorized':False},indent=2,sort_keys=True)+'\n')
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

stage prepare-fresh-error-and-control-risk-set
source_args=(); for shard in $(seq 0 $((NSH-1))); do source_args+=(--source-shard "$IN/source-shard-$shard.json"); done
python3 jobs/tools/l3_curriculum_search_error_atlas.py prepare \
  --selection "$IN/error-selection.json" "${source_args[@]}" \
  --min-regret-cp 50 --max-control-regret-cp 10 --candidates-per-error 16 \
  --budget-rows-per-split "$BUDGET_ROWS_PER_SPLIT" --out "$ART/profile-selection.json" >"$W/prepare.log" 2>&1
SOURCE_ERRORS=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["error_openings"])' "$ART/profile-selection.json")
if [ "$SOURCE_ERRORS" -lt "$MIN_SOURCE_ERRORS" ]; then
  python3 - "$ART" "$SOURCE_ERRORS" "$EXPECTED_CODE_SHA" "$SOURCE_JOB" "$SOURCE_ATTEMPT" <<'PY_SUPPORT_FAIL'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); errors=int(sys.argv[2])
payload={'schema':'jass.curriculum_error_action_ranker_terminal.v1','verdict':'JASS_CURRICULUM_ERROR_ACTION_SOURCE_UNDERPOWERED',
 'source_error_openings':errors,'minimum_source_error_openings':256,'code_sha':sys.argv[3],
 'source_job':sys.argv[4],'source_attempt':sys.argv[5],'pattern_eval_fits':0,'production_model_fits':0,
 'strength_games':0,'new_selfplay_games':0,'frozen_reads':0,'promotion_authorized':False,'next_stage':None}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_SUPPORT_FAIL
  : >"$ART/JASS_CURRICULUM_ERROR_ACTION_SOURCE_UNDERPOWERED"
  stage completed-scientific-source-underpowered
  say "JASS_CURRICULUM_ERROR_ACTION_SOURCE_UNDERPOWERED errors=$SOURCE_ERRORS minimum=$MIN_SOURCE_ERRORS"
  exit 0
fi

stage profile-cost-preflight
mkdir -p "$W/profile-preflight"; T0=$(date +%s); pids=()
for shard in $(seq 0 $((NSH-1))); do
  python3 jobs/tools/l3_curriculum_search_error_atlas.py profile \
    --selection "$ART/profile-selection.json" --jass "$J" --champion "$W/curriculum.pjtw" \
    --search-params "$ART/search-params.txt" --max-rows "$PROFILE_PREFLIGHT_ROWS" \
    --shard "$shard" --nshards "$NSH" --out "$W/profile-preflight/shard-$shard.json" \
    >"$W/profile-preflight-$shard.log" 2>&1 & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done; T1=$(date +%s)
python3 - "$ART/profile-selection.json" "$W/profile-preflight" "$ART/profile-cost-preflight.json" "$((T1-T0))" "$MAX_PROFILE_MINUTES" <<'PY_PROFILE_COST'
import json,sys
from pathlib import Path
selection=json.load(open(sys.argv[1])); root=Path(sys.argv[2]); elapsed=max(int(sys.argv[4]),1); maximum=int(sys.argv[5])
rows=sum(len(json.load(open(p))['rows']) for p in root.glob('shard-*.json')); total=len(selection['rows']); projected=elapsed*total/max(rows,1)/60
payload={'schema':'jass.curriculum_action_profile_cost.v1','sample_rows':rows,'total_rows':total,'elapsed_seconds':elapsed,'projected_minutes':projected,'maximum_minutes':maximum,'passed':rows==16 and projected<=maximum}
Path(sys.argv[3]).write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
if not payload['passed']: raise SystemExit(f'profile cost preflight failed: {payload}')
PY_PROFILE_COST

stage profile-all-fresh-error-and-control-risk-decisions
pids=()
for shard in $(seq 0 $((NSH-1))); do
  python3 jobs/tools/l3_curriculum_search_error_atlas.py profile \
    --selection "$ART/profile-selection.json" --jass "$J" --champion "$W/curriculum.pjtw" \
    --search-params "$ART/search-params.txt" --shard "$shard" --nshards "$NSH" \
    --out "$PROFILE/shard-$shard.json" >"$W/profile-$shard.log" 2>&1 & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done
[ "$(find "$PROFILE" -name 'shard-*.json' | wc -l)" -eq "$NSH" ] || die "profile shard count drift"

stage opening-disjoint-fresh-matching
profile_args=(); for shard in $(seq 0 $((NSH-1))); do profile_args+=(--profile-shard "$PROFILE/shard-$shard.json"); done
python3 jobs/tools/l3_curriculum_search_error_atlas.py match --selection "$ART/profile-selection.json" \
  "${profile_args[@]}" --out "$ART/matched-pairs.json" >"$W/match.log" 2>&1
MATCHED=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["matched_pairs"])' "$ART/matched-pairs.json")
MATCH_PASS=$(python3 -c 'import json,sys;print(int(json.load(open(sys.argv[1]))["matching_passed"]))' "$ART/matched-pairs.json")
if [ "$MATCH_PASS" -ne 1 ]; then
  python3 - "$ART" "$SOURCE_ERRORS" "$MATCHED" "$EXPECTED_CODE_SHA" <<'PY_MATCH_FAIL'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); errors,matched=map(int,sys.argv[2:4]); pairs=json.load(open(art/'matched-pairs.json'))
payload={'schema':'jass.curriculum_error_action_ranker_terminal.v1','verdict':'JASS_CURRICULUM_ERROR_ACTION_MATCHING_NOT_ESTABLISHED','code_sha':sys.argv[4],
 'source_error_openings':errors,'matched_pairs':matched,'matched_fraction':pairs['matched_fraction'],'matching_gate':pairs['matching_gate'],
 'pattern_eval_fits':0,'production_model_fits':0,'strength_games':0,'new_selfplay_games':0,'frozen_reads':0,'promotion_authorized':False,'next_stage':None}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_MATCH_FAIL
  : >"$ART/JASS_CURRICULUM_ERROR_ACTION_MATCHING_NOT_ESTABLISHED"
  stage completed-scientific-matching-fail
  say "JASS_CURRICULUM_ERROR_ACTION_MATCHING_NOT_ESTABLISHED matched=$MATCHED/$SOURCE_ERRORS"
  exit 0
fi

if [ "$COVERAGE_ONLY" = 1 ]; then
  stage paired-image-feature-only-relative-coverage-screen
  python3 jobs/tools/l3_curriculum_error_paired_coverage_screen.py \
    --pairs "$ART/matched-pairs.json" --report "$ART/paired-coverage-screen.json" \
    >"$W/coverage.log" 2>&1
  python3 - "$ART" "$EXPECTED_CODE_SHA" "$SOURCE_JOB" "$SOURCE_ATTEMPT" \
    "$SOURCE_CODE" "$CURRICULUM_SHA" <<'PY_COVERAGE'
import json,re,sys
from pathlib import Path
art=Path(sys.argv[1]); code,job,attempt,source_code,champion_sha=sys.argv[2:]
report=json.load(open(art/'paired-coverage-screen.json'))
if report.get('verdict') not in {
 'JASS_CURRICULUM_ERROR_PAIRED_COVERAGE_SCREEN_READY',
 'JASS_CURRICULUM_ERROR_PAIRED_COVERAGE_SCREEN_NOT_ESTABLISHED'}:
 raise SystemExit('coverage verdict drift')
for key in ('exact_action_value_reads','diagnostic_fits','pattern_eval_fits','strength_games',
            'new_selfplay_games','frozen_reads','outer_confirm_action_value_reads',
            'outer_confirm_profile_rows_examined'):
 if report.get(key)!=0: raise SystemExit(f'coverage forbidden counter drift: {key}')
if report.get('residual_fit_authorized') is not False or report.get('promotion_authorized') is not False:
 raise SystemExit('coverage screen exposed forbidden authorization')
payload={**report,'code_sha':code,'source_job':job,'source_attempt':attempt,
 'source_code_sha':source_code,'champion_sha256':champion_sha,
 'weights_bit_identical':True,'automatic_continuation':False}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/report['verdict']).touch()
clean=lambda value: re.sub(r'[^A-Za-z0-9.+-]+','_',str(value)).strip('_')
gate=report['fixed_gate']; audit=report['feature_audit_metrics']['roles']
(art/f"FIXED_GATE__Q20_{clean(gate['lower_margin_cp'])}__Q60_{clean(gate['upper_margin_cp'])}").touch()
for role in ('error','control'):
 row=audit[role]
 (art/f"AUDIT_{role.upper()}__N_{row['profiles']}__ELIGIBLE_{row['eligible']}__RATE_{clean(row['eligible_rate'])}").touch()
for name,value in report['gates'].items():
 (art/f"GATE__{name.upper()}__{str(value).upper()}").touch()
for marker in ('EXACT_ACTION_VALUE_READS__0','OUTER_CONFIRM_ACTION_VALUE_READS__0',
 'OUTER_CONFIRM_PROFILE_ROWS_EXAMINED__0','DIAGNOSTIC_FITS__0','PATTERNEVAL_FITS__0',
 'STRENGTH_GAMES__0','NEW_SELFPLAY__0','FROZEN_READS__0',
 'RESIDUAL_FIT_AUTHORIZED__FALSE','PROMOTION_AUTHORIZED__FALSE'):
 (art/marker).touch()
PY_COVERAGE
  VERDICT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
  stage completed-feature-only-coverage-screen
  say "$VERDICT action_targets=0 fits=0 confirm_profiles=0 strength=0"
  exit 0
fi

stage atlas-cost-preflight
mkdir -p "$W/atlas-preflight"; T0=$(date +%s); pids=()
for shard in $(seq 0 $((NSH-1))); do
  python3 jobs/tools/l3_curriculum_search_error_atlas.py atlas \
    --pairs "$ART/matched-pairs.json" --jass "$J" --champion "$W/curriculum.pjtw" \
    --search-params "$ART/search-params.txt" --judge-depth 12 --max-pairs "$ATLAS_PREFLIGHT_PAIRS" \
    --shard "$shard" --nshards "$NSH" --out "$W/atlas-preflight/shard-$shard.json" \
    >"$W/atlas-preflight-$shard.log" 2>&1 & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done; T1=$(date +%s)
python3 - "$ART/matched-pairs.json" "$W/atlas-preflight" "$ART/atlas-cost-preflight.json" "$((T1-T0))" "$MAX_ATLAS_MINUTES" <<'PY_ATLAS_COST'
import json,sys
from pathlib import Path
pairs=json.load(open(sys.argv[1])); root=Path(sys.argv[2]); elapsed=max(int(sys.argv[4]),1); maximum=int(sys.argv[5])
rows=sum(len(json.load(open(p))['rows']) for p in root.glob('shard-*.json')); total=pairs['matched_pairs']; projected=elapsed*total/max(rows,1)/60
payload={'schema':'jass.curriculum_action_atlas_cost.v1','sample_pairs':rows,'total_pairs':total,'elapsed_seconds':elapsed,'projected_minutes':projected,'maximum_minutes':maximum,'passed':rows==16 and projected<=maximum}
Path(sys.argv[3]).write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
if not payload['passed']: raise SystemExit(f'atlas cost preflight failed: {payload}')
PY_ATLAS_COST

stage exactly-symmetrised-fresh-action-atlas
pids=()
for shard in $(seq 0 $((NSH-1))); do
  python3 jobs/tools/l3_curriculum_search_error_atlas.py atlas \
    --pairs "$ART/matched-pairs.json" --jass "$J" --champion "$W/curriculum.pjtw" \
    --search-params "$ART/search-params.txt" --judge-depth 12 --shard "$shard" --nshards "$NSH" \
    --out "$ATLAS/shard-$shard.json" >"$W/atlas-$shard.log" 2>&1 & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done
[ "$(find "$ATLAS" -name 'shard-*.json' | wc -l)" -eq "$NSH" ] || die "atlas shard count drift"

stage pairwise-ridge-inner-oof-then-outer-confirm-if-authorized
atlas_args=(); for shard in $(seq 0 $((NSH-1))); do atlas_args+=(--atlas-shard "$ATLAS/shard-$shard.json"); done
python3 jobs/tools/l3_curriculum_error_action_ranker.py --pairs "$ART/matched-pairs.json" \
  "${atlas_args[@]}" --bootstrap-samples "$BOOTSTRAP" \
  --report "$ART/action-ranker-screen.json" --model "$ART/action-ranker-model.json" \
  >"$W/ranker.log" 2>&1
python3 - "$ART" "$EXPECTED_CODE_SHA" "$SOURCE_JOB" "$SOURCE_ATTEMPT" "$SOURCE_CODE" "$CURRICULUM_SHA" <<'PY_FINAL'
import json,os,sys
from pathlib import Path
art=Path(sys.argv[1]); code,job,attempt,source_code,model_sha=sys.argv[2:]
report=json.load(open(art/'action-ranker-screen.json')); model=json.load(open(art/'action-ranker-model.json'))
if report.get('champion_sha256')!=model_sha or model.get('champion_sha256')!=model_sha: raise SystemExit('champion identity drift')
if report.get('verdict') not in {'JASS_CURRICULUM_ERROR_ACTION_RANKER_OOF_READY','JASS_CURRICULUM_ERROR_ACTION_RANKER_NOT_ESTABLISHED'}: raise SystemExit('verdict drift')
for key in ('pattern_eval_fits','production_model_fits','strength_games','new_selfplay_games','frozen_reads'):
 if report.get(key)!=0: raise SystemExit(f'forbidden counter drift: {key}')
payload={**report,'schema':'jass.curriculum_error_action_ranker_terminal.v1','code_sha':code,
 'source_job':job,'source_attempt':attempt,'source_code_sha':source_code,'weights_bit_identical':True,
 'automatic_continuation':False,'promotion_authorized':False}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
support=report['support']; (art/f"SUPPORT__DISCOVERY_{support['discovery']}__FIT_{support['inner_fit']}__VALIDATION_{support['inner_validation']}__CONFIRM_{support['outer_confirm']}").touch()
for row in report.get('candidates',[]):
 mean=row['oof']['paired_error_minus_control']['mean']; changed=row['oof']['error_changed_pairs']
 (art/f"CANDIDATE__A_{row['alpha']}__T_{int(row['advantage_threshold_cp'])}__M_{int(row['margin_band_cp'])}__PASS_{str(row['oof_passed']).upper()}__PAIRED_{mean}__CHANGED_{changed}").touch()
selected=report.get('selected_candidate')
if selected: (art/f"SELECTED__A_{selected['alpha']}__T_{int(selected['advantage_threshold_cp'])}__M_{int(selected['margin_band_cp'])}").touch()
outer=report.get('outer_confirm')
if outer: (art/f"OUTER__ERR_{outer['error_improvement']['mean']}__PAIRED_{outer['paired_error_minus_control']['mean']}__CONTROL_{outer['control_improvement']['mean']}").touch()
PY_FINAL
VERDICT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
OUTER_READS=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["outer_confirm_pairs_read"])' "$ART/JASS_CONTROL_SUMMARY.json")
: >"$ART/$VERDICT"; : >"$ART/OUTER_CONFIRM_PAIRS_READ__$OUTER_READS"
: >"$ART/PATTERNEVAL_FITS__0"; : >"$ART/PRODUCTION_MODEL_FITS__0"
: >"$ART/STRENGTH_GAMES__0"; : >"$ART/NEW_SELFPLAY__0"; : >"$ART/FROZEN_READS__0"
: >"$ART/PRODUCTION_RULE_AUTHORIZED__FALSE"; : >"$ART/PROMOTION_AUTHORIZED__FALSE"
stage completed
say "$VERDICT source_errors=$SOURCE_ERRORS matched=$MATCHED outer_confirm_reads=$OUTER_READS production=false"
