#!/usr/bin/env bash
# Read-only, exactly-symmetrised search-error atlas for CURRICULUM.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
PROFILE="$ART/profile-shards"; ATLAS="$ART/atlas-shards"
mkdir -p "$W" "$IN" "$ART" "$PROFILE" "$ATLAS"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

SELECTION_JOB="cpx62-1468-l3-curriculum-error-autopsy-v1"
SELECTION_ATTEMPT="20260822T134756Z-746421c7"
SELECTION_CODE="746421c7b08fb907e5e116a6ab8f788425dc51ec"
SELECTION_ROOT="r2:jass-data/runs/$SELECTION_JOB/$SELECTION_ATTEMPT"
SOURCE_JOB="cpx62-1474-l3-curriculum-error-autopsy-resume-v1"
SOURCE_ATTEMPT="20260822T153126Z-0be76565"
SOURCE_CODE="0be76565de1882c4d410995603217aa64ea09d70"
SOURCE_ROOT="r2:jass-data/runs/$SOURCE_JOB/$SOURCE_ATTEMPT"
CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE="18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_ROOT="r2:jass-data/runs/$CURRICULUM_JOB/$CURRICULUM_ATTEMPT"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
NSH=16
SOURCE_DECISIONS=79110
SOURCE_ERRORS=388
PROFILE_PREFLIGHT_ROWS=1
ATLAS_PREFLIGHT_PAIRS=1
MAX_PROFILE_MINUTES=240
MAX_ATLAS_MINUTES=480
BOOTSTRAP=100000
CACHE_MB=128

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
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-search-error-atlas-v1$ ]] || die "invalid job nomenclature"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "${NO_SELFPLAY:-0}" = 1 ] || die "self-play guard missing"
[ "${NO_FIT:-0}" = 1 ] || die "fit guard missing"
[ "${NO_STRENGTH_GAMES:-0}" = 1 ] || die "strength-game guard missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] || die "frozen-read guard missing"
[ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] || die "promotion guard missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guard missing"
say "experiment=CURRICULUM_SEARCH_ERROR_ATLAS source=$SOURCE_JOB/$SOURCE_ATTEMPT"
say "weights=bit-identical decisions=$SOURCE_DECISIONS source_errors=$SOURCE_ERRORS selfplay=0 fit=0 games=0"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_curriculum_search_error_atlas.py
python3 -m unittest jobs.tests.test_l3_curriculum_search_error_atlas \
  jobs.tests.test_l3_curriculum_error_learning >"$W/tests.log" 2>&1

stage fetch-authenticate-source-shards-selection-and-champion
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$SELECTION_ROOT" \
  --file artefacts/error-selection.json=error-selection.json \
  --file artefacts/search-params.txt=search-params.txt \
  --out-dir "$IN" --report "$ART/verified-selection.json" --expected-state failed \
  >"$W/fetch-selection.log" 2>&1
SOURCE_ARGS=()
for shard in $(seq 0 $((NSH-1))); do
  SOURCE_ARGS+=(--file "artefacts/autopsy-shards/shard-$shard.json=source-shard-$shard.json")
done
timeout 3600s python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_ROOT" \
  "${SOURCE_ARGS[@]}" \
  --file artefacts/error-autopsy.json=source-error-autopsy.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=source-summary.json \
  --out-dir "$IN" --report "$ART/verified-1474.json" --expected-state completed \
  >"$W/fetch-1474.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=curriculum-summary.json \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" --expected-state completed \
  >"$W/fetch-curriculum.log" 2>&1
gunzip -t "$IN/curriculum.pjtw.gz"
gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
python3 - "$IN" "$ART" "$SOURCE_DECISIONS" "$SOURCE_ERRORS" "$CURRICULUM_SHA" \
  "$SELECTION_JOB" "$SELECTION_ATTEMPT" "$SELECTION_CODE" \
  "$SOURCE_JOB" "$SOURCE_ATTEMPT" "$SOURCE_CODE" \
  "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" "$CURRICULUM_CODE" <<'PY_AUTH'
