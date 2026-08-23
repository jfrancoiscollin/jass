#!/usr/bin/env bash
# Read-only terminal audit of the 1538 catastrophic decision-flip tail.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${SOURCE_JOB:?}"; : "${SOURCE_ATTEMPT:?}"; : "${SOURCE_CODE:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"; RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  for name in tests fetch-source auth audit; do [ -s "$W/$name.log" ] && cp "$W/$name.log" "$ART/$name.log"; done
  rm -rf "$IN"; exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-loss-first-provenance-audit-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree contract mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${READ_ONLY_PROVENANCE_AUDIT:-0}" = 1 ] && [ "${NO_NEW_EXACT_TARGETS:-0}" = 1 ] || die "audit guards missing"
[ "${NO_PATTERNEVAL_FIT:-0}" = 1 ] && [ "${NO_STRENGTH_GAMES:-0}" = 1 ] && [ "${NO_SELFPLAY:-0}" = 1 ] || die "forbidden action guards missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] && [ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"

say "experiment=CURRICULUM_ERROR_LOSS_FIRST_PROVENANCE_AUDIT source=$SOURCE_JOB/$SOURCE_ATTEMPT"
say "new_targets=0 PatternEval=0 force=0 selfplay=0 frozen=0 promotion=false"

python3 -m py_compile jobs/tools/l3_curriculum_error_loss_first_provenance_audit.py
python3 -m unittest jobs.tests.test_l3_curriculum_error_loss_first_provenance_audit \
  jobs.tests.test_l3_curriculum_error_loss_first_provenance_audit_template >"$W/tests.log" 2>&1

prefix="r2:jass-data/runs/$SOURCE_JOB/$SOURCE_ATTEMPT"
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$prefix" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=source-report.json \
  --out-dir "$IN" --report "$ART/verified-source.json" --expected-state completed >"$W/fetch-source.log" 2>&1

python3 - "$ART/verified-source.json" "$SOURCE_JOB" "$SOURCE_ATTEMPT" "$SOURCE_CODE" >"$W/auth.log" 2>&1 <<'PY_AUTH'
import json,sys
row=json.load(open(sys.argv[1])); got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha'))
want=tuple(sys.argv[2:5])
if got!=want or row.get('result_state')!='completed' or row.get('exit_code')!=0:
 raise SystemExit(f'source identity/state drift got={got} want={want}')
PY_AUTH

python3 -m jobs.tools.l3_curriculum_error_loss_first_provenance_audit \
  --source-report "$IN/source-report.json" --report "$ART/loss-first-provenance-audit.json" >"$W/audit.log" 2>&1

python3 - "$ART" "$EXPECTED_CODE_SHA" <<'PY_FINAL'
import json,re,sys
from pathlib import Path
art=Path(sys.argv[1]); code=sys.argv[2]; report=json.load(open(art/'loss-first-provenance-audit.json'))
if report.get('verdict')!='JASS_CURRICULUM_ERROR_LOSS_FIRST_PROVENANCE_AUDIT_READY' or report.get('passed') is not True:
 raise SystemExit('audit verdict drift')
for key in ('new_exact_target_computations','pattern_eval_fits','production_model_fits','strength_games','new_selfplay_games','frozen_reads'):
 if int(report.get(key,-1))!=0: raise SystemExit(f'audit accounting drift {key}')
for key in ('anchored_local_refit_authorized','production_model_authorized','strength_gate_authorized','promotion_authorized','automatic_continuation'):
 if report.get(key) is not False: raise SystemExit(f'audit authorization drift {key}')
payload={**report,'schema':'jass.curriculum_error_loss_first_provenance_audit_terminal.v1','code_sha':code}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/report['verdict']).touch(); clean=lambda value:re.sub(r'[^A-Za-z0-9.+-]+','_',str(value)).strip('_')[:180]
tail=report['loss_tail']; worst=report['worst_error_interventions'][0]
(art/f"TAIL__TOP1_{clean(round(tail['top_1_share'],6))}__TOP3_{clean(round(tail['top_3_share'],6))}__SENTINELS_{tail['sentinel_scale_loss_count']}__SHARE_{clean(round(tail['sentinel_scale_loss_share'],6))}").touch()
(art/f"WORST__PAIR_{worst['pair_id']}__POOL_{clean(worst['source_pool'])}__GAIN_{clean(round(worst['improvement_cp'],3))}__PHASE_{clean(worst['phase'])}__FEATURE_{clean(worst['dominant_feature'])}").touch()
(art/f"STATUS__{clean(report['scientific_status'])}__NEXT__{clean(report['next_stage'])}").touch()
for name in ('NEW_EXACT_TARGETS__0','PATTERNEVAL_FITS__0','PRODUCTION_MODEL_FITS__0','STRENGTH_GAMES__0','NEW_SELFPLAY__0','FROZEN_READS__0','ANCHORED_REFIT_AUTHORIZED__FALSE','PRODUCTION_MODEL_AUTHORIZED__FALSE','STRENGTH_GATE_AUTHORIZED__FALSE','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_CONTINUATION__FALSE'):
 (art/name).touch()
PY_FINAL

say "JASS_CURRICULUM_ERROR_LOSS_FIRST_PROVENANCE_AUDIT_READY new_targets=0 production_fits=0 force=0"
