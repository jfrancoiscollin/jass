#!/usr/bin/env bash
# Read-only, zero-node root-score trajectory screen on sealed 1476 discovery.
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

SOURCE_JOB="cpx62-1476-l3-curriculum-search-error-atlas-v1"
SOURCE_ATTEMPT="20260822T170608Z-92a7f393"
SOURCE_CODE="92a7f393e26d41a1047e6660bee8724a9a64a5aa"
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
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-root-trajectory-screen-v1$ ]] || die "invalid job nomenclature"
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
say "experiment=CURRICULUM_ERROR_ROOT_TRAJECTORY_SCREEN source=$SOURCE_JOB/$SOURCE_ATTEMPT"
say "signal=existing_depth8_depth9_root_scores additional_nodes=0 outer_confirm=forbidden"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_curriculum_error_root_trajectory_screen.py
python3 -m unittest jobs.tests.test_l3_curriculum_error_root_trajectory_screen \
  jobs.tests.test_l3_curriculum_search_error_atlas >"$W/python-tests.log" 2>&1

stage fetch-authenticate-1476
source_files=(
  --file artefacts/JASS_CONTROL_SUMMARY.json=source-summary.json
  --file artefacts/matched-pairs.json=matched-pairs.json
  --file artefacts/search-error-atlas.json=search-error-atlas.json
)
for shard in $(seq 0 $((NSH-1))); do
  source_files+=(--file "artefacts/atlas-shards/shard-$shard.json=atlas-shard-$shard.json")
done
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_ROOT" \
  "${source_files[@]}" --out-dir "$IN" --report "$ART/verified-1476.json" \
  --expected-state completed >"$W/fetch-1476.log" 2>&1
python3 - "$IN" "$ART/verified-1476.json" "$SOURCE_JOB" "$SOURCE_ATTEMPT" "$SOURCE_CODE" "$NSH" <<'PY'
import hashlib,json,sys
from pathlib import Path
src,receipt=Path(sys.argv[1]),json.load(open(sys.argv[2])); expected=tuple(sys.argv[3:6]); nsh=int(sys.argv[6])
got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'))
if got!=expected or receipt.get('result_state')!='completed' or receipt.get('exit_code')!=0:
 raise SystemExit(f'1476 receipt drift: {got!r}')
summary=json.load(open(src/'source-summary.json')); report=json.load(open(src/'search-error-atlas.json'))
if summary.get('verdict')!='JASS_CURRICULUM_SEARCH_ERROR_CONTROLLER_NOT_ESTABLISHED':
 raise SystemExit('1476 terminal verdict drift')
if report.get('verdict')!=summary.get('verdict') or report.get('source',{}).get('matched_pairs')!=353:
 raise SystemExit('1476 report/summary drift')
pairs=json.load(open(src/'matched-pairs.json'))
if pairs.get('matched_pairs')!=353 or pairs.get('pairs_by_split')!={'confirm':158,'discovery':195}:
 raise SystemExit('1476 pair certificate drift')
digest=hashlib.sha256((json.dumps(pairs,indent=2,sort_keys=True)+'\n').encode()).hexdigest()
for shard in range(nsh):
 row=json.load(open(src/f'atlas-shard-{shard}.json'))
 if row.get('schema')!='jass.l3_curriculum_search_error_atlas_shard.v1' or row.get('shard')!=shard or row.get('nshards')!=nsh:
  raise SystemExit(f'1476 atlas shard {shard} drift')
 if row.get('pairs_sha256')!=digest: raise SystemExit(f'1476 atlas shard {shard} pair hash drift')
PY

stage outer-discovery-root-trajectory-screen
args=(); for shard in $(seq 0 $((NSH-1))); do args+=(--atlas-shard "$IN/atlas-shard-$shard.json"); done
python3 jobs/tools/l3_curriculum_error_root_trajectory_screen.py \
  --pairs "$IN/matched-pairs.json" "${args[@]}" \
  --split-seed 2026082228 --bootstrap-seed 2026082229 --bootstrap-samples 10000 \
  --report "$ART/root-trajectory-screen.json" \
  --hypothesis "$ART/root-trajectory-hypothesis.json" >"$W/screen.log" 2>&1

stage terminal-audit
python3 - "$ART/root-trajectory-screen.json" "$ART/root-trajectory-hypothesis.json" \
  "$ART/JASS_CONTROL_SUMMARY.json" "$SOURCE_JOB" "$SOURCE_ATTEMPT" "$SOURCE_CODE" <<'PY'
import hashlib,json,re,sys
from pathlib import Path
report=json.load(open(sys.argv[1])); hypothesis=json.load(open(sys.argv[2])); out=Path(sys.argv[3]); source=tuple(sys.argv[4:7])
allowed={'JASS_CURRICULUM_ERROR_ROOT_TRAJECTORY_HYPOTHESIS_READY','JASS_CURRICULUM_ERROR_ROOT_TRAJECTORY_HYPOTHESIS_NOT_ESTABLISHED'}
if report.get('schema')!='jass.l3_curriculum_error_root_trajectory_screen.v1' or report.get('verdict') not in allowed:
 raise SystemExit('trajectory report schema/verdict drift')
if report.get('outer_discovery_pairs')!=195 or report.get('informative_discovery_pairs')!=160:
 raise SystemExit('trajectory discovery cardinality drift')
