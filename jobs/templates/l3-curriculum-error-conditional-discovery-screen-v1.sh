#!/usr/bin/env bash
# Read-only discovery screen after the sealed negative 1486 global atlas.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

SOURCE_JOB="cpx62-1486-l3-curriculum-error-residual-atlas-v1"
SOURCE_ATTEMPT="20260822T193326Z-2e028428"
SOURCE_CODE="2e0284287657ca6b9325cb76e12e28376c873b0c"
SOURCE_ROOT="r2:jass-data/runs/$SOURCE_JOB/$SOURCE_ATTEMPT"
NSH=16

MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_seconds=%d\n' "$(( $(date +%s)-t0 ))"
      } >"$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 30
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
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-conditional-discovery-screen-v1$ ]] || die "invalid job nomenclature"
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
say "experiment=CURRICULUM_ERROR_CONDITIONAL_DISCOVERY_SCREEN source=$SOURCE_JOB/$SOURCE_ATTEMPT"
say "outer_confirm=consumed_forbidden selfplay=0 fits=0 strength_games=0 frozen=0"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_curriculum_error_conditional_discovery_screen.py
python3 -m unittest jobs.tests.test_l3_curriculum_error_conditional_discovery_screen \
  jobs.tests.test_l3_curriculum_error_residual_atlas >"$W/python-tests.log" 2>&1

stage fetch-authenticate-sealed-negative-1486
source_files=(
  --file artefacts/JASS_CONTROL_SUMMARY.json=source-summary.json
  --file artefacts/residual-atlas.json=residual-atlas.json
)
for shard in $(seq 0 $((NSH-1))); do
  source_files+=(--file "artefacts/residual-shards/shard-$shard.json=shard-$shard.json")
done
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_ROOT" \
  "${source_files[@]}" --out-dir "$IN" --report "$ART/verified-1486.json" \
  --expected-state completed >"$W/fetch-1486.log" 2>&1
python3 - "$IN" "$ART/verified-1486.json" "$SOURCE_JOB" "$SOURCE_ATTEMPT" "$SOURCE_CODE" "$NSH" <<'PY'
import json,sys
from pathlib import Path
src,receipt=Path(sys.argv[1]),json.load(open(sys.argv[2])); expected=tuple(sys.argv[3:6]); nsh=int(sys.argv[6])
got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'))
if got!=expected or receipt.get('result_state')!='completed' or receipt.get('exit_code')!=0:
 raise SystemExit(f'1486 receipt drift: {got!r}')
summary=json.load(open(src/'source-summary.json')); report=json.load(open(src/'residual-atlas.json'))
if summary.get('verdict')!='JASS_CURRICULUM_ERROR_RESIDUAL_REGION_NOT_ESTABLISHED':
 raise SystemExit('1486 summary is not the sealed negative result')
if report.get('verdict')!=summary.get('verdict') or report.get('pairs')!=353:
 raise SystemExit('1486 report/summary drift')
if report.get('all_splits')!={'confirm':158,'discovery':195} or report.get('splits')!={'confirm':130,'discovery':160}:
 raise SystemExit('1486 split cardinality drift')
for shard in range(nsh):
 row=json.load(open(src/f'shard-{shard}.json'))
 if row.get('schema')!='jass.l3_curriculum_error_residual_leaf_shard.v1' or row.get('shard')!=shard or row.get('nshards')!=nsh:
  raise SystemExit(f'1486 shard {shard} drift')
PY

stage authenticate-active-exact-fold-geometry
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
TOTAL_BUCKETS="$(PYTHONPATH=pattern_jass/tools python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')"
[ "$TOTAL_BUCKETS" -eq 4251528 ] || die "active 8cf geometry drift"
say "pattern_total_buckets=$TOTAL_BUCKETS"

stage discovery-only-conditional-screen
args=(); for shard in $(seq 0 $((NSH-1))); do args+=(--shard "$IN/shard-$shard.json"); done
python3 jobs/tools/l3_curriculum_error_conditional_discovery_screen.py \
  --atlas-report "$IN/residual-atlas.json" "${args[@]}" \
  --total-buckets "$TOTAL_BUCKETS" --split-seed 2026082226 \
  --bootstrap-seed 2026082227 --bootstrap-samples 10000 \
  --min-fit-pairs 12 --min-validation-pairs 6 --min-coordinate-hits 4 \
  --min-coordinate-fraction 0.15 --min-buckets 4 --max-buckets 32 \
  --report "$ART/conditional-discovery-screen.json" \
  --hypothesis "$ART/conditional-hypothesis.json" >"$W/screen.log" 2>&1

stage terminal-audit
python3 - "$ART/conditional-discovery-screen.json" "$ART/conditional-hypothesis.json" \
  "$ART/JASS_CONTROL_SUMMARY.json" "$TOTAL_BUCKETS" "$SOURCE_JOB" "$SOURCE_ATTEMPT" "$SOURCE_CODE" <<'PY'
