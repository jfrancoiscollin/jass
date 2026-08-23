#!/usr/bin/env bash
# Read-only familywise cross-pool atlas after target-specificity stable6 failed.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${TRAINING_SOURCE_JOB:?}"; : "${TRAINING_SOURCE_ATTEMPT:?}"; : "${TRAINING_SOURCE_CODE:?}"
: "${FRESH_SOURCE_JOB:?}"; : "${FRESH_SOURCE_ATTEMPT:?}"; : "${FRESH_SOURCE_CODE:?}"
: "${SUBSPACE_SOURCE_JOB:?}"; : "${SUBSPACE_SOURCE_ATTEMPT:?}"; : "${SUBSPACE_SOURCE_CODE:?}"
: "${TARGET_SOURCE_JOB:?}"; : "${TARGET_SOURCE_ATTEMPT:?}"; : "${TARGET_SOURCE_CODE:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"; RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  for name in tests fetch-training fetch-fresh fetch-subspace fetch-target auth atlas; do
    [ -s "$W/$name.log" ] && cp "$W/$name.log" "$ART/$name.log"
  done
  rm -rf "$IN"; exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-bucket-treatment-atlas-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree contract mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${READ_ONLY_BUCKET_TREATMENT_ATLAS:-0}" = 1 ] && [ "${REPLAY_1524_BIT_EXACT:-0}" = 1 ] || die "atlas guards missing"
