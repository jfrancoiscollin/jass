#!/usr/bin/env bash
# Read-only PV-leaf Jacobian attribution of certified CURRICULUM errors.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
SHARDS="$ART/residual-shards"
mkdir -p "$W" "$IN" "$ART" "$SHARDS"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

SOURCE_JOB="cpx62-1476-l3-curriculum-search-error-atlas-v1"
SOURCE_ATTEMPT="20260822T170608Z-92a7f393"
SOURCE_CODE="92a7f393e26d41a1047e6660bee8724a9a64a5aa"
SOURCE_ROOT="r2:jass-data/runs/$SOURCE_JOB/$SOURCE_ATTEMPT"
CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE="18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_ROOT="r2:jass-data/runs/$CURRICULUM_JOB/$CURRICULUM_ATTEMPT"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
NSH=16
WORKERS=4
PAIRS=353
MAX_PROJECTED_MINUTES=60
CACHE_MB=128

MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        printf 'residual_shards=%s/%s\n' "$(find "$SHARDS" -name 'shard-*.json' 2>/dev/null | wc -l)" "$NSH"
      } >"$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 60
    done ) & MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-residual-atlas-v1$ ]] || die "invalid job nomenclature"
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
say "experiment=CURRICULUM_ERROR_RESIDUAL_ATLAS source=$SOURCE_JOB/$SOURCE_ATTEMPT"
say "pairs=$PAIRS weights=bit-identical selfplay=0 fit=0 strength_games=0 frozen=0"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_curriculum_error_residual_atlas.py \
  jobs/tools/l3_context3_decision_flip_autopsy.py
python3 -m unittest jobs.tests.test_l3_curriculum_error_residual_atlas \
  jobs.tests.test_l3_context3_decision_flip_autopsy \
  jobs.tests.test_l3_curriculum_search_error_atlas \
  pattern_jass.tests.test_train_stream_local_refit >"$W/python-tests.log" 2>&1

stage fetch-authenticate-1476-and-curriculum
source_files=(
  --file artefacts/JASS_CONTROL_SUMMARY.json=source-summary.json
  --file artefacts/matched-pairs.json=matched-pairs.json
  --file artefacts/search-params.txt=search-params.txt
  --file artefacts/source-certificate.json=source-certificate.json
)
for shard in $(seq 0 $((NSH-1))); do
  source_files+=(--file "artefacts/atlas-shards/shard-$shard.json=atlas-shard-$shard.json")
done
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_ROOT" \
  "${source_files[@]}" --out-dir "$IN" --report "$ART/verified-1476.json" \
  --expected-state completed >"$W/fetch-1476.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=curriculum-summary.json \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" \
  --expected-state completed >"$W/fetch-curriculum.log" 2>&1
gunzip -t "$IN/curriculum.pjtw.gz"
gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
python3 - "$IN" "$ART" "$SOURCE_JOB" "$SOURCE_ATTEMPT" "$SOURCE_CODE" \
  "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" "$CURRICULUM_CODE" "$CURRICULUM_SHA" "$PAIRS" "$NSH" <<'PY'
import hashlib,json,sys
from pathlib import Path
src,art=map(Path,sys.argv[1:3]); source=tuple(sys.argv[3:6]); curriculum=tuple(sys.argv[6:9])
model_sha=sys.argv[9]; pairs=int(sys.argv[10]); nsh=int(sys.argv[11])
for name,want in (("verified-1476.json",source),("verified-curriculum.json",curriculum)):
 receipt=json.load(open(art/name)); got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'))
 if got!=want or receipt.get('result_state')!='completed' or receipt.get('exit_code')!=0:
  raise SystemExit(f'{name} identity/state drift: {got!r}')
