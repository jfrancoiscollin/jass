#!/usr/bin/env bash
# Read-only pre-registration of the single target-free trace proxy selected by 1506.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${TRACE_SOURCE_JOB:?}"; : "${TRACE_SOURCE_ATTEMPT:?}"; : "${TRACE_SOURCE_CODE:?}"
: "${COVERAGE_SOURCE_JOB:?}"; : "${COVERAGE_SOURCE_ATTEMPT:?}"; : "${COVERAGE_SOURCE_CODE:?}"
: "${ACTION_SOURCE_JOB:?}"; : "${ACTION_SOURCE_ATTEMPT:?}"; : "${ACTION_SOURCE_CODE:?}"
cd "$JASS_CODE_DIR"; W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"; RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; for log in tests trace-fetch coverage-fetch action-fetch preregistration; do [ -s "$W/$log.log" ] && cp "$W/$log.log" "$ART/$log.log"; done; rm -rf "$IN"; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-trace-proxy-preregistration-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"; [ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree contract mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${NO_FIT:-0}" = 1 ] && [ "${NO_SELFPLAY:-0}" = 1 ] && [ "${NO_STRENGTH_GAMES:-0}" = 1 ] || die "read-only guards missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] && [ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"
python3 -m py_compile jobs/tools/l3_curriculum_error_trace_proxy_preregistration.py
python3 -m unittest jobs.tests.test_l3_curriculum_error_trace_proxy_preregistration jobs.tests.test_l3_curriculum_error_trace_proxy_preregistration_template >"$W/tests.log" 2>&1
fetch(){ local job="$1" attempt="$2" remote="$3" local_name="$4" receipt="$5" log="$6"; python3 jobs/tools/fetch_result_files.py --prefix "r2:jass-data/runs/$job/$attempt" --file "artefacts/JASS_CONTROL_SUMMARY.json=$local_name" --out-dir "$IN" --report "$ART/$receipt" --expected-state completed >"$W/$log.log" 2>&1; }
fetch "$TRACE_SOURCE_JOB" "$TRACE_SOURCE_ATTEMPT" trace trace-report.json verified-trace-source.json trace-fetch
fetch "$COVERAGE_SOURCE_JOB" "$COVERAGE_SOURCE_ATTEMPT" coverage coverage-report.json verified-coverage-source.json coverage-fetch
fetch "$ACTION_SOURCE_JOB" "$ACTION_SOURCE_ATTEMPT" action action-source.json verified-action-source.json action-fetch
python3 - "$ART" "$TRACE_SOURCE_JOB" "$TRACE_SOURCE_ATTEMPT" "$TRACE_SOURCE_CODE" "$COVERAGE_SOURCE_JOB" "$COVERAGE_SOURCE_ATTEMPT" "$COVERAGE_SOURCE_CODE" "$ACTION_SOURCE_JOB" "$ACTION_SOURCE_ATTEMPT" "$ACTION_SOURCE_CODE" <<'PY_AUTH'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); values=sys.argv[2:]
for index,name in enumerate(('verified-trace-source.json','verified-coverage-source.json','verified-action-source.json')):
    receipt=json.load(open(art/name)); want=tuple(values[index*3:index*3+3]); got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'))
    if got!=want or receipt.get('result_state')!='completed' or receipt.get('exit_code')!=0: raise SystemExit(f'{name} identity/state drift got={got} want={want}')
PY_AUTH
python3 jobs/tools/l3_curriculum_error_trace_proxy_preregistration.py --trace-report "$IN/trace-report.json" --trace-job "$TRACE_SOURCE_JOB" --trace-attempt "$TRACE_SOURCE_ATTEMPT" --trace-code "$TRACE_SOURCE_CODE" --coverage-report "$IN/coverage-report.json" --action-source "$IN/action-source.json" --action-job "$ACTION_SOURCE_JOB" --action-attempt "$ACTION_SOURCE_ATTEMPT" --action-code "$ACTION_SOURCE_CODE" --output "$ART/JASS_CONTROL_SUMMARY.json" >"$W/preregistration.log" 2>&1
python3 - "$ART" <<'PY_MARKERS'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); report=json.load(open(art/'JASS_CONTROL_SUMMARY.json')); (art/report['verdict']).touch()
(art/'FIXED__MAX_DEPTH_SCORE_SPREAD_GT52_LE154__ALPHA_100__CAP_75__CONSENSUS').touch()
for name in ('VALIDATION_ACTION_VALUE_READS__0','OUTER_CONFIRM_PROFILE_ROWS_EXAMINED__0','OUTER_CONFIRM_ACTION_VALUE_READS__0','DIAGNOSTIC_FITS__0','PATTERNEVAL_FITS__0','STRENGTH_GAMES__0','FROZEN_READS__0','PROMOTION_AUTHORIZED__FALSE'): (art/name).touch()
PY_MARKERS
say "JASS_CURRICULUM_ERROR_TRACE_PROXY_PREREGISTERED architectures=1 targets=0 fits=0 confirm=0"
