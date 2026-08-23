#!/usr/bin/env bash
# Seal the anchored local-refit OOS campaign before any OOS game or label.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${JOINT_SOURCE_JOB:?}"; : "${JOINT_SOURCE_ATTEMPT:?}"; : "${JOINT_SOURCE_CODE:?}"
: "${FIT_SOURCE_JOB:?}"; : "${FIT_SOURCE_ATTEMPT:?}"; : "${FIT_SOURCE_CODE:?}"
: "${OOS_EXCLUSION_SOURCES:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$IN" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-anchored-local-refit-oos-availability-preregistration-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree contract mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "${TARGET_FREE_PREREGISTRATION_ONLY:-0}" = 1 ] && [ "${NO_OOS_GAME:-0}" = 1 ] && [ "${NO_OOS_LABEL:-0}" = 1 ] || die "OOS sealing guards missing"
[ "${NO_FIT:-0}" = 1 ] && [ "${NO_STRENGTH_GAMES:-0}" = 1 ] && [ "${NO_FROZEN_READ:-0}" = 1 ] || die "forbidden compute guards missing"
[ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"

python3 -m py_compile jobs/tools/l3_curriculum_error_anchored_local_refit_oos_availability_preregistration.py
python3 -m unittest \
  jobs.tests.test_l3_curriculum_error_anchored_local_refit_oos_availability_preregistration \
  jobs.tests.test_l3_curriculum_error_anchored_local_refit_oos_availability \
  jobs.tests.test_l3_curriculum_error_anchored_local_refit_oos_campaign >"$W/tests.log" 2>&1

JOINT_ROOT="r2:jass-data/runs/$JOINT_SOURCE_JOB/$JOINT_SOURCE_ATTEMPT"
FIT_ROOT="r2:jass-data/runs/$FIT_SOURCE_JOB/$FIT_SOURCE_ATTEMPT"
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$JOINT_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=joint.json \
  --out-dir "$IN" --report "$ART/verified-joint.json" --expected-state completed >"$W/fetch-joint.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$FIT_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=fit-report.json \
  --file artefacts/anchored-local-residual-model.json=fit-model.json \
  --out-dir "$IN" --report "$ART/verified-fit.json" --expected-state completed >"$W/fetch-fit.log" 2>&1

exclude_args=(); exclusion_count=0
while IFS='|' read -r role job attempt code; do
  [ -n "${role:-}" ] || continue
  exclusion_count=$((exclusion_count+1))
  root="r2:jass-data/runs/$job/$attempt"
  timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$root" \
    --file artefacts/JASS_CONTROL_SUMMARY.json="$role-summary.json" \
    --out-dir "$IN" --report "$ART/verified-exclusion-$role.json" --expected-state completed \
    >"$W/fetch-exclusion-$role.log" 2>&1
  python3 - "$ART/verified-exclusion-$role.json" "$job" "$attempt" "$code" <<'PY_EXCLUSION'
import json,sys
row=json.load(open(sys.argv[1])); got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha')); want=tuple(sys.argv[2:5])
if got!=want or row.get('result_state')!='completed' or row.get('exit_code')!=0: raise SystemExit(f'exclusion identity/state drift got={got} want={want}')
PY_EXCLUSION
  exclude_args+=(--exclude-source "$role|$job|$attempt|$code")
done <<<"$OOS_EXCLUSION_SOURCES"
[ "$exclusion_count" -eq 6 ] || die "OOS exclusion-chain count drift"

python3 - "$ART/verified-joint.json" "$JOINT_SOURCE_JOB" "$JOINT_SOURCE_ATTEMPT" "$JOINT_SOURCE_CODE" \
  "$ART/verified-fit.json" "$FIT_SOURCE_JOB" "$FIT_SOURCE_ATTEMPT" "$FIT_SOURCE_CODE" <<'PY_AUTH'
import json,sys
for offset in (1,5):
 row=json.load(open(sys.argv[offset])); got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha')); want=tuple(sys.argv[offset+1:offset+4])
 if got!=want or row.get('result_state')!='completed' or row.get('exit_code')!=0: raise SystemExit(f'source identity/state drift got={got} want={want}')
PY_AUTH

python3 -m jobs.tools.l3_curriculum_error_anchored_local_refit_oos_availability_preregistration \
  --joint-preregistration "$IN/joint.json" --joint-job "$JOINT_SOURCE_JOB" \
  --joint-attempt "$JOINT_SOURCE_ATTEMPT" --joint-code "$JOINT_SOURCE_CODE" \
  --fit-report "$IN/fit-report.json" --fit-model "$IN/fit-model.json" \
  --fit-job "$FIT_SOURCE_JOB" --fit-attempt "$FIT_SOURCE_ATTEMPT" --fit-code "$FIT_SOURCE_CODE" \
  "${exclude_args[@]}" --output "$ART/oos-availability-preregistration.json" >"$W/preregister.log" 2>&1

python3 - "$ART/oos-availability-preregistration.json" "$ART/JASS_CONTROL_SUMMARY.json" "$EXPECTED_CODE_SHA" <<'PY_FINAL'
import json,sys
from pathlib import Path
src,out=map(Path,sys.argv[1:3]); row=json.load(open(src))
if row.get('verdict')!='JASS_CURRICULUM_ERROR_ANCHORED_LOCAL_REFIT_OOS_AVAILABILITY_PREREGISTERED' or row.get('passed') is not True: raise SystemExit('OOS availability preregistration drift')
for key in ('new_targets','oos_reads','diagnostic_fits','pattern_eval_fits','production_model_fits','strength_games','new_selfplay_games','frozen_reads'):
 if int(row.get(key,-1))!=0: raise SystemExit(f'forbidden counter drift {key}')
payload={**row,'schema':'jass.curriculum_error_anchored_local_refit_oos_availability_preregistration_terminal.v1','code_sha':sys.argv[3]}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
for name in ('JASS_CURRICULUM_ERROR_ANCHORED_LOCAL_REFIT_OOS_AVAILABILITY_PREREGISTERED','NEW_TARGETS__0','OOS_READS__0','FITS__0','STRENGTH_GAMES__0','NEW_SELFPLAY__0','FROZEN_READS__0','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_CONTINUATION__FALSE'): (out.parent/name).touch()
PY_FINAL
say "JASS_CURRICULUM_ERROR_ANCHORED_LOCAL_REFIT_OOS_AVAILABILITY_PREREGISTERED games=0 labels=0 fits=0 strength=0"
