#!/usr/bin/env bash
# Read-only decision-flip/loss-tail autopsy of the negative 1536 screen.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${TRAINING_SOURCE_JOB:?}"; : "${TRAINING_SOURCE_ATTEMPT:?}"; : "${TRAINING_SOURCE_CODE:?}"
: "${FRESH_SOURCE_JOB:?}"; : "${FRESH_SOURCE_ATTEMPT:?}"; : "${FRESH_SOURCE_CODE:?}"
: "${SUBSPACE_SOURCE_JOB:?}"; : "${SUBSPACE_SOURCE_ATTEMPT:?}"; : "${SUBSPACE_SOURCE_CODE:?}"
: "${TARGET_SOURCE_JOB:?}"; : "${TARGET_SOURCE_ATTEMPT:?}"; : "${TARGET_SOURCE_CODE:?}"
: "${BUCKET_SOURCE_JOB:?}"; : "${BUCKET_SOURCE_ATTEMPT:?}"; : "${BUCKET_SOURCE_CODE:?}"
: "${ACTION_SOURCE_JOB:?}"; : "${ACTION_SOURCE_ATTEMPT:?}"; : "${ACTION_SOURCE_CODE:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"; RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  for name in tests fetch-training fetch-fresh fetch-subspace fetch-target fetch-bucket fetch-action auth autopsy; do
    [ -s "$W/$name.log" ] && cp "$W/$name.log" "$ART/$name.log"
  done
  rm -rf "$IN"; exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-action-flip-tail-autopsy-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree contract mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${READ_ONLY_ACTION_FLIP_AUTOPSY:-0}" = 1 ] && [ "${REPLAY_1536_BIT_EXACT:-0}" = 1 ] || die "autopsy guards missing"
