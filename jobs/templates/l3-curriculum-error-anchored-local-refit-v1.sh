#!/usr/bin/env bash
# Single support-limited residual fit; no OOS read and no strength game.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${PREREG_SOURCE_JOB:?}"; : "${PREREG_SOURCE_ATTEMPT:?}"; : "${PREREG_SOURCE_CODE:?}"
: "${TRAINING_SOURCE_JOB:?}"; : "${TRAINING_SOURCE_ATTEMPT:?}"; : "${TRAINING_SOURCE_CODE:?}"
: "${CONFIRMATION_SOURCE_JOB:?}"; : "${CONFIRMATION_SOURCE_ATTEMPT:?}"; : "${CONFIRMATION_SOURCE_CODE:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"; RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; for name in tests fetch-prereg fetch-training fetch-confirmation fit; do [ -s "$W/$name.log" ] && cp "$W/$name.log" "$ART/$name.log"; done; rm -rf "$IN"; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-anchored-local-refit-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree contract mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${PREREGISTERED_SINGLE_FIT:-0}" = 1 ] && [ "${CONFIRMED_600_TRAINING_ONLY:-0}" = 1 ] || die "fit authorization guards missing"
[ "${NO_OOS_READ:-0}" = 1 ] && [ "${NO_NEW_TARGETS:-0}" = 1 ] && [ "${NO_HYPERPARAMETER_SEARCH:-0}" = 1 ] || die "sealed fit guards missing"
[ "${PATTERNEVAL_BYTE_IDENTICAL:-0}" = 1 ] && [ "${OUTSIDE_SUPPORT_BYTE_IDENTICAL:-0}" = 1 ] || die "anchor guards missing"
[ "${NO_SELFPLAY:-0}" = 1 ] && [ "${NO_STRENGTH_GAMES:-0}" = 1 ] && [ "${NO_FROZEN_READ:-0}" = 1 ] || die "compute guards missing"
[ "${NO_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"
PREREG_ROOT="r2:jass-data/runs/$PREREG_SOURCE_JOB/$PREREG_SOURCE_ATTEMPT"
TRAINING_ROOT="r2:jass-data/runs/$TRAINING_SOURCE_JOB/$TRAINING_SOURCE_ATTEMPT"
CONFIRMATION_ROOT="r2:jass-data/runs/$CONFIRMATION_SOURCE_JOB/$CONFIRMATION_SOURCE_ATTEMPT"
say "experiment=CURRICULUM_ERROR_ANCHORED_LOCAL_REFIT prereg=$PREREG_SOURCE_JOB confirmation=$CONFIRMATION_SOURCE_JOB"
say "candidate_models=1 PatternEval=0 oos_reads=0 targets=0 selfplay=0 force=0 frozen=0 promotion=false"

python3 -m py_compile jobs/tools/l3_curriculum_error_anchored_local_refit.py
python3 -m unittest jobs.tests.test_l3_curriculum_error_anchored_local_refit \
  jobs.tests.test_l3_curriculum_error_anchored_local_refit_template \
  jobs.tests.test_l3_curriculum_error_anchored_local_refit_preregistration \
  >"$W/tests.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$PREREG_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=preregistration.json \
  --out-dir "$IN" --report "$ART/verified-preregistration.json" --expected-state completed \
  >"$W/fetch-prereg.log" 2>&1
training_args=(); for shard in $(seq 0 15); do training_args+=(--file "artefacts/gate-fit-atlas-shards/shard-$shard.json=historical-shard-$shard.json"); done
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$TRAINING_ROOT" \
  --file artefacts/gate-fit-pairs.json=historical-pairs.json \
  "${training_args[@]}" --out-dir "$IN" --report "$ART/verified-training-source.json" --expected-state completed \
  >"$W/fetch-training.log" 2>&1
confirmation_args=(); for shard in $(seq 0 15); do confirmation_args+=(--file "artefacts/fresh-confirmation-atlas-shards/shard-$shard.json=confirmed-shard-$shard.json"); done
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CONFIRMATION_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=confirmation-summary.json \
  --file artefacts/fresh-confirmation-pairs.json=confirmed-pairs.json \
  "${confirmation_args[@]}" --out-dir "$IN" --report "$ART/verified-confirmation-source.json" --expected-state completed \
  >"$W/fetch-confirmation.log" 2>&1
python3 - "$ART" "$IN" "$PREREG_SOURCE_JOB" "$PREREG_SOURCE_ATTEMPT" "$PREREG_SOURCE_CODE" "$TRAINING_SOURCE_JOB" "$TRAINING_SOURCE_ATTEMPT" "$TRAINING_SOURCE_CODE" "$CONFIRMATION_SOURCE_JOB" "$CONFIRMATION_SOURCE_ATTEMPT" "$CONFIRMATION_SOURCE_CODE" <<'PY_AUTH'
import json,sys
from pathlib import Path
art,src=map(Path,sys.argv[1:3]); identities=[tuple(sys.argv[i:i+3]) for i in (3,6,9)]
for name,want in zip(('verified-preregistration.json','verified-training-source.json','verified-confirmation-source.json'),identities,strict=True):
 receipt=json.load(open(art/name)); got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'))
 if got!=want or receipt.get('result_state')!='completed' or receipt.get('exit_code')!=0: raise SystemExit(f'{name} identity/state drift got={got} want={want}')
confirmation=json.load(open(src/'confirmation-summary.json'))
if confirmation.get('verdict')!='JASS_CURRICULUM_ERROR_ENDGAME_ABSTENTION_CONFIRMATION_READY' or confirmation.get('passed') is not True: raise SystemExit('confirmation source verdict drift')
PY_AUTH
historical_args=(); confirmed_args=()
for shard in $(seq 0 15); do historical_args+=(--historical-shard "$IN/historical-shard-$shard.json"); confirmed_args+=(--confirmed-shard "$IN/confirmed-shard-$shard.json"); done
python3 -m jobs.tools.l3_curriculum_error_anchored_local_refit \
  --preregistration "$IN/preregistration.json" \
  --historical-pairs "$IN/historical-pairs.json" "${historical_args[@]}" \
  --confirmed-pairs "$IN/confirmed-pairs.json" "${confirmed_args[@]}" \
  --report "$ART/anchored-local-refit.json" --model "$ART/anchored-local-residual-model.json" \
  >"$W/fit.log" 2>&1
python3 - "$ART" "$EXPECTED_CODE_SHA" <<'PY_FINAL'
import json,re,sys
from pathlib import Path
art=Path(sys.argv[1]); code=sys.argv[2]; report=json.load(open(art/'anchored-local-refit.json')); model=json.load(open(art/'anchored-local-residual-model.json'))
if report.get('verdict') not in {'JASS_CURRICULUM_ERROR_ANCHORED_LOCAL_REFIT_READY','JASS_CURRICULUM_ERROR_ANCHORED_LOCAL_REFIT_NOT_ESTABLISHED'}: raise SystemExit('fit verdict drift')
expected={'model_candidates_fit':1,'residual_production_fits':1,'pattern_eval_fits':0,'oos_reads':0,'strength_games':0,'new_selfplay_games':0,'frozen_reads':0}
for key,value in expected.items():
 if report.get(key)!=value: raise SystemExit(f'fit counter drift {key}')
if report.get('oos_labels_used_for_fit') is not False or report.get('fresh_confirmation_labels_used_for_fit') is not True: raise SystemExit('fit population drift')
if model.get('authorized_for_strength') is not False or model.get('authorized_for_promotion') is not False: raise SystemExit('model authorization drift')
if report.get('strength_gate_authorized') is not False or report.get('promotion_authorized') is not False or report.get('automatic_continuation') is not False: raise SystemExit('terminal authorization drift')
payload={**report,'schema':'jass.curriculum_error_anchored_local_refit_terminal.v1','code_sha':code}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n'); (art/report['verdict']).touch()
clean=lambda value: re.sub(r'[^A-Za-z0-9.+-]+','_',str(value)).strip('_')
(art/f"MODEL__{report['model_sha256']}").touch(); (art/f"SUPPORT__{report['support']['support_sha256']}").touch()
for gate,value in sorted(report['gates'].items()): (art/f"GATE__{gate.upper()}__{str(value).upper()}").touch()
for name in ('MODEL_CANDIDATES_FIT__1','RESIDUAL_PRODUCTION_FITS__1','PATTERNEVAL_FITS__0','OOS_READS__0','STRENGTH_GAMES__0','NEW_SELFPLAY__0','FROZEN_READS__0','STRENGTH_GATE_AUTHORIZED__FALSE','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_CONTINUATION__FALSE'): (art/name).touch()
PY_FINAL
VERDICT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
say "$VERDICT candidate_models=1 PatternEval=0 oos=0 strength=0"
