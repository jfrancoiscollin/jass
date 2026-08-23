#!/usr/bin/env bash
# Read-only preregistration of one endgame-abstention residual hypothesis.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${AUDIT_SOURCE_JOB:?}"; : "${AUDIT_SOURCE_ATTEMPT:?}"; : "${AUDIT_SOURCE_CODE:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"; RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; for name in tests fetch prereg; do [ -s "$W/$name.log" ] && cp "$W/$name.log" "$ART/$name.log"; done; rm -rf "$IN"; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-endgame-abstention-preregistration-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree contract mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${READ_ONLY_PREREGISTRATION:-0}" = 1 ] && [ "${ONE_HYPOTHESIS_ONLY:-0}" = 1 ] || die "preregistration guards missing"
[ "${NO_TARGETS:-0}" = 1 ] && [ "${NO_FITS:-0}" = 1 ] && [ "${NO_SELFPLAY:-0}" = 1 ] || die "read-only guards missing"
[ "${NO_STRENGTH_GAMES:-0}" = 1 ] && [ "${NO_FROZEN_READ:-0}" = 1 ] && [ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"

python3 -m py_compile jobs/tools/l3_curriculum_error_endgame_abstention_preregistration.py
python3 -m unittest jobs.tests.test_l3_curriculum_error_endgame_abstention_preregistration jobs.tests.test_l3_curriculum_error_endgame_abstention_preregistration_template >"$W/tests.log" 2>&1
ROOT="r2:jass-data/runs/$AUDIT_SOURCE_JOB/$AUDIT_SOURCE_ATTEMPT"
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=audit.json --out-dir "$IN" \
  --report "$ART/verified-audit-source.json" --expected-state completed >"$W/fetch.log" 2>&1
python3 - "$ART/verified-audit-source.json" "$AUDIT_SOURCE_JOB" "$AUDIT_SOURCE_ATTEMPT" "$AUDIT_SOURCE_CODE" <<'PY_AUTH'
import json,sys
row=json.load(open(sys.argv[1])); want=tuple(sys.argv[2:5]); got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha'))
if got!=want or row.get('result_state')!='completed' or row.get('exit_code')!=0: raise SystemExit(f'audit identity/state drift got={got} want={want}')
PY_AUTH
python3 -m jobs.tools.l3_curriculum_error_endgame_abstention_preregistration \
  --audit "$IN/audit.json" --audit-job "$AUDIT_SOURCE_JOB" \
  --audit-attempt "$AUDIT_SOURCE_ATTEMPT" --audit-code "$AUDIT_SOURCE_CODE" \
  --output "$ART/endgame-abstention-preregistration.json" >"$W/prereg.log" 2>&1
python3 - "$ART" "$EXPECTED_CODE_SHA" "$AUDIT_SOURCE_JOB" "$AUDIT_SOURCE_ATTEMPT" "$AUDIT_SOURCE_CODE" <<'PY_FINAL'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); code=sys.argv[2]; source=tuple(sys.argv[3:6]); report=json.load(open(art/'endgame-abstention-preregistration.json'))
if report.get('verdict')!='JASS_CURRICULUM_ERROR_ENDGAME_ABSTENTION_PREREGISTERED' or report.get('passed') is not True: raise SystemExit('preregistration verdict drift')
if report.get('protocol',{}).get('fresh_pair_mining',{}).get('pair_count_exact')!=600: raise SystemExit('fresh pair count drift')
if report.get('frozen_hypothesis',{}).get('phase_rule',{}).get('abstain_exact_value')!='endgame': raise SystemExit('phase rule drift')
for key in ('new_targets','fits','strength_games','new_selfplay_games','frozen_reads'):
 if int(report.get(key,-1))!=0: raise SystemExit(f'forbidden counter drift {key}')
for key in ('fresh_target_reconstruction_authorized','production_refit_authorized','strength_gate_authorized','promotion_authorized','automatic_continuation'):
 if report.get(key) is not False: raise SystemExit(f'authorization drift {key}')
payload={**report,'schema':'jass.curriculum_error_endgame_abstention_preregistration_terminal.v1','code_sha':code,'audit_source':dict(zip(('job','attempt','code_sha'),source))}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n'); (art/report['verdict']).touch()
for name in ('HYPOTHESES__1','FRESH_PAIRS__600','OPENINGS_PER_POOL__3840','SOURCE_GAMES__15360','PHASE_RULE__ABSTAIN_ENDGAME','NEW_TARGETS__0','FITS__0','STRENGTH_GAMES__0','NEW_SELFPLAY__0','FROZEN_READS__0','FRESH_TARGET_RECONSTRUCTION_AUTHORIZED__FALSE','PRODUCTION_REFIT_AUTHORIZED__FALSE','STRENGTH_GATE_AUTHORIZED__FALSE','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_CONTINUATION__FALSE'): (art/name).touch()
PY_FINAL
say "JASS_CURRICULUM_ERROR_ENDGAME_ABSTENTION_PREREGISTERED pairs=600 rule=abstain_endgame targets=0 fits=0"