import hashlib,json,sys
from pathlib import Path
src,art=map(Path,sys.argv[1:3]); decisions,errors=map(int,sys.argv[3:5]); model_sha=sys.argv[5]
expected=[tuple(sys.argv[6:9]),tuple(sys.argv[9:12]),tuple(sys.argv[12:15])]
for name,want in zip(('verified-selection.json','verified-1474.json','verified-curriculum.json'),expected):
 receipt=json.load(open(art/name)); got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'))
 if got!=want: raise SystemExit(f'{name} identity drift: {got!r} != {want!r}')
 if receipt.get('result_state')!=('failed' if name=='verified-selection.json' else 'completed'):
  raise SystemExit(f'{name} state drift')
 if name!='verified-selection.json' and receipt.get('exit_code')!=0:
  raise SystemExit(f'{name} exit-code drift')
selection=json.load(open(src/'error-selection.json')); report=json.load(open(src/'source-error-autopsy.json'))
if selection.get('schema')!='jass.l3_curriculum_error_selection.v1' or selection.get('decisions')!=decisions:
 raise SystemExit('sealed selection identity drift')
if report.get('verdict')!='JASS_CURRICULUM_ERROR_REGION_NOT_ESTABLISHED': raise SystemExit('1474 verdict drift')
if report.get('decisions')!=decisions or report.get('loss_error_openings')!=errors: raise SystemExit('1474 counts drift')
if report.get('matched_control_openings')!=10 or abs(report.get('matched_fraction',0)-0.02577319587628866)>1e-12:
 raise SystemExit('1474 matching metrics drift')
if report.get('confirmed_buckets')!=0 or report.get('perspective_guard',{}).get('max_abs_exact_symmetry_delta_cp')!=8:
 raise SystemExit('1474 closure mechanism drift')
# The raw model lives in the job work directory and is authenticated below by the shell.
(art/'source-certificate.json').write_text(json.dumps({
 'schema':'jass.curriculum_search_error_source.v1','selection_decisions':decisions,
 'source_error_openings':errors,'source_verdict':report['verdict'],
 'selection_sha256':hashlib.sha256((src/'error-selection.json').read_bytes()).hexdigest(),
 'source_report_sha256':hashlib.sha256((src/'source-error-autopsy.json').read_bytes()).hexdigest(),
 'expected_champion_sha256':model_sha,'weights_may_change':False,
 'new_selfplay_games':0,'fits':0,'strength_games':0,'frozen_reads':0,
 'promotion_authorized':False},indent=2,sort_keys=True)+'\n')