[ "${POSTHOC_RULES_DIAGNOSTIC_ONLY:-0}" = 1 ] && [ "${FIT_IMMUTABLE_1508_ONLY:-0}" = 1 ] || die "diagnostic scope guards missing"
[ "${NO_NEW_EXACT_TARGETS:-0}" = 1 ] && [ "${NO_SELFPLAY:-0}" = 1 ] && [ "${NO_PATTERNEVAL_FIT:-0}" = 1 ] || die "forbidden data guards missing"
[ "${NO_STRENGTH_GAMES:-0}" = 1 ] && [ "${NO_FROZEN_READ:-0}" = 1 ] && [ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"

root(){ echo "r2:jass-data/runs/$1/$2"; }
say "experiment=CURRICULUM_ERROR_ACTION_FLIP_TAIL_AUTOPSY action=$ACTION_SOURCE_JOB/$ACTION_SOURCE_ATTEMPT"
say "new_targets=0 diagnostic_base_fits=1 diagnostic_action_reproduction_fits=2 PatternEval=0 force=0 selfplay=0 frozen=0 promotion=false"

python3 -m py_compile jobs/tools/l3_curriculum_error_action_flip_tail_autopsy.py
python3 -m unittest \
  jobs.tests.test_l3_curriculum_error_action_flip_tail_autopsy \
  jobs.tests.test_l3_curriculum_error_action_margin_contrastive_screen \
  jobs.tests.test_l3_curriculum_error_fresh_tail_autopsy >"$W/tests.log" 2>&1

training_args=(); fresh_args=()
for shard in $(seq 0 15); do
  training_args+=(--file "artefacts/gate-fit-atlas-shards/shard-$shard.json=training-atlas-$shard.json")
  fresh_args+=(--file "artefacts/fresh-confirmation-atlas-shards/shard-$shard.json=fresh-atlas-$shard.json")
done
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$(root "$TRAINING_SOURCE_JOB" "$TRAINING_SOURCE_ATTEMPT")" \
  --file artefacts/trace-residual-training.json=training-report.json \
  --file artefacts/trace-residual-model.json=failed-model.json \
  --file artefacts/gate-fit-pairs.json=training-pairs.json \
  "${training_args[@]}" --out-dir "$IN" --report "$ART/verified-training-source.json" --expected-state completed >"$W/fetch-training.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$(root "$FRESH_SOURCE_JOB" "$FRESH_SOURCE_ATTEMPT")" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=fresh-summary.json \
  --file artefacts/fresh-powered-confirmation.json=fresh-report.json \
  --file artefacts/fresh-confirmation-pairs.json=fresh-pairs.json \
  --file artefacts/fresh-target-cache.json=fresh-target-cache.json \
  "${fresh_args[@]}" --out-dir "$IN" --report "$ART/verified-fresh-source.json" --expected-state completed >"$W/fetch-fresh.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$(root "$SUBSPACE_SOURCE_JOB" "$SUBSPACE_SOURCE_ATTEMPT")" \
  --file artefacts/stable-subspace-screen.json=subspace-report.json \
  --out-dir "$IN" --report "$ART/verified-subspace-source.json" --expected-state completed >"$W/fetch-subspace.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$(root "$TARGET_SOURCE_JOB" "$TARGET_SOURCE_ATTEMPT")" \
  --file artefacts/target-specificity-autopsy.json=target-report.json \
  --out-dir "$IN" --report "$ART/verified-target-source.json" --expected-state completed >"$W/fetch-target.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$(root "$BUCKET_SOURCE_JOB" "$BUCKET_SOURCE_ATTEMPT")" \
  --file artefacts/bucket-treatment-atlas.json=bucket-report.json \
  --out-dir "$IN" --report "$ART/verified-bucket-source.json" --expected-state completed >"$W/fetch-bucket.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$(root "$ACTION_SOURCE_JOB" "$ACTION_SOURCE_ATTEMPT")" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=action-report.json \
  --out-dir "$IN" --report "$ART/verified-action-source.json" --expected-state completed >"$W/fetch-action.log" 2>&1

python3 - "$ART" \
  "$TRAINING_SOURCE_JOB" "$TRAINING_SOURCE_ATTEMPT" "$TRAINING_SOURCE_CODE" \
  "$FRESH_SOURCE_JOB" "$FRESH_SOURCE_ATTEMPT" "$FRESH_SOURCE_CODE" \
  "$SUBSPACE_SOURCE_JOB" "$SUBSPACE_SOURCE_ATTEMPT" "$SUBSPACE_SOURCE_CODE" \
  "$TARGET_SOURCE_JOB" "$TARGET_SOURCE_ATTEMPT" "$TARGET_SOURCE_CODE" \
  "$BUCKET_SOURCE_JOB" "$BUCKET_SOURCE_ATTEMPT" "$BUCKET_SOURCE_CODE" \
  "$ACTION_SOURCE_JOB" "$ACTION_SOURCE_ATTEMPT" "$ACTION_SOURCE_CODE" >"$W/auth.log" 2>&1 <<'PY_AUTH'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); wants=[tuple(sys.argv[i:i+3]) for i in (2,5,8,11,14,17)]
names=('verified-training-source.json','verified-fresh-source.json','verified-subspace-source.json','verified-target-source.json','verified-bucket-source.json','verified-action-source.json')
for name,want in zip(names,wants):
 row=json.load(open(art/name)); got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha'))
 if got!=want or row.get('result_state')!='completed' or row.get('exit_code')!=0: raise SystemExit(f'{name} identity/state drift got={got} want={want}')
PY_AUTH

training_shards=(); fresh_shards=()
for shard in $(seq 0 15); do
  training_shards+=(--training-shard "$IN/training-atlas-$shard.json")
  fresh_shards+=(--fresh-shard "$IN/fresh-atlas-$shard.json")
done
python3 -m jobs.tools.l3_curriculum_error_action_flip_tail_autopsy \
  --training-report "$IN/training-report.json" --failed-model "$IN/failed-model.json" \
  --training-pairs "$IN/training-pairs.json" "${training_shards[@]}" \
  --fresh-summary "$IN/fresh-summary.json" --fresh-report "$IN/fresh-report.json" \
  --fresh-pairs "$IN/fresh-pairs.json" "${fresh_shards[@]}" \
  --target-cache "$IN/fresh-target-cache.json" --subspace-report "$IN/subspace-report.json" \
  --target-report "$IN/target-report.json" --bucket-report "$IN/bucket-report.json" \
  --action-report "$IN/action-report.json" --report "$ART/action-flip-tail-autopsy.json" >"$W/autopsy.log" 2>&1

