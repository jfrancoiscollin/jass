#!/usr/bin/env bash
# Read-only paired target-specificity autopsy after the certified negative 1524 gate.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${TRAINING_SOURCE_JOB:?}"; : "${TRAINING_SOURCE_ATTEMPT:?}"; : "${TRAINING_SOURCE_CODE:?}"
: "${FRESH_SOURCE_JOB:?}"; : "${FRESH_SOURCE_ATTEMPT:?}"; : "${FRESH_SOURCE_CODE:?}"
: "${SUBSPACE_SOURCE_JOB:?}"; : "${SUBSPACE_SOURCE_ATTEMPT:?}"; : "${SUBSPACE_SOURCE_CODE:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"; RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  for name in tests fetch-training fetch-fresh fetch-subspace auth autopsy; do
    [ -s "$W/$name.log" ] && cp "$W/$name.log" "$ART/$name.log"
  done
  rm -rf "$IN"; exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-target-specificity-autopsy-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree contract mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${READ_ONLY_TARGET_SPECIFICITY_AUTOPSY:-0}" = 1 ] && [ "${REPLAY_1524_BIT_EXACT:-0}" = 1 ] || die "autopsy guards missing"
[ "${FIT_IMMUTABLE_1508_ONLY:-0}" = 1 ] && [ "${DIAGNOSTIC_RESIDUAL_FIT_ALLOWED:-0}" = 1 ] || die "base fit guard missing"
[ "${DIAGNOSTIC_UPLIFT_FITS_ALLOWED:-0}" = 1 ] && [ "${UPLIFT_SUPPORT_FROM_1525_ONLY:-0}" = 1 ] || die "uplift guard missing"
[ "${NO_FIT_ON_FRESH_FOR_PRODUCTION:-0}" = 1 ] && [ "${NO_NEW_EXACT_TARGETS:-0}" = 1 ] || die "fresh isolation guards missing"
[ "${NO_SELFPLAY:-0}" = 1 ] && [ "${NO_PATTERNEVAL_FIT:-0}" = 1 ] && [ "${NO_STRENGTH_GAMES:-0}" = 1 ] || die "forbidden compute guards missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] && [ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"

TRAINING_ROOT="r2:jass-data/runs/$TRAINING_SOURCE_JOB/$TRAINING_SOURCE_ATTEMPT"
FRESH_ROOT="r2:jass-data/runs/$FRESH_SOURCE_JOB/$FRESH_SOURCE_ATTEMPT"
SUBSPACE_ROOT="r2:jass-data/runs/$SUBSPACE_SOURCE_JOB/$SUBSPACE_SOURCE_ATTEMPT"
say "experiment=CURRICULUM_ERROR_TARGET_SPECIFICITY_AUTOPSY training=$TRAINING_SOURCE_JOB/$TRAINING_SOURCE_ATTEMPT fresh=$FRESH_SOURCE_JOB/$FRESH_SOURCE_ATTEMPT support=$SUBSPACE_SOURCE_JOB/$SUBSPACE_SOURCE_ATTEMPT"
say "new_targets=0 production_fits=0 diagnostic_base_fit=1 diagnostic_uplift_fits=2003 PatternEval=0 force=0 selfplay=0 frozen=0 promotion=false"

python3 -m py_compile jobs/tools/l3_curriculum_error_target_specificity_autopsy.py
python3 -m unittest \
  jobs.tests.test_l3_curriculum_error_target_specificity_autopsy \
  jobs.tests.test_l3_curriculum_error_target_specificity_autopsy_template \
  jobs.tests.test_l3_curriculum_error_endgame_abstention_confirmation \
  jobs.tests.test_l3_curriculum_error_residual_stable_subspace_screen >"$W/tests.log" 2>&1

training_args=(); fresh_args=()
for shard in $(seq 0 15); do
  training_args+=(--file "artefacts/gate-fit-atlas-shards/shard-$shard.json=training-atlas-$shard.json")
  fresh_args+=(--file "artefacts/fresh-confirmation-atlas-shards/shard-$shard.json=fresh-atlas-$shard.json")
