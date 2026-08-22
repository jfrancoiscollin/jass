#!/usr/bin/env bash
# Read-only pre-registration of the single fixed equivariant-annular action correction.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${RANKER_SOURCE_JOB:?}"; : "${RANKER_SOURCE_ATTEMPT:?}"; : "${RANKER_SOURCE_CODE:?}"
: "${READOUT_SOURCE_JOB:?}"; : "${READOUT_SOURCE_ATTEMPT:?}"; : "${READOUT_SOURCE_CODE:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  for log in tests ranker-fetch readout-fetch preregistration; do
    [ -s "$W/$log.log" ] && cp "$W/$log.log" "$ART/$log.log"
  done
  rm -rf "$IN"; exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-action-annulus-preregistration-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${NO_FIT:-0}" = 1 ] && [ "${NO_SELFPLAY:-0}" = 1 ] && [ "${NO_STRENGTH_GAMES:-0}" = 1 ] || die "read-only guards missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] && [ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"

python3 -m py_compile jobs/tools/l3_curriculum_error_annulus_preregistration.py
python3 -m unittest jobs.tests.test_l3_curriculum_error_annulus_preregistration >"$W/tests.log" 2>&1

RANKER_ROOT="r2:jass-data/runs/$RANKER_SOURCE_JOB/$RANKER_SOURCE_ATTEMPT"
python3 jobs/tools/fetch_result_files.py --prefix "$RANKER_ROOT" \
  --file artefacts/action-ranker-screen.json=ranker-report.json \
  --out-dir "$IN" --report "$ART/verified-ranker-source.json" --expected-state completed >"$W/ranker-fetch.log" 2>&1
READOUT_ROOT="r2:jass-data/runs/$READOUT_SOURCE_JOB/$READOUT_SOURCE_ATTEMPT"
python3 jobs/tools/fetch_result_files.py --prefix "$READOUT_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=oof-autopsy.json \
  --out-dir "$IN" --report "$ART/verified-readout-source.json" --expected-state completed >"$W/readout-fetch.log" 2>&1

python3 - "$ART" "$RANKER_SOURCE_JOB" "$RANKER_SOURCE_ATTEMPT" "$RANKER_SOURCE_CODE" \
  "$READOUT_SOURCE_JOB" "$READOUT_SOURCE_ATTEMPT" "$READOUT_SOURCE_CODE" <<'PY_AUTH'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); values=sys.argv[2:]
for receipt_name,offset in (("verified-ranker-source.json",0),("verified-readout-source.json",3)):
    receipt=json.load(open(art/receipt_name)); got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'))
    want=tuple(values[offset:offset+3])
    if got!=want or receipt.get('result_state')!='completed' or receipt.get('exit_code')!=0:
        raise SystemExit(f'{receipt_name} identity/state drift got={got} want={want}')
PY_AUTH

python3 jobs/tools/l3_curriculum_error_annulus_preregistration.py \
  --ranker-report "$IN/ranker-report.json" --oof-autopsy "$IN/oof-autopsy.json" \
  --output "$ART/JASS_CONTROL_SUMMARY.json" >"$W/preregistration.log" 2>&1
python3 - "$ART" <<'PY_MARKERS'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); report=json.load(open(art/'JASS_CONTROL_SUMMARY.json'))
(art/report['verdict']).touch()
for gate,value in report['mechanistic_gates'].items():
    (art/f"GATE__{gate.upper()}__{str(value).upper()}").touch()
architecture=report.get('fixed_architecture')
if architecture:
    (art/'FIXED__PAIRED_IMAGE_D9__CANONICAL_EQUIVARIANT__ALPHA_100__ADV_25__MARGIN_GT50_LE100__CAP_75').touch()
for name,value in (
    ('VALIDATION_DECISION_PAYLOAD_READS',0),('OUTER_CONFIRM_DECISION_PAYLOAD_READS',0),
    ('DIAGNOSTIC_FITS',0),('STRENGTH_GAMES',0),('FROZEN_READS',0),
): (art/f'{name}__{value}').touch()
(art/'PROMOTION_AUTHORIZED__FALSE').touch()
PY_MARKERS
VERDICT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
say "$VERDICT architectures=1 validation_reads=0 confirm_reads=0 fits=0"
