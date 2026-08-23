#!/usr/bin/env bash
# Seal the loss-first sibling-ranking campaign after 1541.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${SOURCE_JOB:?}"; : "${SOURCE_ATTEMPT:?}"; : "${SOURCE_CODE:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"; RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; for n in tests fetch-source auth prereg; do [ -s "$W/$n.log" ] && cp "$W/$n.log" "$ART/$n.log"; done; rm -rf "$IN"; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-loss-first-sibling-rank-preregistration-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree contract mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX contract mismatch"
[ "${PREREGISTRATION_ONLY:-0}" = 1 ] && [ "${NO_NEW_EXACT_TARGETS:-0}" = 1 ] && [ "${NO_PATTERNEVAL_FIT:-0}" = 1 ] || die "prereg guards missing"
[ "${NO_STRENGTH_GAMES:-0}" = 1 ] && [ "${NO_SELFPLAY:-0}" = 1 ] && [ "${NO_FROZEN_READ:-0}" = 1 ] || die "forbidden action guards missing"
[ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"
say "experiment=CURRICULUM_ERROR_LOSS_FIRST_SIBLING_RANK_PREREGISTRATION source=$SOURCE_JOB/$SOURCE_ATTEMPT"
python3 -m py_compile jobs/tools/l3_curriculum_error_loss_first_sibling_rank_preregistration.py
python3 -m unittest jobs.tests.test_l3_curriculum_error_loss_first_sibling_rank_preregistration jobs.tests.test_l3_curriculum_error_loss_first_sibling_rank_preregistration_template >"$W/tests.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "r2:jass-data/runs/$SOURCE_JOB/$SOURCE_ATTEMPT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=source-report.json --expected-state completed \
  --out-dir "$IN" --report "$ART/verified-source.json" >"$W/fetch-source.log" 2>&1
python3 - "$ART/verified-source.json" "$SOURCE_JOB" "$SOURCE_ATTEMPT" "$SOURCE_CODE" >"$W/auth.log" 2>&1 <<'PY_AUTH'
import json,sys
r=json.load(open(sys.argv[1])); got=(r.get('job_id'),r.get('attempt_id'),r.get('code_sha'),r.get('result_state'),r.get('exit_code')); want=(*sys.argv[2:5],'completed',0)
if got!=want: raise SystemExit(f'source identity/state drift got={got} want={want}')
PY_AUTH
python3 -m jobs.tools.l3_curriculum_error_loss_first_sibling_rank_preregistration --source-report "$IN/source-report.json" --report "$ART/loss-first-sibling-rank-preregistration.json" >"$W/prereg.log" 2>&1
python3 - "$ART" "$EXPECTED_CODE_SHA" <<'PY_FINAL'
import json,re,sys
from pathlib import Path
art=Path(sys.argv[1]); code=sys.argv[2]; r=json.load(open(art/'loss-first-sibling-rank-preregistration.json'))
if r.get('verdict')!='JASS_CURRICULUM_ERROR_LOSS_FIRST_SIBLING_RANK_PREREGISTERED' or r.get('passed') is not True: raise SystemExit('prereg verdict drift')
for key in ('new_exact_target_computations','pattern_eval_fits','production_model_fits','strength_games','new_selfplay_games','frozen_reads'):
 if int(r.get(key,-1))!=0: raise SystemExit(f'accounting drift {key}')
for key in ('anchored_local_refit_authorized','production_model_authorized','strength_gate_authorized','promotion_authorized','automatic_continuation'):
 if r.get(key) is not False: raise SystemExit(f'authorization drift {key}')
payload={**r,'schema':'jass.curriculum_error_loss_first_sibling_rank_preregistration_terminal.v1','code_sha':code}; (art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n'); (art/r['verdict']).touch()
clean=lambda v:re.sub(r'[^A-Za-z0-9.+-]+','_',str(v)).strip('_')[:160]
(art/f"CAMPAIGN__POOLS_2__OPENINGS_384x2__GAMES_1536__SEEDS_{r['seeds']['pool1']}_{r['seeds']['pool2']}").touch(); (art/f"TARGET__{clean(r['labels']['primary'])}__CPRAW_DIAGNOSTIC_ONLY").touch(); (art/f"NEXT__{clean(r['next_stage'])}").touch()
for name in ('NEW_EXACT_TARGETS__0','PATTERNEVAL_FITS__0','PRODUCTION_MODEL_FITS__0','STRENGTH_GAMES__0','NEW_SELFPLAY__0','FROZEN_READS__0','ANCHORED_REFIT_AUTHORIZED__FALSE','PRODUCTION_MODEL_AUTHORIZED__FALSE','STRENGTH_GATE_AUTHORIZED__FALSE','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_CONTINUATION__FALSE'): (art/name).touch()
PY_FINAL
say "JASS_CURRICULUM_ERROR_LOSS_FIRST_SIBLING_RANK_PREREGISTERED targets=0 fits=0 force=0"