done
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$TRAINING_ROOT" \
  --file artefacts/trace-residual-training.json=training-report.json \
  --file artefacts/trace-residual-model.json=failed-model.json \
  --file artefacts/gate-fit-pairs.json=training-pairs.json \
  "${training_args[@]}" --out-dir "$IN" --report "$ART/verified-training-source.json" \
  --expected-state completed >"$W/fetch-training.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$FRESH_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=fresh-summary.json \
  --file artefacts/fresh-powered-confirmation.json=fresh-report.json \
  --file artefacts/fresh-confirmation-pairs.json=fresh-pairs.json \
  --file artefacts/fresh-target-cache.json=fresh-target-cache.json \
  "${fresh_args[@]}" --out-dir "$IN" --report "$ART/verified-fresh-source.json" \
  --expected-state completed >"$W/fetch-fresh.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$SUBSPACE_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=subspace-summary.json \
  --file artefacts/stable-subspace-screen.json=subspace-report.json \
  --out-dir "$IN" --report "$ART/verified-subspace-source.json" \
  --expected-state completed >"$W/fetch-subspace.log" 2>&1

python3 - "$ART" "$IN" \
  "$TRAINING_SOURCE_JOB" "$TRAINING_SOURCE_ATTEMPT" "$TRAINING_SOURCE_CODE" \
  "$FRESH_SOURCE_JOB" "$FRESH_SOURCE_ATTEMPT" "$FRESH_SOURCE_CODE" \
  "$SUBSPACE_SOURCE_JOB" "$SUBSPACE_SOURCE_ATTEMPT" "$SUBSPACE_SOURCE_CODE" >"$W/auth.log" 2>&1 <<'PY_AUTH'
import json,sys
from pathlib import Path
art,inputs=map(Path,sys.argv[1:3]); wants=[tuple(sys.argv[i:i+3]) for i in (3,6,9)]
names=('verified-training-source.json','verified-fresh-source.json','verified-subspace-source.json')
receipts=[json.load(open(art/name)) for name in names]
for name,row,want in zip(names[:2],receipts[:2],wants[:2]):
 got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha'))
 if got!=want or row.get('result_state')!='completed' or row.get('exit_code')!=0: raise SystemExit(f'{name} identity/state drift got={got} want={want}')
row,want=receipts[2],wants[2]
got=(row.get('job_id'),row.get('attempt_id'))
if got!=want[:2] or row.get('result_state')!='completed' or row.get('exit_code')!=0: raise SystemExit(f'{names[2]} path/state drift got={got} want={want[:2]}')
summary=json.load(open(inputs/'subspace-summary.json'))
if (summary.get('code_sha')!=want[2] or summary.get('verdict')!='JASS_CURRICULUM_ERROR_RESIDUAL_STABLE_SUBSPACE_READY' or summary.get('passed') is not True): raise SystemExit(f'{names[2]} signed terminal identity/verdict drift')
PY_AUTH

training_shards=(); fresh_shards=()
for shard in $(seq 0 15); do
  training_shards+=(--training-shard "$IN/training-atlas-$shard.json")
  fresh_shards+=(--fresh-shard "$IN/fresh-atlas-$shard.json")
done
python3 -m jobs.tools.l3_curriculum_error_target_specificity_autopsy \
  --training-report "$IN/training-report.json" --failed-model "$IN/failed-model.json" \
  --training-pairs "$IN/training-pairs.json" "${training_shards[@]}" \
  --fresh-summary "$IN/fresh-summary.json" --fresh-report "$IN/fresh-report.json" \
  --fresh-pairs "$IN/fresh-pairs.json" "${fresh_shards[@]}" \
  --target-cache "$IN/fresh-target-cache.json" --subspace-report "$IN/subspace-report.json" \
  --report "$ART/target-specificity-autopsy.json" >"$W/autopsy.log" 2>&1

python3 - "$ART" "$EXPECTED_CODE_SHA" \
  "$TRAINING_SOURCE_JOB" "$TRAINING_SOURCE_ATTEMPT" "$TRAINING_SOURCE_CODE" \
  "$FRESH_SOURCE_JOB" "$FRESH_SOURCE_ATTEMPT" "$FRESH_SOURCE_CODE" \
  "$SUBSPACE_SOURCE_JOB" "$SUBSPACE_SOURCE_ATTEMPT" "$SUBSPACE_SOURCE_CODE" <<'PY_FINAL'