PY_AUTH
[ "$(sha256sum "$W/curriculum.pjtw" | awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM raw hash drift"
[ "$(tr ',' '\n' <"$IN/search-params.txt" | wc -l)" -eq 63 ] || die "Q00 key count drift"
cp "$IN/search-params.txt" "$ART/search-params.txt"

stage build-current-exact-fold-tempo-engine-with-readonly-root-cost-trace
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

stage prepare-error-and-decision-control-risk-set
source_args=(); for shard in $(seq 0 $((NSH-1))); do source_args+=(--source-shard "$IN/source-shard-$shard.json"); done
python3 jobs/tools/l3_curriculum_search_error_atlas.py prepare \
  --selection "$IN/error-selection.json" "${source_args[@]}" \
  --min-regret-cp 50 --max-control-regret-cp 10 --candidates-per-error 16 \
  --budget-rows-per-split 1024 \
  --out "$ART/profile-selection.json" >"$W/prepare.log" 2>&1
python3 - "$ART/profile-selection.json" "$SOURCE_ERRORS" <<'PY_PREP'
import json,sys
p=json.load(open(sys.argv[1])); expected=int(sys.argv[2])
if p.get('error_openings')!=expected: raise SystemExit('source error count drift')
if p.get('control_candidate_decisions',0)<expected: raise SystemExit('insufficient broad control risk set')
if p.get('budget_calibration_decisions')!=2048: raise SystemExit('budget calibration sample drift')
PY_PREP

stage profile-cost-preflight
mkdir -p "$W/profile-preflight"
T0=$(date +%s); pids=()
for shard in $(seq 0 $((NSH-1))); do
  python3 jobs/tools/l3_curriculum_search_error_atlas.py profile \
    --selection "$ART/profile-selection.json" --jass "$J" --champion "$W/curriculum.pjtw" \
    --search-params "$ART/search-params.txt" --max-rows "$PROFILE_PREFLIGHT_ROWS" \
    --shard "$shard" --nshards "$NSH" --out "$W/profile-preflight/shard-$shard.json" \
    >"$W/profile-preflight-$shard.log" 2>&1 & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done
T1=$(date +%s)
python3 - "$ART/profile-selection.json" "$W/profile-preflight" "$ART/profile-cost-preflight.json" "$((T1-T0))" "$MAX_PROFILE_MINUTES" <<'PY_COST'
import json,sys
from pathlib import Path
selection=json.load(open(sys.argv[1])); root=Path(sys.argv[2]); elapsed=max(int(sys.argv[4]),1); maximum=int(sys.argv[5])
rows=sum(len(json.load(open(p))['rows']) for p in root.glob('shard-*.json'))
total=len(selection['rows']); projected=elapsed*total/max(rows,1)/60
payload={'schema':'jass.curriculum_search_profile_cost.v1','sample_rows':rows,'total_rows':total,
 'elapsed_seconds':elapsed,'projected_minutes':projected,'maximum_minutes':maximum,'passed':rows==16 and projected<=maximum}
Path(sys.argv[3]).write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
if not payload['passed']: raise SystemExit(f'profile cost preflight failed: {payload}')
PY_COST

stage profile-all-error-and-control-risk-decisions
pids=()
for shard in $(seq 0 $((NSH-1))); do
  python3 jobs/tools/l3_curriculum_search_error_atlas.py profile \
    --selection "$ART/profile-selection.json" --jass "$J" --champion "$W/curriculum.pjtw" \
    --search-params "$ART/search-params.txt" --shard "$shard" --nshards "$NSH" \
    --out "$PROFILE/shard-$shard.json" >"$W/profile-$shard.log" 2>&1 & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done
[ "$(find "$PROFILE" -name 'shard-*.json' | wc -l)" -eq "$NSH" ] || die "profile shard count drift"

stage opening-disjoint-fine-matching
profile_args=(); for shard in $(seq 0 $((NSH-1))); do profile_args+=(--profile-shard "$PROFILE/shard-$shard.json"); done
python3 jobs/tools/l3_curriculum_search_error_atlas.py match \
  --selection "$ART/profile-selection.json" "${profile_args[@]}" \
  --out "$ART/matched-pairs.json" >"$W/match.log" 2>&1
MATCHED=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["matched_pairs"])' "$ART/matched-pairs.json")
MATCH_PASS=$(python3 -c 'import json,sys;print(int(json.load(open(sys.argv[1]))["matching_passed"]))' "$ART/matched-pairs.json")
if [ "$MATCH_PASS" -ne 1 ]; then
  python3 - "$ART" "$EXPECTED_CODE_SHA" <<'PY_MATCH_FAIL'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); pairs=json.load(open(art/'matched-pairs.json'))
payload={'schema':'jass.curriculum_search_error_terminal.v1','verdict':'JASS_CURRICULUM_SEARCH_ERROR_MATCHING_NOT_ESTABLISHED',
 'code_sha':sys.argv[2],'source_decisions':79110,'source_error_openings':388,
 'matched_pairs':pairs['matched_pairs'],'matched_fraction':pairs['matched_fraction'],'matching_gate':pairs['matching_gate'],
 'weights_bit_identical':True,'new_selfplay_games':0,'fits':0,'strength_games':0,'frozen_reads':0,
 'promotion_authorized':False,'automatic_continuation':False,'next_stage':None}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_MATCH_FAIL
  : >"$ART/VERDICT__JASS_CURRICULUM_SEARCH_ERROR_MATCHING_NOT_ESTABLISHED"
  stage completed-scientific-matching-fail
  say "JASS_CURRICULUM_SEARCH_ERROR_MATCHING_NOT_ESTABLISHED matched=$MATCHED/$SOURCE_ERRORS"
  exit 0
fi

stage atlas-cost-preflight
mkdir -p "$W/atlas-preflight"
T0=$(date +%s); pids=()
for shard in $(seq 0 $((NSH-1))); do
  python3 jobs/tools/l3_curriculum_search_error_atlas.py atlas \
    --pairs "$ART/matched-pairs.json" --jass "$J" --champion "$W/curriculum.pjtw" \
    --search-params "$ART/search-params.txt" --judge-depth 12 --max-pairs "$ATLAS_PREFLIGHT_PAIRS" \
    --shard "$shard" --nshards "$NSH" --out "$W/atlas-preflight/shard-$shard.json" \
    >"$W/atlas-preflight-$shard.log" 2>&1 & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done
