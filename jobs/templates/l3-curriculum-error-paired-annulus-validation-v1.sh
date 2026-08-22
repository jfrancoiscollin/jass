#!/usr/bin/env bash
# One-shot 31-pair validation of the immutable paired-image annular residual.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${RANKER_SOURCE_JOB:?}"; : "${RANKER_SOURCE_ATTEMPT:?}"; : "${RANKER_SOURCE_CODE:?}"
: "${PREREG_SOURCE_JOB:?}"; : "${PREREG_SOURCE_ATTEMPT:?}"; : "${PREREG_SOURCE_CODE:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  for log in tests ranker-fetch prereg-fetch validation; do
    [ -s "$W/$log.log" ] && cp "$W/$log.log" "$ART/$log.log"
  done
  rm -rf "$IN"; exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-paired-annulus-validation-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${ONE_SHOT_VALIDATION_APPROVED:-0}" = 1 ] && [ "${OUTER_CONFIRM_SEALED:-0}" = 1 ] || die "sealed validation contract missing"
[ "${NO_SELFPLAY:-0}" = 1 ] && [ "${NO_PATTERNEVAL_FIT:-0}" = 1 ] && [ "${NO_STRENGTH_GAMES:-0}" = 1 ] || die "forbidden-action guards missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] && [ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"

python3 -m py_compile jobs/tools/l3_curriculum_error_paired_annulus_validation.py
python3 -m unittest jobs.tests.test_l3_curriculum_error_paired_annulus_validation >"$W/tests.log" 2>&1

RANKER_ROOT="r2:jass-data/runs/$RANKER_SOURCE_JOB/$RANKER_SOURCE_ATTEMPT"
RANKER_FILES=(
  --file artefacts/action-ranker-screen.json=ranker-report.json
  --file artefacts/matched-pairs.json=matched-pairs.json
)
for shard in $(seq 0 15); do
  RANKER_FILES+=(--file "artefacts/atlas-shards/shard-$shard.json=atlas-shard-$shard.json")
done
python3 jobs/tools/fetch_result_files.py --prefix "$RANKER_ROOT" \
  "${RANKER_FILES[@]}" --out-dir "$IN" --report "$ART/verified-ranker-source.json" \
  --expected-state completed >"$W/ranker-fetch.log" 2>&1

PREREG_ROOT="r2:jass-data/runs/$PREREG_SOURCE_JOB/$PREREG_SOURCE_ATTEMPT"
python3 jobs/tools/fetch_result_files.py --prefix "$PREREG_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=preregistration.json \
  --out-dir "$IN" --report "$ART/verified-prereg-source.json" \
  --expected-state completed >"$W/prereg-fetch.log" 2>&1

python3 - "$ART" "$RANKER_SOURCE_JOB" "$RANKER_SOURCE_ATTEMPT" "$RANKER_SOURCE_CODE" \
  "$PREREG_SOURCE_JOB" "$PREREG_SOURCE_ATTEMPT" "$PREREG_SOURCE_CODE" <<'PY_AUTH'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); values=sys.argv[2:]
for receipt_name,offset in (("verified-ranker-source.json",0),("verified-prereg-source.json",3)):
    receipt=json.load(open(art/receipt_name)); got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'))
    want=tuple(values[offset:offset+3])
    if got!=want or receipt.get('result_state')!='completed' or receipt.get('exit_code')!=0:
        raise SystemExit(f'{receipt_name} identity/state drift got={got} want={want}')
PY_AUTH

ATLAS_ARGS=(); for shard in $(seq 0 15); do ATLAS_ARGS+=(--atlas-shard "$IN/atlas-shard-$shard.json"); done
python3 jobs/tools/l3_curriculum_error_paired_annulus_validation.py \
  --ranker-report "$IN/ranker-report.json" --preregistration "$IN/preregistration.json" \
  --pairs "$IN/matched-pairs.json" "${ATLAS_ARGS[@]}" \
  --report "$ART/paired-annulus-validation.json" --model "$ART/paired-annulus-validation-model.json" \
  >"$W/validation.log" 2>&1
cp "$ART/paired-annulus-validation.json" "$ART/JASS_CONTROL_SUMMARY.json"

python3 - "$ART" <<'PY_MARKERS'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); report=json.load(open(art/'JASS_CONTROL_SUMMARY.json'))
(art/report['verdict']).touch()
for gate,value in report['validation_gates'].items():
    (art/f"GATE__{gate.upper()}__{str(value).upper()}").touch()
m=report['validation_metrics']; sham=report['sham']
(art/f"OOS__ERROR_ANCHOR_{m['error_aligned_vs_anchor']['mean']}__PAIRED_ANCHOR_{m['paired_error_minus_control_vs_anchor']['mean']}__ERROR_ZERO_{m['error_aligned_vs_zero']['mean']}__PAIRED_ZERO_{m['paired_error_minus_control_vs_zero']['mean']}").touch()
(art/f"CALIBRATION__N_{m['error_calibration']['n']}__POSRATE_{m['error_calibration']['positive_realization_rate']}__BIAS_{m['error_calibration']['mean_bias_realized_minus_predicted_cp']}").touch()
(art/f"SYMMETRY__ANCHOR_{m['error_anchor_symmetry']}__ZERO_{m['error_zero_symmetry']}__ALIGNED_{m['error_aligned_symmetry']}").touch()
(art/f"SHAM__N_{sham['replicates']}__REAL_{sham['real_paired_residual_vs_zero_mean_cp']}__Q95_{sham['sham_paired_residual_vs_zero_q95_cp']}").touch()
(art/'INNER_VALIDATION_DECISION_PAYLOAD_READS__31').touch(); (art/'OUTER_CONFIRM_DECISION_PAYLOAD_READS__0').touch()
(art/'DIAGNOSTIC_RESIDUAL_FITS__101').touch(); (art/'PATTERNEVAL_FITS__0').touch(); (art/'STRENGTH_GAMES__0').touch()
(art/'FROZEN_READS__0').touch(); (art/'PROMOTION_AUTHORIZED__FALSE').touch()
PY_MARKERS
VERDICT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
say "$VERDICT validation_reads=31 confirm_reads=0 diagnostic_fits=101 force=0"
