#!/usr/bin/env bash
# Target-free trace variability diagnostic after the certified zero-margin screen.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${COVERAGE_SOURCE_JOB:?}"; : "${COVERAGE_SOURCE_ATTEMPT:?}"; : "${COVERAGE_SOURCE_CODE:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"; RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; for log in tests fetch diagnostic; do [ -s "$W/$log.log" ] && cp "$W/$log.log" "$ART/$log.log"; done; rm -rf "$IN"; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-trace-variability-screen-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "job worktree contract mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${NO_FIT:-0}" = 1 ] && [ "${NO_SELFPLAY:-0}" = 1 ] && [ "${NO_STRENGTH_GAMES:-0}" = 1 ] || die "read-only guards missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] && [ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"

python3 -m py_compile jobs/tools/l3_curriculum_error_trace_variability_screen.py
python3 -m unittest jobs.tests.test_l3_curriculum_error_trace_variability_screen jobs.tests.test_l3_curriculum_error_trace_variability_template >"$W/tests.log" 2>&1
ROOT="r2:jass-data/runs/$COVERAGE_SOURCE_JOB/$COVERAGE_SOURCE_ATTEMPT"
python3 jobs/tools/fetch_result_files.py --prefix "$ROOT" \
  --file artefacts/matched-pairs.json=matched-pairs.json \
  --file artefacts/paired-coverage-screen.json=failed-coverage.json \
  --out-dir "$IN" --report "$ART/verified-coverage-source.json" --expected-state completed >"$W/fetch.log" 2>&1
python3 - "$ART" "$COVERAGE_SOURCE_JOB" "$COVERAGE_SOURCE_ATTEMPT" "$COVERAGE_SOURCE_CODE" <<'PY_AUTH'
import json,sys
from pathlib import Path
receipt=json.load(open(Path(sys.argv[1])/'verified-coverage-source.json')); want=tuple(sys.argv[2:5])
got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'))
if got!=want or receipt.get('result_state')!='completed' or receipt.get('exit_code')!=0:
    raise SystemExit(f'coverage source identity/state drift got={got} want={want}')
PY_AUTH
python3 jobs/tools/l3_curriculum_error_trace_variability_screen.py \
  --pairs "$IN/matched-pairs.json" --failed-coverage "$IN/failed-coverage.json" \
  --coverage-job "$COVERAGE_SOURCE_JOB" --coverage-attempt "$COVERAGE_SOURCE_ATTEMPT" \
  --coverage-code "$COVERAGE_SOURCE_CODE" \
  --report "$ART/JASS_CONTROL_SUMMARY.json" >"$W/diagnostic.log" 2>&1
python3 - "$ART" <<'PY_MARKERS'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); report=json.load(open(art/'JASS_CONTROL_SUMMARY.json')); (art/report['verdict']).touch()
for name,row in ((item['name'],item) for item in report['candidates']):
    (art/f"PROXY__{name.upper()}__PASSED__{str(row['passed']).upper()}__Q20_{row['lower_open']}__Q60_{row['upper_closed']}").touch()
for name,value in report['global_gates'].items(): (art/f"GATE__{name.upper()}__{str(value).upper()}").touch()
for name in ('EXACT_ACTION_VALUE_READS__0','OUTER_CONFIRM_PROFILE_ROWS_EXAMINED__0','OUTER_CONFIRM_ACTION_VALUE_READS__0','DIAGNOSTIC_FITS__0','STRENGTH_GAMES__0','FROZEN_READS__0','PROMOTION_AUTHORIZED__FALSE'): (art/name).touch()
PY_MARKERS
VERDICT=$(python3 -c 'import json,sys;r=json.load(open(sys.argv[1]));print(r["verdict"]+" selected="+str((r.get("selected_proxy") or {}).get("name")))' "$ART/JASS_CONTROL_SUMMARY.json")
say "$VERDICT targets=0 fits=0 confirm=0"
