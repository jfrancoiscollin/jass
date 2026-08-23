#!/usr/bin/env bash
# Joint no-compute preregistration after confirmation and support screens pass.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${CONFIRMATION_SOURCE_JOB:?}"; : "${CONFIRMATION_SOURCE_ATTEMPT:?}"; : "${CONFIRMATION_SOURCE_CODE:?}"
: "${SUBSPACE_SOURCE_JOB:?}"; : "${SUBSPACE_SOURCE_ATTEMPT:?}"; : "${SUBSPACE_SOURCE_CODE:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"; RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; for name in tests fetch-confirmation fetch-subspace preregister; do [ -s "$W/$name.log" ] && cp "$W/$name.log" "$ART/$name.log"; done; rm -rf "$IN"; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-anchored-local-refit-preregistration-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree contract mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${JOINT_PASS_REQUIRED:-0}" = 1 ] && [ "${NO_OOS_READ:-0}" = 1 ] && [ "${NO_NEW_TARGETS:-0}" = 1 ] || die "sealed preregistration guards missing"
[ "${NO_FIT:-0}" = 1 ] && [ "${NO_SELFPLAY:-0}" = 1 ] && [ "${NO_STRENGTH_GAMES:-0}" = 1 ] || die "compute guards missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] && [ "${NO_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"
CONFIRMATION_ROOT="r2:jass-data/runs/$CONFIRMATION_SOURCE_JOB/$CONFIRMATION_SOURCE_ATTEMPT"
SUBSPACE_ROOT="r2:jass-data/runs/$SUBSPACE_SOURCE_JOB/$SUBSPACE_SOURCE_ATTEMPT"
say "experiment=CURRICULUM_ERROR_ANCHORED_LOCAL_REFIT_PREREG confirmation=$CONFIRMATION_SOURCE_JOB subspace=$SUBSPACE_SOURCE_JOB"
say "oos_reads=0 targets=0 fits=0 selfplay=0 force=0 frozen=0 promotion=false"

python3 -m py_compile jobs/tools/l3_curriculum_error_anchored_local_refit_preregistration.py
python3 -m unittest \
  jobs.tests.test_l3_curriculum_error_anchored_local_refit_preregistration \
  jobs.tests.test_l3_curriculum_error_anchored_local_refit_preregistration_template \
  >"$W/tests.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CONFIRMATION_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=confirmation.json \
  --out-dir "$IN" --report "$ART/verified-confirmation-source.json" --expected-state completed \
  >"$W/fetch-confirmation.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$SUBSPACE_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=subspace.json \
  --out-dir "$IN" --report "$ART/verified-subspace-source.json" --expected-state completed \
  >"$W/fetch-subspace.log" 2>&1
python3 - "$ART" "$CONFIRMATION_SOURCE_JOB" "$CONFIRMATION_SOURCE_ATTEMPT" "$CONFIRMATION_SOURCE_CODE" "$SUBSPACE_SOURCE_JOB" "$SUBSPACE_SOURCE_ATTEMPT" "$SUBSPACE_SOURCE_CODE" <<'PY_AUTH'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); confirmation=tuple(sys.argv[2:5]); subspace=tuple(sys.argv[5:8])
for name,want in (('verified-confirmation-source.json',confirmation),('verified-subspace-source.json',subspace)):
 receipt=json.load(open(art/name)); got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'))
 if got!=want or receipt.get('result_state')!='completed' or receipt.get('exit_code')!=0: raise SystemExit(f'{name} identity/state drift got={got} want={want}')
PY_AUTH
python3 -m jobs.tools.l3_curriculum_error_anchored_local_refit_preregistration \
  --confirmation "$IN/confirmation.json" \
  --confirmation-job "$CONFIRMATION_SOURCE_JOB" --confirmation-attempt "$CONFIRMATION_SOURCE_ATTEMPT" --confirmation-code "$CONFIRMATION_SOURCE_CODE" \
  --subspace "$IN/subspace.json" \
  --subspace-job "$SUBSPACE_SOURCE_JOB" --subspace-attempt "$SUBSPACE_SOURCE_ATTEMPT" --subspace-code "$SUBSPACE_SOURCE_CODE" \
  --output "$ART/anchored-local-refit-preregistration.json" >"$W/preregister.log" 2>&1
python3 - "$ART" "$EXPECTED_CODE_SHA" <<'PY_FINAL'
import json,re,sys
from pathlib import Path
art=Path(sys.argv[1]); code=sys.argv[2]; report=json.load(open(art/'anchored-local-refit-preregistration.json'))
if report.get('verdict')!='JASS_CURRICULUM_ERROR_ANCHORED_LOCAL_REFIT_PREREGISTERED' or report.get('passed') is not True: raise SystemExit('preregistration verdict drift')
expected={'new_targets':0,'oos_reads':0,'diagnostic_fits':0,'pattern_eval_fits':0,'production_model_fits':0,'strength_games':0,'new_selfplay_games':0,'frozen_reads':0}
for key,value in expected.items():
 if report.get(key)!=value: raise SystemExit(f'forbidden counter drift {key}')
if report.get('anchored_local_refit_authorized') is not True: raise SystemExit('anchored refit authorization missing')
for key in ('oos_campaign_authorized','strength_gate_authorized','promotion_authorized','automatic_continuation'):
 if report.get(key) is not False: raise SystemExit(f'authorization drift {key}')
payload={**report,'schema':'jass.curriculum_error_anchored_local_refit_preregistration_terminal.v1','code_sha':code}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n'); (art/report['verdict']).touch()
clean=lambda value: re.sub(r'[^A-Za-z0-9.+-]+','_',str(value)).strip('_')
(art/f"SUPPORT__N_{report['support']['feature_count']}__HASH_{report['support']['support_sha256'][:16]}").touch()
(art/f"PROTOCOL__{report['protocol_sha256']}").touch()
for name in ('NEW_TARGETS__0','OOS_READS__0','DIAGNOSTIC_FITS__0','PATTERNEVAL_FITS__0','PRODUCTION_MODEL_FITS__0','STRENGTH_GAMES__0','NEW_SELFPLAY__0','FROZEN_READS__0','ANCHORED_LOCAL_REFIT_AUTHORIZED__TRUE','OOS_CAMPAIGN_AUTHORIZED__FALSE','STRENGTH_GATE_AUTHORIZED__FALSE','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_CONTINUATION__FALSE'): (art/name).touch()
PY_FINAL
say "JASS_CURRICULUM_ERROR_ANCHORED_LOCAL_REFIT_PREREGISTERED oos_reads=0 fits=0 strength=0"
