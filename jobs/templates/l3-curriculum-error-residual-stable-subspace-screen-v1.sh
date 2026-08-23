#!/usr/bin/env bash
# Read-only fold-stability screen over immutable 1508 residual targets.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${TRAINING_SOURCE_JOB:?}"; : "${TRAINING_SOURCE_ATTEMPT:?}"; : "${TRAINING_SOURCE_CODE:?}"
: "${PREREG_SOURCE_JOB:?}"; : "${PREREG_SOURCE_ATTEMPT:?}"; : "${PREREG_SOURCE_CODE:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"; RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; for name in tests fetch-training fetch-prereg screen; do [ -s "$W/$name.log" ] && cp "$W/$name.log" "$ART/$name.log"; done; rm -rf "$IN"; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-residual-stable-subspace-screen-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree contract mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${TRAINING_ONLY_REUSE_TARGETS:-0}" = 1 ] && [ "${DIAGNOSTIC_RESIDUAL_FITS_ALLOWED:-0}" = 1 ] || die "diagnostic training guards missing"
[ "${NO_NEW_ACTION_TARGETS:-0}" = 1 ] && [ "${NO_FRESH_LABEL_READ:-0}" = 1 ] || die "fresh-data guards missing"
[ "${NO_FEATURE_AUDIT_READ:-0}" = 1 ] && [ "${NO_OUTER_CONFIRM_READ:-0}" = 1 ] || die "sealed-data guards missing"
[ "${NO_SELFPLAY:-0}" = 1 ] && [ "${NO_PATTERNEVAL_FIT:-0}" = 1 ] && [ "${NO_PRODUCTION_FIT:-0}" = 1 ] || die "fit guards missing"
[ "${NO_STRENGTH_GAMES:-0}" = 1 ] && [ "${NO_FROZEN_READ:-0}" = 1 ] || die "forbidden-compute guards missing"
[ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"
TRAINING_ROOT="r2:jass-data/runs/$TRAINING_SOURCE_JOB/$TRAINING_SOURCE_ATTEMPT"
PREREG_ROOT="r2:jass-data/runs/$PREREG_SOURCE_JOB/$PREREG_SOURCE_ATTEMPT"
say "experiment=CURRICULUM_ERROR_RESIDUAL_STABLE_SUBSPACE source=$TRAINING_SOURCE_JOB/$TRAINING_SOURCE_ATTEMPT alpha=300"
say "reuse_1508_targets=1 new_targets=0 fresh_labels=0 PatternEval=0 production=0 force=0 frozen=0 promotion=false"

python3 -m py_compile jobs/tools/l3_curriculum_error_residual_stable_subspace_screen.py
python3 -m unittest \
  jobs.tests.test_l3_curriculum_error_residual_stable_subspace_screen \
  jobs.tests.test_l3_curriculum_error_residual_ridge_path_screen \
  jobs.tests.test_l3_curriculum_error_trace_residual_training \
  jobs.tests.test_l3_curriculum_error_residual_stable_subspace_screen_template \
  >"$W/tests.log" 2>&1
training_args=()
for shard in $(seq 0 15); do training_args+=(--file "artefacts/gate-fit-atlas-shards/shard-$shard.json=atlas-$shard.json"); done
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$TRAINING_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=training-summary.json \
  --file artefacts/trace-residual-training.json=training-report.json \
  --file artefacts/trace-residual-model.json=failed-model.json \
  --file artefacts/gate-fit-pairs.json=gate-fit-pairs.json \
  "${training_args[@]}" --out-dir "$IN" --report "$ART/verified-training-source.json" \
  --expected-state completed >"$W/fetch-training.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$PREREG_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=preregistration.json \
  --out-dir "$IN" --report "$ART/verified-preregistration.json" --expected-state completed \
  >"$W/fetch-prereg.log" 2>&1
python3 - "$IN" "$ART" "$TRAINING_SOURCE_JOB" "$TRAINING_SOURCE_ATTEMPT" "$TRAINING_SOURCE_CODE" "$PREREG_SOURCE_JOB" "$PREREG_SOURCE_ATTEMPT" "$PREREG_SOURCE_CODE" <<'PY_AUTH'
import json,sys
from pathlib import Path
src,art=map(Path,sys.argv[1:3]); training=tuple(sys.argv[3:6]); prereg=tuple(sys.argv[6:9])
for name,want in (('verified-training-source.json',training),('verified-preregistration.json',prereg)):
 receipt=json.load(open(art/name)); got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'))
 if got!=want or receipt.get('result_state')!='completed' or receipt.get('exit_code')!=0: raise SystemExit(f'{name} identity/state drift got={got} want={want}')
summary=json.load(open(src/'training-summary.json')); report=json.load(open(src/'training-report.json'))
if summary.get('verdict')!='JASS_CURRICULUM_ERROR_TRACE_RESIDUAL_TRAINING_NOT_ESTABLISHED' or report.get('passed') is not False: raise SystemExit('training source verdict drift')
for row,name in ((summary,'summary'),(report,'report')):
 for key in ('feature_audit_action_value_reads','outer_confirm_action_value_reads','pattern_eval_fits','strength_games','new_selfplay_games','frozen_reads'):
  if row.get(key)!=0: raise SystemExit(f'{name} forbidden source counter drift {key}')
PY_AUTH
atlas_args=(); for shard in $(seq 0 15); do atlas_args+=(--atlas-shard "$IN/atlas-$shard.json"); done
python3 -m jobs.tools.l3_curriculum_error_residual_stable_subspace_screen \
  --preregistration "$IN/preregistration.json" --training-report "$IN/training-report.json" \
  --failed-model "$IN/failed-model.json" --pairs "$IN/gate-fit-pairs.json" \
  "${atlas_args[@]}" --report "$ART/stable-subspace-screen.json" >"$W/screen.log" 2>&1
python3 - "$ART" "$EXPECTED_CODE_SHA" "$TRAINING_SOURCE_JOB" "$TRAINING_SOURCE_ATTEMPT" "$TRAINING_SOURCE_CODE" <<'PY_FINAL'
import json,re,sys
from pathlib import Path
art=Path(sys.argv[1]); code=sys.argv[2]; source=tuple(sys.argv[3:6]); report=json.load(open(art/'stable-subspace-screen.json'))
allowed={'JASS_CURRICULUM_ERROR_RESIDUAL_STABLE_SUBSPACE_READY','JASS_CURRICULUM_ERROR_RESIDUAL_STABLE_SUBSPACE_NOT_ESTABLISHED'}
if report.get('verdict') not in allowed: raise SystemExit('stable subspace verdict drift')
expected={'new_exact_target_computations':0,'fresh_label_reads':0,'feature_audit_action_value_reads':0,'outer_confirm_action_value_reads':0,'pattern_eval_fits':0,'production_model_fits':0,'strength_games':0,'new_selfplay_games':0,'frozen_reads':0}
for key,value in expected.items():
 if report.get(key)!=value: raise SystemExit(f'forbidden counter drift {key}')
for key in ('anchored_refit_authorized','strength_gate_authorized','promotion_authorized','automatic_continuation'):
 if report.get(key) is not False: raise SystemExit(f'authorization drift {key}')
payload={**report,'schema':'jass.curriculum_error_residual_stable_subspace_terminal.v1','code_sha':code,
 'training_source':{'job':source[0],'attempt':source[1],'code_sha':source[2]}}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n'); (art/report['verdict']).touch()
clean=lambda value: re.sub(r'[^A-Za-z0-9.+-]+','_',str(value)).strip('_')
analysis=report['analysis']; stability=analysis['fold_stability']
(art/f"SUBSPACE__N_{analysis['selected_feature_count']}__HASH_{analysis['support_sha256'][:16]}").touch()
(art/f"STABILITY__COSMIN_{clean(round(stability['minimum_coefficient_cosine'],6))}__JACCMIN_{clean(round(stability['minimum_top6_jaccard'],6))}").touch()
for index,name in zip(analysis['selected_feature_indices'],analysis['selected_feature_names'],strict=True): (art/f"FEATURE__{index:02d}__{clean(name)}").touch()
for gate,value in sorted(report['gates'].items()): (art/f"GATE__{gate.upper()}__{str(value).upper()}").touch()
for name in ('NEW_ACTION_TARGETS__0','FRESH_LABEL_READS__0','FEATURE_AUDIT_ACTION_VALUE_READS__0','OUTER_CONFIRM_ACTION_VALUE_READS__0','PATTERNEVAL_FITS__0','PRODUCTION_MODEL_FITS__0','STRENGTH_GAMES__0','NEW_SELFPLAY__0','FROZEN_READS__0','ANCHORED_REFIT_AUTHORIZED__FALSE','STRENGTH_GATE_AUTHORIZED__FALSE','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_CONTINUATION__FALSE'): (art/name).touch()
PY_FINAL
VERDICT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
N=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["analysis"]["selected_feature_count"])' "$ART/JASS_CONTROL_SUMMARY.json")
say "$VERDICT selected_features=$N alpha=300 fresh_labels=0 refit=false strength=0"