if report.get('outer_confirm_pairs_read_for_selection_or_evaluation')!=0:
 raise SystemExit('consumed 1476 outer-confirm leakage')
if report.get('protocol',{}).get('additional_search_nodes')!=0 or report['protocol'].get('curriculum_scalar_unchanged') is not True:
 raise SystemExit('zero-node/scalar contract drift')
if len(report.get('candidate_results',[]))!=12: raise SystemExit('candidate family drift')
if any(int(report.get(key,-1))!=0 for key in ('pattern_eval_fits','production_model_fits','strength_games','selfplay_games','frozen_reads')):
 raise SystemExit('forbidden action counter drift')
if report.get('production_rule_authorized') is not False or report.get('promotion_authorized') is not False or report.get('automatic_continuation') is not False:
 raise SystemExit('forbidden authorization drift')
if bool(report.get('fresh_campaign_authorized'))!=bool(report.get('passed')):
 raise SystemExit('fresh confirmation authorization drift')
if hypothesis.get('production_rule_authorized') is not False or hypothesis.get('promotion_authorized') is not False:
 raise SystemExit('hypothesis authorizes production')
if bool(hypothesis.get('authorized'))!=bool(report.get('passed')):
 raise SystemExit('hypothesis/report verdict drift')
readout={'schema':'jass.curriculum_error_root_trajectory_terminal.v1',
 'verdict':report['verdict'],'source_job':source[0],'source_attempt':source[1],'source_code':source[2],
 'source_pairs_sha256':report['source_pairs_sha256'],'outer_discovery_pairs':195,
 'informative_discovery_pairs':160,'outer_confirm_pairs_read_for_selection_or_evaluation':0,
 'inner_split':report['inner_split'],'protocol':report['protocol'],
 'candidate_results':report['candidate_results'],'selected_candidate':report['selected_candidate'],
 'validation':report['validation'],'validation_gates':report['validation_gates'],
 'failed_validation_gates':report['failed_validation_gates'],
 'hypothesis_sha256':hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest(),
 'fresh_campaign_authorized':report['fresh_campaign_authorized'],
 'production_rule_authorized':False,'pattern_eval_fits':0,'production_model_fits':0,
 'selfplay_games':0,'strength_games':0,'frozen_reads':0,'promotion_authorized':False,
 'automatic_continuation':False,'next_stage':report['next_stage']}
out.write_text(json.dumps(readout,indent=2,sort_keys=True)+'\n')
clean=lambda value: re.sub(r'[^A-Za-z0-9.+-]+','_',str(value)).strip('_')
markers={report['verdict'],'JASS_CURRICULUM_ERROR_ROOT_TRAJECTORY_SCREEN_READY',
 'OUTER_CONFIRM_READS__0','ADDITIONAL_SEARCH_NODES__0','CURRICULUM_SCALAR_UNCHANGED__TRUE',
 'PATTERNEVAL_FITS__0','PRODUCTION_MODEL_FITS__0','NEW_SELFPLAY__0','STRENGTH_GAMES__0',
 'FROZEN_READS__0','PRODUCTION_RULE_AUTHORIZED__FALSE','PROMOTION_AUTHORIZED__FALSE',
 f"INNER_SPLIT__FIT_{report['inner_split']['fit_pairs']}__VALIDATION_{report['inner_split']['validation_pairs']}",
 ('NEXT_STAGE_RECOMMENDED__FRESH_ROOT_TRAJECTORY_CONFIRMATION' if report['passed'] else 'NEXT_STAGE__NONE')}
for row in report['candidate_results']:
 fit=row['fit']; label='ALWAYS' if row['margin_label']=='always' else row['margin_label']
 markers.add(f"CANDIDATE__BETA_{clean(row['beta'])}__MARGIN_{label}__PASS_{str(row['fit_passed']).upper()}__ERR_{clean(fit['error_improvement']['mean'])}__PAIRED_{clean(fit['paired_error_minus_control']['mean'])}__FLIPS_{fit['error_changed_pairs']}")
if report['selected_candidate']:
 selected=report['selected_candidate']; markers.add(f"SELECTED__BETA_{clean(selected['beta'])}__MARGIN_{clean(selected['margin_label'])}")
if report['validation']:
 validation=report['validation']
 markers.add(f"VALIDATION__ERROR_MEAN_{clean(validation['error_improvement']['mean'])}__CI95_{clean(validation['error_improvement']['ci95'][0])}_{clean(validation['error_improvement']['ci95'][1])}")
 markers.add(f"VALIDATION__PAIRED_MEAN_{clean(validation['paired_error_minus_control']['mean'])}__CI95_{clean(validation['paired_error_minus_control']['ci95'][0])}_{clean(validation['paired_error_minus_control']['ci95'][1])}")
for marker in markers:
 if len(marker.encode())>240: raise SystemExit(f'marker too long: {marker}')
 (out.parent/marker).touch()
PY
cp "$ART/JASS_CONTROL_SUMMARY.json" "$ART/JASS_CURRICULUM_ERROR_ROOT_TRAJECTORY_SCREEN_READY.json"
verdict=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
say "verdict=$verdict outer_confirm_reads=0 additional_nodes=0 fits=0 games=0 frozen=0"
stage complete
