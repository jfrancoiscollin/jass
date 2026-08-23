#!/usr/bin/env bash
# Read-only freeze of one ridge hypothesis for a fresh 300-pair confirmation.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${SCREEN_SOURCE_JOB:?}"; : "${SCREEN_SOURCE_ATTEMPT:?}"; : "${SCREEN_SOURCE_CODE:?}"
: "${AUDIT_SOURCE_JOB:?}"; : "${AUDIT_SOURCE_ATTEMPT:?}"; : "${AUDIT_SOURCE_CODE:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"; RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; for log in tests fetch-screen fetch-audit preregistration; do [ -s "$W/$log.log" ] && cp "$W/$log.log" "$ART/$log.log"; done; rm -rf "$IN"; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-residual-power-extension-preregistration-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree contract mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${NO_FIT:-0}" = 1 ] && [ "${NO_NEW_TARGETS:-0}" = 1 ] && [ "${NO_HOLDOUT_READ:-0}" = 1 ] || die "read-only guards missing"
[ "${NO_SELFPLAY:-0}" = 1 ] && [ "${NO_PATTERNEVAL_FIT:-0}" = 1 ] && [ "${NO_STRENGTH_GAMES:-0}" = 1 ] || die "forbidden-compute guards missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] && [ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"
python3 -m py_compile jobs/tools/l3_curriculum_error_residual_power_extension_preregistration.py
python3 -m unittest \
  jobs.tests.test_l3_curriculum_error_residual_power_extension_preregistration \
  jobs.tests.test_l3_curriculum_error_residual_power_extension_preregistration_template \
  >"$W/tests.log" 2>&1
timeout 1200s python3 jobs/tools/fetch_result_files.py \
  --prefix "r2:jass-data/runs/$SCREEN_SOURCE_JOB/$SCREEN_SOURCE_ATTEMPT" \
  --file artefacts/ridge-path-screen.json=screen.json \
  --out-dir "$IN" --report "$ART/verified-screen-source.json" \
  --expected-state completed >"$W/fetch-screen.log" 2>&1
timeout 1200s python3 jobs/tools/fetch_result_files.py \
  --prefix "r2:jass-data/runs/$AUDIT_SOURCE_JOB/$AUDIT_SOURCE_ATTEMPT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=audit.json \
  --out-dir "$IN" --report "$ART/verified-audit-source.json" \
  --expected-state completed >"$W/fetch-audit.log" 2>&1
python3 - "$ART" "$SCREEN_SOURCE_JOB" "$SCREEN_SOURCE_ATTEMPT" "$SCREEN_SOURCE_CODE" "$AUDIT_SOURCE_JOB" "$AUDIT_SOURCE_ATTEMPT" "$AUDIT_SOURCE_CODE" <<'PY_AUTH'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); values=sys.argv[2:]
for index,name in enumerate(('verified-screen-source.json','verified-audit-source.json')):
 receipt=json.load(open(art/name)); want=tuple(values[index*3:index*3+3]); got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'))
 if got!=want or receipt.get('result_state')!='completed' or receipt.get('exit_code')!=0: raise SystemExit(f'{name} identity/state drift got={got} want={want}')
PY_AUTH
python3 -m jobs.tools.l3_curriculum_error_residual_power_extension_preregistration \
  --screen "$IN/screen.json" --screen-job "$SCREEN_SOURCE_JOB" \
  --screen-attempt "$SCREEN_SOURCE_ATTEMPT" --screen-code "$SCREEN_SOURCE_CODE" \
  --audit "$IN/audit.json" --audit-job "$AUDIT_SOURCE_JOB" \
  --audit-attempt "$AUDIT_SOURCE_ATTEMPT" --audit-code "$AUDIT_SOURCE_CODE" \
  --output "$ART/JASS_CONTROL_SUMMARY.json" >"$W/preregistration.log" 2>&1
python3 - "$ART" <<'PY_MARKERS'
import json,re,sys
from pathlib import Path
art=Path(sys.argv[1]); report=json.load(open(art/'JASS_CONTROL_SUMMARY.json')); (art/report['verdict']).touch()
h=report['selected_hypothesis']; evidence=h['training_evidence']; paired=evidence['paired_error_minus_control']
clean=lambda value: re.sub(r'[^A-Za-z0-9.+-]+','_',str(value)).strip('_')
(art/f"FIXED__A_{clean(h['alpha'])}__CAP_{clean(h['cap_cp'])}__MODE_{h['mode']}__T_{clean(h['threshold_cp'])}__ERRINT_{evidence['error_interventions']}__CTLINT_{evidence['control_interventions']}__PAIRMEAN_{clean(round(paired['mean'],3))}__PAIRLO_{clean(round(paired['ci95'][0],3))}").touch()
(art/f"FRESH_PROTOCOL__PAIRS_{report['protocol']['fresh_pair_mining']['pair_count_exact']}__BOOT_{report['protocol']['fresh_confirmation']['bootstrap_samples']}__SHAMS_{report['protocol']['fresh_confirmation']['sham_replicates']}").touch()
for name in ('DISCOVERY_FAMILY_CLOSED__TRUE','NEW_TARGETS__0','HOLDOUT_READS__0','DIAGNOSTIC_FITS__0','PATTERNEVAL_FITS__0','PRODUCTION_MODEL_FITS__0','STRENGTH_GAMES__0','NEW_SELFPLAY__0','FROZEN_READS__0','FRESH_PAIR_MINING_AUTHORIZED__TRUE','FRESH_TARGET_RECONSTRUCTION_AUTHORIZED__FALSE','HISTORICAL_HOLDOUT_READ_AUTHORIZED__FALSE','PRODUCTION_RULE_AUTHORIZED__FALSE','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_CONTINUATION__FALSE'):
 (art/name).touch()
PY_MARKERS
say "JASS_CURRICULUM_ERROR_RESIDUAL_POWER_EXTENSION_PREREGISTERED hypotheses=1 pairs=300 targets=0 holdout=0"