import json,re,sys
from pathlib import Path
art=Path(sys.argv[1]); code=sys.argv[2]; sources=[tuple(sys.argv[i:i+3]) for i in (3,6,9)]
report=json.load(open(art/'target-specificity-autopsy.json'))
if report.get('verdict')!='JASS_CURRICULUM_ERROR_TARGET_SPECIFICITY_AUTOPSY_READY' or report.get('passed') is not True: raise SystemExit('autopsy verdict drift')
accounting=report.get('accounting',{})
expected={'new_exact_target_computations':0,'diagnostic_base_residual_fits_on_immutable_1508':1,'diagnostic_uplift_fits':2003,'fresh_label_pattern_eval_fits':0,'production_model_fits':0,'strength_games':0,'new_selfplay_games':0,'frozen_reads':0}
for key,value in expected.items():
 if int(accounting.get(key,-1))!=value: raise SystemExit(f'autopsy accounting drift {key}')
for key in ('anchored_local_refit_authorized','production_model_authorized','strength_gate_authorized','promotion_authorized','automatic_continuation'):
 if report.get(key) is not False: raise SystemExit(f'autopsy authorization drift {key}')
payload={**report,'schema':'jass.curriculum_error_target_specificity_autopsy_terminal.v1','code_sha':code,
 'training_source':dict(zip(('job','attempt','code_sha'),sources[0])),
 'fresh_source':dict(zip(('job','attempt','code_sha'),sources[1])),
 'subspace_source':dict(zip(('job','attempt','code_sha'),sources[2]))}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/report['verdict']).touch()
screen=report['cross_pool_uplift_screen']; metrics=screen['oof_metrics']; sham=screen['sham']; clean=lambda value:re.sub(r'[^A-Za-z0-9.+-]+','_',str(value)).strip('_')[:180]
(art/f"TARGET_SPECIFICITY__{clean(screen['status'])}").touch()
(art/f"OOF__ERR_{clean(round(metrics['error']['mean'],3))}__PAIR_{clean(round(metrics['paired']['mean'],3))}__PAIRLO_{clean(round(metrics['paired']['ci95'][0],3))}").touch()
(art/f"STABILITY__COS_{clean(round(screen['coefficient_cosine'],6))}__RANK1_{screen['pool_fits']['pool1']['rank']}__RANK2_{screen['pool_fits']['pool2']['rank']}").touch()
(art/f"SHAM__REAL_{clean(round(sham['real_paired_mean_cp'],3))}__Q99_{clean(round(sham['paired_mean_q99_cp'],3))}__PASS_{str(sham['real_exceeds_sham_q99']).upper()}").touch()
for key,value in sorted(screen['gates'].items()): (art/f"GATE__{clean(key.upper())}__{str(value).upper()}").touch()
for name in ('NEW_EXACT_TARGETS__0','DIAGNOSTIC_BASE_FITS_IMMUTABLE_1508__1','DIAGNOSTIC_UPLIFT_FITS__2003','FRESH_LABEL_PATTERNEVAL_FITS__0','PRODUCTION_MODEL_FITS__0','STRENGTH_GAMES__0','NEW_SELFPLAY__0','FROZEN_READS__0','ANCHORED_REFIT_AUTHORIZED__FALSE','PRODUCTION_MODEL_AUTHORIZED__FALSE','STRENGTH_GATE_AUTHORIZED__FALSE','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_CONTINUATION__FALSE','FRESH_1524_REUSE_FOR_CONFIRMATION__FORBIDDEN'): (art/name).touch()
(art/f"NEW_FRESH_POOL_PREREGISTRATION_RECOMMENDED__{str(report['new_fresh_pool_preregistration_recommended']).upper()}").touch()
PY_FINAL

say "JASS_CURRICULUM_ERROR_TARGET_SPECIFICITY_AUTOPSY_READY new_targets=0 production_fits=0 force=0 production=false"