summary=json.load(open(src/'source-summary.json')); matched=json.load(open(src/'matched-pairs.json'))
if summary.get('verdict')!='JASS_CURRICULUM_SEARCH_ERROR_CONTROLLER_NOT_ESTABLISHED': raise SystemExit('1476 verdict drift')
if matched.get('matched_pairs')!=pairs or matched.get('matching_passed') is not True: raise SystemExit('pair certificate drift')
digest=hashlib.sha256((src/'matched-pairs.json').read_bytes()).hexdigest()
for shard in range(nsh):
 row=json.load(open(src/f'atlas-shard-{shard}.json'))
 if row.get('schema')!='jass.l3_curriculum_search_error_atlas_shard.v1': raise SystemExit('atlas schema drift')
 if row.get('pairs_sha256')!=digest or row.get('shard')!=shard or row.get('nshards')!=nsh or row.get('max_pairs')!=0:
  raise SystemExit(f'atlas shard {shard} identity drift')
 if row.get('champion_sha256')!=model_sha: raise SystemExit('source champion drift')
if hashlib.sha256((src/'search-params.txt').read_bytes()).hexdigest()!=json.load(open(src/'atlas-shard-0.json'))['search_params_sha256']:
 raise SystemExit('search-params hash drift')
PY
[ "$(sha256sum "$W/curriculum.pjtw" | awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM raw hash drift"
cp "$IN/search-params.txt" "$ART/search-params.txt"

stage build-current-exact-fold-tempo-engine-with-pv-leaf-identity
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
printf 'position startpos\ngo depth 2\nquit\n' | timeout 60 "$J" --pattern "$W/curriculum.pjtw" \
  --search-params "$(cat "$ART/search-params.txt")" >"$W/pvleaf-smoke.log" 2>&1
grep -q ' pvleaf=' "$W/pvleaf-smoke.log" || die "PV leaf identity missing from HUB result"

stage exact-cost-preflight
SECONDS=0
python3 jobs/tools/l3_curriculum_error_residual_atlas.py worker \
  --atlas-shard "$IN/atlas-shard-0.json" --jass "$J" --champion "$W/curriculum.pjtw" \
  --search-params "$ART/search-params.txt" --shard 0 --nshards "$NSH" --max-pairs 1 \
  --out "$W/preflight.json" >"$W/preflight.log" 2>&1
preflight_seconds=$SECONDS
max_pairs_per_shard=$(( (PAIRS + NSH - 1) / NSH ))
projected_seconds=$(( preflight_seconds * max_pairs_per_shard ))
waves=$(( (NSH + WORKERS - 1) / WORKERS ))
projected_seconds=$(( projected_seconds * waves ))
python3 - "$W/preflight.json" "$ART/cost-preflight.json" "$preflight_seconds" "$projected_seconds" "$MAX_PROJECTED_MINUTES" "$WORKERS" "$waves" <<'PY'
import json,sys
src,out=sys.argv[1:3]; elapsed,projected,limit,workers,waves=map(int,sys.argv[3:])
row=json.load(open(src)); passed=row.get('pairs')==1 and projected<=limit*60
json.dump({'schema':'jass.curriculum_error_residual_cost.v1','sample_pairs':row.get('pairs'),
 'elapsed_seconds':elapsed,'projected_parallel_seconds':projected,'workers':workers,
 'waves':waves,'limit_minutes':limit,'passed':passed},open(out,'w'),indent=2,sort_keys=True)
if not passed: raise SystemExit('residual atlas projected runtime exceeds limit')
PY

stage pv-leaf-jacobian-shards
failed=0; : >"$W/worker-failures.txt"
for batch_start in $(seq 0 "$WORKERS" $((NSH-1))); do
  pids=(); shards=()
  for shard in $(seq "$batch_start" $((batch_start+WORKERS-1))); do
    [ "$shard" -lt "$NSH" ] || continue
    python3 jobs/tools/l3_curriculum_error_residual_atlas.py worker \
      --atlas-shard "$IN/atlas-shard-$shard.json" --jass "$J" --champion "$W/curriculum.pjtw" \
      --search-params "$ART/search-params.txt" --shard "$shard" --nshards "$NSH" \
      --out "$SHARDS/shard-$shard.json" >"$W/worker-$shard.log" 2>&1 &
    pids+=("$!"); shards+=("$shard")
  done
  for index in "${!pids[@]}"; do
    if wait "${pids[$index]}"; then rc=0; else rc=$?; failed=1; fi
    [ "$rc" -eq 0 ] || printf 'shard=%s rc=%s\n' "${shards[$index]}" "$rc" >>"$W/worker-failures.txt"
  done
done
if [ "$failed" -ne 0 ]; then
  python3 - "$W" "$SHARDS" "$ART/worker-root-cause.json" "$WORKERS" <<'PY_WORKERS'
import collections,json,re,sys
from pathlib import Path
w,shards,out=map(Path,sys.argv[1:4]); workers=int(sys.argv[4]); failures=[]
for line in (w/'worker-failures.txt').read_text().splitlines():
 match=re.fullmatch(r'shard=(\d+) rc=(\d+)',line)
 if not match: raise SystemExit(f'malformed worker failure line: {line!r}')
 shard,rc=map(int,match.groups()); path=w/f'worker-{shard}.log'
 lines=path.read_text(errors='replace').splitlines() if path.exists() else []
 tail=lines[-40:]
 terminal=[value.strip() for value in tail if re.match(r'^(?:[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception)|SystemExit|AssertionError):\s*.+$',value.strip())]
 failures.append({'shard':shard,'returncode':rc,'log_tail':tail,
                  'terminal_exception':terminal[-1] if terminal else None})
payload={'schema':'jass.curriculum_error_residual_worker_failure.v1',
 'verdict':'JASS_CURRICULUM_ERROR_RESIDUAL_WORKER_FAILURE_READY',
 'workers':workers,'failures':failures,'failed_shards':[row['shard'] for row in failures],
 'completed_shards':len(list(shards.glob('shard-*.json'))),
 'fits':0,'strength_games':0,'selfplay_games':0,'frozen_reads':0,'promotion_authorized':False}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
clean=lambda value: re.sub(r'[^A-Za-z0-9.+-]+','_',str(value)).strip('_')
counts=collections.Counter(row['terminal_exception'] or 'UNCLASSIFIED' for row in failures)
for value,count in counts.items():
 marker=f'WORKER_EXCEPTION_COUNT_{count}__{clean(value)[:180]}'
 if len(marker.encode())>240: raise SystemExit(f'worker exception marker too long: {marker}')
 (out.parent/marker).touch()
PY_WORKERS
  : >"$ART/JASS_CURRICULUM_ERROR_RESIDUAL_WORKER_FAILURE_READY"
  die "one or more residual workers failed; see worker-root-cause.json"
fi
[ "$(find "$SHARDS" -name 'shard-*.json' | wc -l)" -eq "$NSH" ] || die "residual shard count drift"

stage sealed-discovery-confirm-aggregate
args=(); for shard in $(seq 0 $((NSH-1))); do args+=(--shard "$SHARDS/shard-$shard.json"); done
python3 jobs/tools/l3_curriculum_error_residual_atlas.py aggregate "${args[@]}" \
  --min-discovery-hits 6 --min-region-buckets 8 --max-region-buckets 128 \
  --min-orientation-cosine 0.0 --min-coordinate-replication 0.70 \
  --bootstrap-samples 100000 --permutation-samples 10000 --seed 2026082222 \
  --expected-informative-errors 290 \
  --report "$ART/residual-atlas.json" --region "$ART/error-residual-region.json" \
  >"$W/aggregate.log" 2>&1

stage terminal-audit
python3 - "$ART/residual-atlas.json" "$ART/error-residual-region.json" "$ART/JASS_CONTROL_SUMMARY.json" "$CURRICULUM_SHA" "$PAIRS" <<'PY'
import json,re,sys
from pathlib import Path
report=json.load(open(sys.argv[1])); region=json.load(open(sys.argv[2])); out=Path(sys.argv[3])
champion=sys.argv[4]; pairs=int(sys.argv[5])
allowed={'JASS_CURRICULUM_ERROR_RESIDUAL_REGION_CONFIRMED','JASS_CURRICULUM_ERROR_RESIDUAL_REGION_NOT_ESTABLISHED'}
if report.get('verdict') not in allowed or report.get('pairs')!=pairs: raise SystemExit('terminal report drift')
if report.get('informative_error_pairs')!=290: raise SystemExit('1476 exact-error cardinality drift')
if report.get('reclassified_exact_non_errors',{}).get('total')!=pairs-290:
 raise SystemExit('exact non-error reclassification cardinality drift')
if report.get('champion_sha256')!=champion: raise SystemExit('champion identity drift')
if any(int(report.get(key,-1))!=0 for key in ('fits','strength_games','selfplay_games','frozen_reads')):
 raise SystemExit('forbidden action counter drift')
if report.get('promotion_authorized') is not False or report.get('automatic_continuation') is not False:
 raise SystemExit('forbidden continuation drift')
if bool(region.get('fit_authorized')) != bool(report.get('passed')): raise SystemExit('region/report authorization drift')
readout={'schema':'jass.curriculum_error_residual_terminal.v1','verdict':report['verdict'],
 'source_job':'cpx62-1476-l3-curriculum-search-error-atlas-v1','source_attempt':'20260822T170608Z-92a7f393',
 'champion_sha256':champion,'pairs':pairs,'splits':report['splits'],
 'all_splits':report['all_splits'],'informative_error_pairs':report['informative_error_pairs'],
 'reclassified_exact_non_errors':report['reclassified_exact_non_errors'],
 'selected_canonical_buckets':report['selected_canonical_buckets'],
 'selected_full_columns':report['selected_full_columns'],
 'orientation_symmetry_fraction':report['orientation_symmetry_fraction'],
 'forced_controls':report['forced_controls'],
 'coordinate_replication_fraction':report['coordinate_replication_fraction'],
 'confirm':report['confirm'],'gates':report['gates'],'failed_gates':report['failed_gates'],
 'fit_authorized':report['passed'],'next_stage':report['next_stage'],
 'weights_bit_identical':True,'selfplay':0,'fits':0,'strength_games':0,'frozen_reads':0,
 'promotion_authorized':False,'automatic_continuation':False}
out.write_text(json.dumps(readout,indent=2,sort_keys=True)+'\n')
clean=lambda value: re.sub(r'[^A-Za-z0-9.+-]+','_',str(value)).strip('_')
markers={report['verdict'],'JASS_CURRICULUM_ERROR_RESIDUAL_ATLAS_READY',
 f"SELECTED_BUCKETS__{report['selected_canonical_buckets']}",
 f"ORIENTATION_SYMMETRY_FRACTION__{clean(report['orientation_symmetry_fraction'])}",
 f"COORDINATE_REPLICATION_FRACTION__{clean(report['coordinate_replication_fraction'])}",
 f"FORCED_CONTROLS__{report['forced_controls']['total']}",
 f"FORCED_CONTROL_FRACTION__{clean(report['forced_controls']['fraction'])}",
 f"INFORMATIVE_CONFIRM_PAIRS__{report['forced_controls']['informative_confirm_pairs']}",
 f"INFORMATIVE_ERROR_PAIRS__{report['informative_error_pairs']}",
 f"RECLASSIFIED_EXACT_NON_ERRORS__{report['reclassified_exact_non_errors']['total']}",
 'WEIGHTS_BIT_IDENTICAL__TRUE','NEW_SELFPLAY__0','FITS__0','STRENGTH_GAMES__0',
 'FROZEN_READS__0','PROMOTION_AUTHORIZED__FALSE',
 ('NEXT_STAGE_RECOMMENDED__LOCAL_RESIDUAL_REFIT' if report['passed'] else 'NEXT_STAGE__NONE'),
 'FAILED_GATES__'+('+'.join(report['failed_gates']) or 'NONE')}
for marker in markers: (out.parent/marker).touch()
PY
cp "$ART/JASS_CONTROL_SUMMARY.json" "$ART/JASS_CURRICULUM_ERROR_RESIDUAL_ATLAS_READY.json"
verdict=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
selected=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["selected_canonical_buckets"])' "$ART/JASS_CONTROL_SUMMARY.json")
failed_gates=$(python3 -c 'import json,sys;print("+".join(json.load(open(sys.argv[1]))["failed_gates"]) or "none")' "$ART/JASS_CONTROL_SUMMARY.json")
say "verdict=$verdict selected_buckets=$selected failed_gates=$failed_gates"
say "weights=bit-identical selfplay=0 fits=0 strength_games=0 frozen=0 promotion=false automatic_continuation=false"
stage complete