[ "${FAMILYWISE_1000_SHAMS:-0}" = 1 ] && [ "${CROSS_POOL_ONLY:-0}" = 1 ] || die "causal screen guards missing"
[ "${FIT_IMMUTABLE_1508_ONLY:-0}" = 1 ] && [ "${DIAGNOSTIC_BUCKET_FITS_ALLOWED:-0}" = 1 ] || die "diagnostic fit guards missing"
[ "${NO_NEW_EXACT_TARGETS:-0}" = 1 ] && [ "${NO_SELFPLAY:-0}" = 1 ] && [ "${NO_PATTERNEVAL_FIT:-0}" = 1 ] || die "forbidden data guards missing"
[ "${NO_STRENGTH_GAMES:-0}" = 1 ] && [ "${NO_FROZEN_READ:-0}" = 1 ] && [ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"

TRAINING_ROOT="r2:jass-data/runs/$TRAINING_SOURCE_JOB/$TRAINING_SOURCE_ATTEMPT"
FRESH_ROOT="r2:jass-data/runs/$FRESH_SOURCE_JOB/$FRESH_SOURCE_ATTEMPT"
SUBSPACE_ROOT="r2:jass-data/runs/$SUBSPACE_SOURCE_JOB/$SUBSPACE_SOURCE_ATTEMPT"
TARGET_ROOT="r2:jass-data/runs/$TARGET_SOURCE_JOB/$TARGET_SOURCE_ATTEMPT"
say "experiment=CURRICULUM_ERROR_BUCKET_TREATMENT_ATLAS target=$TARGET_SOURCE_JOB/$TARGET_SOURCE_ATTEMPT"
say "new_targets=0 production_fits=0 diagnostic_base_fit=1 diagnostic_bucket_fit_equivalents=240240 PatternEval=0 force=0 selfplay=0 frozen=0 promotion=false"

python3 -m py_compile jobs/tools/l3_curriculum_error_bucket_treatment_atlas.py
python3 -m unittest \
  jobs.tests.test_l3_curriculum_error_bucket_treatment_atlas \
  jobs.tests.test_l3_curriculum_error_bucket_treatment_atlas_template \
  jobs.tests.test_l3_curriculum_error_target_specificity_autopsy \
  jobs.tests.test_l3_curriculum_error_endgame_abstention_confirmation >"$W/tests.log" 2>&1

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
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$TARGET_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=target-summary.json \
  --file artefacts/target-specificity-autopsy.json=target-report.json \
  --out-dir "$IN" --report "$ART/verified-target-source.json" \
  --expected-state completed >"$W/fetch-target.log" 2>&1

python3 - "$ART" "$IN" \
  "$TRAINING_SOURCE_JOB" "$TRAINING_SOURCE_ATTEMPT" "$TRAINING_SOURCE_CODE" \
  "$FRESH_SOURCE_JOB" "$FRESH_SOURCE_ATTEMPT" "$FRESH_SOURCE_CODE" \
  "$SUBSPACE_SOURCE_JOB" "$SUBSPACE_SOURCE_ATTEMPT" "$SUBSPACE_SOURCE_CODE" \
  "$TARGET_SOURCE_JOB" "$TARGET_SOURCE_ATTEMPT" "$TARGET_SOURCE_CODE" >"$W/auth.log" 2>&1 <<'PY_AUTH'
import json,sys
from pathlib import Path
art,inputs=map(Path,sys.argv[1:3]); wants=[tuple(sys.argv[i:i+3]) for i in (3,6,9,12)]
names=('verified-training-source.json','verified-fresh-source.json','verified-subspace-source.json','verified-target-source.json')
receipts=[json.load(open(art/name)) for name in names]
for name,row,want in zip(names,receipts,wants):
 got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha'))
 if got!=want or row.get('result_state')!='completed' or row.get('exit_code')!=0: raise SystemExit(f'{name} identity/state drift got={got} want={want}')
target_summary=json.load(open(inputs/'target-summary.json')); target_report=json.load(open(inputs/'target-report.json'))
if target_summary.get('code_sha')!=wants[3][2] or target_summary.get('verdict')!='JASS_CURRICULUM_ERROR_TARGET_SPECIFICITY_AUTOPSY_READY' or target_summary.get('passed') is not True: raise SystemExit('target terminal drift')
for key in ('cross_pool_uplift_screen','source_hashes','split_integrity','reproduction'):
 if target_summary.get(key)!=target_report.get(key): raise SystemExit(f'target terminal/report drift {key}')
PY_AUTH

training_shards=(); fresh_shards=()
for shard in $(seq 0 15); do
  training_shards+=(--training-shard "$IN/training-atlas-$shard.json")
  fresh_shards+=(--fresh-shard "$IN/fresh-atlas-$shard.json")
done
python3 -m jobs.tools.l3_curriculum_error_bucket_treatment_atlas \
  --training-report "$IN/training-report.json" --failed-model "$IN/failed-model.json" \
  --training-pairs "$IN/training-pairs.json" "${training_shards[@]}" \
  --fresh-summary "$IN/fresh-summary.json" --fresh-report "$IN/fresh-report.json" \
  --fresh-pairs "$IN/fresh-pairs.json" "${fresh_shards[@]}" \
  --target-cache "$IN/fresh-target-cache.json" --subspace-report "$IN/subspace-report.json" \
  --target-report "$IN/target-report.json" --report "$ART/bucket-treatment-atlas.json" >"$W/atlas.log" 2>&1

python3 - "$ART" "$EXPECTED_CODE_SHA" <<'PY_FINAL'
import json,re,sys
from pathlib import Path
art=Path(sys.argv[1]); code=sys.argv[2]; report=json.load(open(art/'bucket-treatment-atlas.json'))
if report.get('verdict')!='JASS_CURRICULUM_ERROR_BUCKET_TREATMENT_ATLAS_READY' or report.get('passed') is not True: raise SystemExit('atlas verdict drift')
accounting=report.get('accounting',{}); expected={'new_exact_target_computations':0,'diagnostic_base_residual_fits_on_immutable_1508':1,'diagnostic_bucket_fit_equivalents':240240,'fresh_label_pattern_eval_fits':0,'production_model_fits':0,'strength_games':0,'new_selfplay_games':0,'frozen_reads':0}
for key,value in expected.items():
 if int(accounting.get(key,-1))!=value: raise SystemExit(f'atlas accounting drift {key}')
for key in ('anchored_local_refit_authorized','production_model_authorized','strength_gate_authorized','promotion_authorized','automatic_continuation'):
 if report.get(key) is not False: raise SystemExit(f'atlas authorization drift {key}')
screen=report['bucket_treatment_screen']; best=screen['best_candidate']; sham=screen['familywise_sham']
payload={**report,'schema':'jass.curriculum_error_bucket_treatment_atlas_terminal.v1','code_sha':code}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/report['verdict']).touch(); clean=lambda value:re.sub(r'[^A-Za-z0-9.+-]+','_',str(value)).strip('_')[:180]
(art/f"BUCKET_TREATMENT__{clean(screen['status'])}").touch()
(art/f"BEST__{clean(best['config']['name'])}__MINPOOL_{clean(round(best['selection_score_min_pool_paired_mean_cp'],3))}__COS_{clean(round(best['coefficient_cosine'],6))}").touch()
(art/f"OOF__ERR_{clean(round(screen['oof_metrics']['error']['mean'],3))}__PAIR_{clean(round(screen['oof_metrics']['paired']['mean'],3))}__PAIRLO_{clean(round(screen['oof_metrics']['paired']['ci95'][0],3))}").touch()
(art/f"SHAM_FAMILYWISE__REAL_{clean(round(sham['real_selection_score_cp'],3))}__Q99_{clean(round(sham['maximum_selection_score_q99_cp'],3))}__PASS_{str(sham['real_exceeds_q99']).upper()}").touch()
for key,value in sorted(screen['gates'].items()): (art/f"GATE__{clean(key.upper())}__{str(value).upper()}").touch()
for name in ('NEW_EXACT_TARGETS__0','DIAGNOSTIC_BASE_FITS_IMMUTABLE_1508__1','DIAGNOSTIC_BUCKET_FIT_EQUIVALENTS__240240','FRESH_LABEL_PATTERNEVAL_FITS__0','PRODUCTION_MODEL_FITS__0','STRENGTH_GAMES__0','NEW_SELFPLAY__0','FROZEN_READS__0','ANCHORED_REFIT_AUTHORIZED__FALSE','PRODUCTION_MODEL_AUTHORIZED__FALSE','STRENGTH_GATE_AUTHORIZED__FALSE','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_CONTINUATION__FALSE','FRESH_1524_REUSE_FOR_CONFIRMATION__FORBIDDEN'): (art/name).touch()
(art/f"NEW_FRESH_POOL_PREREGISTRATION_RECOMMENDED__{str(report['new_fresh_pool_preregistration_recommended']).upper()}").touch()
PY_FINAL

say "JASS_CURRICULUM_ERROR_BUCKET_TREATMENT_ATLAS_READY new_targets=0 production_fits=0 force=0 production=false"