python3 - "$ART" "$EXPECTED_CODE_SHA" <<'PY_FINAL'
import json,re,sys
from pathlib import Path
art=Path(sys.argv[1]); code=sys.argv[2]; report=json.load(open(art/'action-flip-tail-autopsy.json'))
if report.get('verdict')!='JASS_CURRICULUM_ERROR_ACTION_FLIP_TAIL_AUTOPSY_READY' or report.get('passed') is not True: raise SystemExit('autopsy verdict drift')
expected={'new_exact_target_computations':0,'diagnostic_base_residual_fits_on_immutable_1508':1,'diagnostic_action_margin_reproduction_fits':2,'pattern_eval_fits':0,'production_model_fits':0,'strength_games':0,'new_selfplay_games':0,'frozen_reads':0}
for key,value in expected.items():
 if int(report.get(key,-1))!=value: raise SystemExit(f'autopsy accounting drift {key}')
for key in ('anchored_local_refit_authorized','production_model_authorized','strength_gate_authorized','promotion_authorized','automatic_continuation'):
 if report.get(key) is not False: raise SystemExit(f'autopsy authorization drift {key}')
payload={**report,'schema':'jass.curriculum_error_action_flip_tail_autopsy_terminal.v1','code_sha':code}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/report['verdict']).touch(); clean=lambda value:re.sub(r'[^A-Za-z0-9.+-]+','_',str(value)).strip('_')[:180]
counts=report['counts']; loss=report['loss_concentration']; rules=report['descriptively_stable_counterfactuals']
(art/f"COUNTS__ERRINT_{counts['error_interventions']}__ERRPOS_{counts['error_positive_interventions']}__ERRNEG_{counts['error_negative_interventions']}__CTRLINT_{counts['control_interventions']}").touch()
(art/f"LOSS__TOTAL_{clean(round(loss.get('total_loss_cp',0),3))}__NEG_{loss.get('negative_interventions',0)}__TOP1_{clean(round(loss.get('top_1_share',0),6))}__TOP3_{clean(round(loss.get('top_3_share',0),6))}").touch()
(art/f"DESCRIPTIVE_RULES__{len(rules)}__NEXT__{clean(report['next_stage'])}").touch()
if rules:
 best=rules[0]; (art/f"BEST_POSTHOC__{clean(best['flag'])}__MINPOOL_{clean(round(best['minimum_pool_paired_mean_cp'],3))}__POSRATE_{clean(round(best['retained_error_positive_realization_rate'],6))}").touch()
negative=report['feature_attribution']['negative_error_interventions']
if negative:
 dominant=max(negative,key=lambda row:(row['mean_absolute_cp'],row['name']))
 (art/f"NEGATIVE_WEIGHT_AXIS__{clean(dominant['name'])}__MEANABS_{clean(round(dominant['mean_absolute_cp'],6))}__MEANSIGNED_{clean(round(dominant['mean_signed_cp'],6))}").touch()
for name in ('NEW_EXACT_TARGETS__0','DIAGNOSTIC_BASE_FITS__1','DIAGNOSTIC_ACTION_REPRODUCTION_FITS__2','PATTERNEVAL_FITS__0','PRODUCTION_MODEL_FITS__0','STRENGTH_GAMES__0','NEW_SELFPLAY__0','FROZEN_READS__0','ANCHORED_REFIT_AUTHORIZED__FALSE','PRODUCTION_MODEL_AUTHORIZED__FALSE','STRENGTH_GATE_AUTHORIZED__FALSE','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_CONTINUATION__FALSE','FRESH_1524_REUSE_FOR_CONFIRMATION__FORBIDDEN'): (art/name).touch()
PY_FINAL

say "JASS_CURRICULUM_ERROR_ACTION_FLIP_TAIL_AUTOPSY_READY new_targets=0 production_fits=0 force=0"
