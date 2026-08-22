#!/usr/bin/env bash
# Read-only OOF gate autopsy; validation and confirm remain sealed.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${RANKER_SOURCE_JOB:?}"; : "${RANKER_SOURCE_ATTEMPT:?}"; : "${RANKER_SOURCE_CODE:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; rm -rf "$IN"; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-action-ranker-readout-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${NO_FIT:-0}" = 1 ] && [ "${NO_SELFPLAY:-0}" = 1 ] && [ "${NO_STRENGTH_GAMES:-0}" = 1 ] || die "read-only guards missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] && [ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"

python3 -m py_compile jobs/tools/l3_curriculum_error_action_ranker_oof_autopsy.py
python3 -m unittest jobs.tests.test_l3_curriculum_error_action_ranker_oof_autopsy >"$W/tests.log" 2>&1

ROOT="r2:jass-data/runs/$RANKER_SOURCE_JOB/$RANKER_SOURCE_ATTEMPT"
python3 jobs/tools/fetch_result_files.py --prefix "$ROOT" \
  --file artefacts/action-ranker-screen.json=report.json \
  --file artefacts/action-ranker-model.json=model.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=source-summary.json \
  --out-dir "$IN" --report "$ART/verified-source.json" --expected-state completed >"$W/fetch.log" 2>&1
python3 - "$ART/verified-source.json" "$RANKER_SOURCE_JOB" "$RANKER_SOURCE_ATTEMPT" "$RANKER_SOURCE_CODE" <<'PY_AUTH'
import json,sys
receipt=json.load(open(sys.argv[1])); got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'))
want=tuple(sys.argv[2:5])
if got!=want: raise SystemExit(f"source identity mismatch got={got} want={want}")
PY_AUTH

python3 jobs/tools/l3_curriculum_error_action_ranker_oof_autopsy.py \
  --report "$IN/report.json" --model "$IN/model.json" --output "$ART/JASS_CONTROL_SUMMARY.json" >"$W/autopsy.log" 2>&1
python3 - "$ART" <<'PY_MARKERS'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); report=json.load(open(art/'JASS_CONTROL_SUMMARY.json'))
(art/report['verdict']).touch()
(art/f"POSITIVE_PAIRED_MEAN_CANDIDATES__{report['positive_paired_mean_candidate_count']}").touch()
best=report['best_paired_mean_candidate']
(art/f"BEST__A_{best['alpha']}__T_{int(best['advantage_threshold_cp'])}__M_{int(best['margin_band_cp'])}__PAIRED_{best['paired_error_minus_control']['mean']}").touch()
for gate,count in report['gate_failure_histogram'].items():
    (art/f"GATE_FAIL__{gate.upper()}__{count}").touch()
(art/'VALIDATION_DECISION_PAYLOAD_READS__0').touch()
(art/'OUTER_CONFIRM_DECISION_PAYLOAD_READS__0').touch()
(art/'DIAGNOSTIC_FITS__0').touch(); (art/'STRENGTH_GAMES__0').touch(); (art/'FROZEN_READS__0').touch(); (art/'PROMOTION_AUTHORIZED__FALSE').touch()
PY_MARKERS
say "JASS_CURRICULUM_ERROR_ACTION_RANKER_OOF_AUTOPSY_READY validation_reads=0 confirm_reads=0 fits=0"