import hashlib,json,re,sys
from pathlib import Path
report=json.load(open(sys.argv[1])); hypothesis=json.load(open(sys.argv[2])); out=Path(sys.argv[3])
total=int(sys.argv[4]); source=tuple(sys.argv[5:8])
allowed={'JASS_CURRICULUM_ERROR_CONDITIONAL_HYPOTHESIS_READY','JASS_CURRICULUM_ERROR_CONDITIONAL_HYPOTHESIS_NOT_ESTABLISHED'}
if report.get('schema')!='jass.l3_curriculum_error_conditional_discovery_screen.v1' or report.get('verdict') not in allowed:
 raise SystemExit('conditional screen schema/verdict drift')
if report.get('source_verdict')!='JASS_CURRICULUM_ERROR_RESIDUAL_REGION_NOT_ESTABLISHED':
 raise SystemExit('source verdict drift')
if report.get('outer_discovery_pairs')!=195 or report.get('outer_confirm_pairs_read_for_selection_or_evaluation')!=0:
 raise SystemExit('consumed outer confirmation leakage')
if report.get('pattern_total_buckets')!=total or total!=4251528: raise SystemExit('geometry drift')
if any(int(report.get(key,-1))!=0 for key in ('fits','strength_games','selfplay_games','frozen_reads')):
 raise SystemExit('forbidden action counter drift')
if report.get('fit_authorized') is not False or report.get('promotion_authorized') is not False or report.get('automatic_continuation') is not False:
 raise SystemExit('forbidden authorization drift')
if bool(report.get('fresh_campaign_authorized'))!=bool(report.get('passed')):
 raise SystemExit('fresh-campaign/report authorization drift')
if hypothesis.get('fit_authorized') is not False or hypothesis.get('promotion_authorized') is not False:
 raise SystemExit('hypothesis authorizes a forbidden action')
if bool(hypothesis.get('authorized'))!=bool(report.get('passed')):
 raise SystemExit('hypothesis/report verdict drift')
selected=report.get('selected_population')
if report.get('passed') and (not selected or not selected.get('direction')):
 raise SystemExit('positive screen lacks a sealed direction')
if not report.get('passed') and selected is not None:
 raise SystemExit('negative screen unexpectedly selected a population')
readout={'schema':'jass.curriculum_error_conditional_discovery_terminal.v1',
 'verdict':report['verdict'],'source_job':source[0],'source_attempt':source[1],'source_code':source[2],
 'source_atlas_sha256':report['source_atlas_sha256'],'outer_discovery_pairs':report['outer_discovery_pairs'],
 'outer_confirm_pairs_read_for_selection_or_evaluation':0,
 'eligible_exact_symmetry_stable_pairs':report['eligible_exact_symmetry_stable_pairs'],
 'exclusions':report['exclusions'],'inner_split':report['inner_split'],
 'candidate_family':report['candidate_family'],'candidate_results':report['candidate_results'],
 'selected_population':selected,'hypothesis_sha256':hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest(),
 'fresh_campaign_authorized':report['fresh_campaign_authorized'],'fit_authorized':False,
 'selfplay_games':0,'fits':0,'strength_games':0,'frozen_reads':0,
 'promotion_authorized':False,'automatic_continuation':False}
out.write_text(json.dumps(readout,indent=2,sort_keys=True)+'\n')
clean=lambda value: re.sub(r'[^A-Za-z0-9.+-]+','_',str(value)).strip('_')
markers={report['verdict'],'JASS_CURRICULUM_ERROR_CONDITIONAL_DISCOVERY_SCREEN_READY',
 f"ELIGIBLE_SYMMETRY_STABLE_PAIRS__{report['eligible_exact_symmetry_stable_pairs']}",
 f"CANDIDATES_EVALUATED__{len(report['candidate_results'])}",'OUTER_CONFIRM_READS__0',
 'FIT_AUTHORIZED__FALSE','NEW_SELFPLAY__0','FITS__0','STRENGTH_GAMES__0','FROZEN_READS__0',
 'PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_CONTINUATION__FALSE',
 ('NEXT_STAGE_RECOMMENDED__FRESH_CONDITIONAL_ERROR_CONFIRMATION' if report['passed'] else 'NEXT_STAGE__NONE')}
if selected:
 markers.add('SELECTED_POPULATION__'+clean(selected['population']))
 markers.add('SELECTED_BUCKETS__'+str(selected['selected_canonical_buckets']))
for marker in markers: (out.parent/marker).touch()
PY
cp "$ART/JASS_CONTROL_SUMMARY.json" "$ART/JASS_CURRICULUM_ERROR_CONDITIONAL_DISCOVERY_SCREEN_READY.json"
verdict=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
eligible=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["eligible_exact_symmetry_stable_pairs"])' "$ART/JASS_CONTROL_SUMMARY.json")
say "verdict=$verdict eligible_pairs=$eligible outer_confirm_reads=0"
say "fresh_campaign_only=true selfplay=0 fits=0 strength_games=0 frozen=0 promotion=false continuation=false"
stage complete