T1=$(date +%s)
python3 - "$ART/matched-pairs.json" "$W/atlas-preflight" "$ART/atlas-cost-preflight.json" "$((T1-T0))" "$MAX_ATLAS_MINUTES" <<'PY_COST'
import json,sys
from pathlib import Path
pairs=json.load(open(sys.argv[1])); root=Path(sys.argv[2]); elapsed=max(int(sys.argv[4]),1); maximum=int(sys.argv[5])
rows=sum(len(json.load(open(p))['rows']) for p in root.glob('shard-*.json'))
total=pairs['matched_pairs']; projected=elapsed*total/max(rows,1)/60
payload={'schema':'jass.curriculum_search_atlas_cost.v1','sample_pairs':rows,'total_pairs':total,
 'elapsed_seconds':elapsed,'projected_minutes':projected,'maximum_minutes':maximum,'passed':rows==16 and projected<=maximum}
Path(sys.argv[3]).write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
if not payload['passed']: raise SystemExit(f'atlas cost preflight failed: {payload}')
PY_COST

stage exactly-symmetrised-search-error-atlas
pids=()
for shard in $(seq 0 $((NSH-1))); do
  python3 jobs/tools/l3_curriculum_search_error_atlas.py atlas \
    --pairs "$ART/matched-pairs.json" --jass "$J" --champion "$W/curriculum.pjtw" \
    --search-params "$ART/search-params.txt" --judge-depth 12 \
    --shard "$shard" --nshards "$NSH" --out "$ATLAS/shard-$shard.json" \
    >"$W/atlas-$shard.log" 2>&1 & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done
[ "$(find "$ATLAS" -name 'shard-*.json' | wc -l)" -eq "$NSH" ] || die "atlas shard count drift"

stage discovery-select-confirm-once-budget-neutral-controller
atlas_args=(); for shard in $(seq 0 $((NSH-1))); do atlas_args+=(--atlas-shard "$ATLAS/shard-$shard.json"); done
python3 jobs/tools/l3_curriculum_search_error_atlas.py aggregate \
  --pairs "$ART/matched-pairs.json" "${atlas_args[@]}" \
  --bootstrap-samples "$BOOTSTRAP" --bootstrap-seed 2026082221 \
  --out "$ART/search-error-atlas.json" >"$W/aggregate.log" 2>&1
python3 - "$ART" "$EXPECTED_CODE_SHA" "$SOURCE_JOB" "$SOURCE_ATTEMPT" "$CURRICULUM_SHA" <<'PY_FINAL'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); code,job,attempt,model=sys.argv[2:]
report=json.load(open(art/'search-error-atlas.json'))
if report.get('champion_sha256')!=model or report.get('weights_bit_identical') is not True: raise SystemExit('champion identity drift')
if report.get('verdict') not in {'JASS_CURRICULUM_SEARCH_ERROR_CONTROLLER_SCREEN_PASSED','JASS_CURRICULUM_SEARCH_ERROR_CONTROLLER_NOT_ESTABLISHED'}:
 raise SystemExit('terminal verdict drift')
if report.get('new_selfplay_games')!=0 or report.get('fits')!=0 or report.get('strength_games')!=0 or report.get('frozen_reads')!=0:
 raise SystemExit('forbidden action counter drift')
payload={**report,'schema':'jass.curriculum_search_error_terminal.v1','code_sha':code,
 'source_job':job,'source_attempt':attempt,'source_decisions':79110,
 'automatic_continuation':False,'promotion_authorized':False}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_FINAL
VERDICT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
: >"$ART/VERDICT__$VERDICT"; : >"$ART/WEIGHTS_BIT_IDENTICAL__TRUE"
: >"$ART/NEW_SELFPLAY__0"; : >"$ART/FITS__0"; : >"$ART/STRENGTH_GAMES__0"
: >"$ART/FROZEN_READS__0"; : >"$ART/PROMOTION_AUTHORIZED__FALSE"
stage completed
say "$VERDICT matched=$MATCHED/$SOURCE_ERRORS weights=bit-identical selfplay=0 fit=0 games=0"
