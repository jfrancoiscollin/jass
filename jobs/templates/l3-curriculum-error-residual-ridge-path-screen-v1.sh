#!/usr/bin/env bash
# Training-only OOF alpha/cap/consensus stability screen over the fixed 1508 atlas.
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
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-residual-ridge-path-screen-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree contract mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${TRAINING_ONLY_REUSE_TARGETS:-0}" = 1 ] && [ "${DIAGNOSTIC_RESIDUAL_FITS_ALLOWED:-0}" = 1 ] || die "diagnostic training guards missing"
[ "${NO_NEW_ACTION_TARGETS:-0}" = 1 ] && [ "${NO_FEATURE_AUDIT_READ:-0}" = 1 ] && [ "${NO_OUTER_CONFIRM_READ:-0}" = 1 ] || die "sealed-data guards missing"
[ "${NO_SELFPLAY:-0}" = 1 ] && [ "${NO_PATTERNEVAL_FIT:-0}" = 1 ] && [ "${NO_STRENGTH_GAMES:-0}" = 1 ] || die "forbidden-compute guards missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] && [ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"
TRAINING_ROOT="r2:jass-data/runs/$TRAINING_SOURCE_JOB/$TRAINING_SOURCE_ATTEMPT"
PREREG_ROOT="r2:jass-data/runs/$PREREG_SOURCE_JOB/$PREREG_SOURCE_ATTEMPT"
say "experiment=CURRICULUM_ERROR_RESIDUAL_RIDGE_PATH source=$TRAINING_SOURCE_JOB/$TRAINING_SOURCE_ATTEMPT"
say "reuse_gate_fit_targets=1 new_targets=0 feature_audit=0 confirm=0 PatternEval=0 force=0 frozen=0 promotion=false"

python3 -m py_compile jobs/tools/l3_curriculum_error_residual_ridge_path_screen.py
python3 -m unittest jobs.tests.test_l3_curriculum_error_residual_ridge_path_screen \
  jobs.tests.test_l3_curriculum_error_residual_ridge_path_screen_template \
  jobs.tests.test_l3_curriculum_error_trace_residual_training >"$W/tests.log" 2>&1
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
python3 -m jobs.tools.l3_curriculum_error_residual_ridge_path_screen \
  --preregistration "$IN/preregistration.json" --training-report "$IN/training-report.json" \
  --failed-model "$IN/failed-model.json" --pairs "$IN/gate-fit-pairs.json" \
  "${atlas_args[@]}" --report "$ART/ridge-path-screen.json" >"$W/screen.log" 2>&1
python3 - "$ART" "$EXPECTED_CODE_SHA" "$TRAINING_SOURCE_JOB" "$TRAINING_SOURCE_ATTEMPT" "$TRAINING_SOURCE_CODE" <<'PY_FINAL'
import collections,json,re,sys
from pathlib import Path
art=Path(sys.argv[1]); code=sys.argv[2]; source=tuple(sys.argv[3:6]); report=json.load(open(art/'ridge-path-screen.json'))
if report.get('verdict') not in {'JASS_CURRICULUM_ERROR_RESIDUAL_RIDGE_PATH_SCREEN_READY','JASS_CURRICULUM_ERROR_RESIDUAL_RIDGE_PATH_SCREEN_NOT_ESTABLISHED'}: raise SystemExit('screen verdict drift')
if report.get('feature_audit_profile_rows_examined')!=0 or report.get('feature_audit_action_value_reads')!=0 or report.get('outer_confirm_action_value_reads')!=0: raise SystemExit('sealed read drift')
for key in ('pattern_eval_fits','production_model_fits','strength_games','new_selfplay_games','frozen_reads'):
 if report.get(key)!=0: raise SystemExit(f'forbidden screen counter drift {key}')
payload={**report,'schema':'jass.curriculum_error_residual_ridge_path_terminal.v1','code_sha':code,
 'training_source':{'job':source[0],'attempt':source[1],'code_sha':source[2]},'automatic_continuation':False,
 'feature_audit_authorized':False,'production_rule_authorized':False,'promotion_authorized':False}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n'); (art/report['verdict']).touch()
clean=lambda value: re.sub(r'[^A-Za-z0-9.+-]+','_',str(value)).strip('_')
rows=report['candidates']; fail=collections.Counter(gate for row in rows for gate in row['failed_gates'])
(art/f"GRID__CANDIDATES_{len(rows)}__BASEPASS_{sum(row['base_passed'] for row in rows)}__PASS_{report['passing_candidates']}").touch()
(art/f"MAX__ERRINT_{max(row['metrics']['error_interventions'] for row in rows)}__PAIRLO_{clean(round(max(row['metrics']['paired_error_minus_control']['ci95'][0] for row in rows),3))}__DECJACC_{clean(round(max(row['stability']['minimum_fold_decision_jaccard'] for row in rows),3))}").touch()
for gate,count in sorted(fail.items()): (art/f"FAILCOUNT__{gate.upper()}__{count}").touch()
selected=report['selected']
if selected:
 m=selected['metrics']; (art/f"SELECTED__A_{clean(selected['alpha'])}__CAP_{clean(selected['cap_cp'])}__MODE_{selected['mode']}__T_{clean(selected['threshold_cp'])}__ERRINT_{m['error_interventions']}__CTLINT_{m['control_interventions']}__PAIRLO_{clean(round(m['paired_error_minus_control']['ci95'][0],3))}").touch()
else: (art/'SELECTED__NONE').touch()
sham=report['sham']
if sham: (art/f"SHAM__REAL_{clean(round(sham['real_paired_mean_cp'],3))}__Q95_{clean(round(sham['sham_q95_cp'],3))}__PASS_{str(sham['real_exceeds_sham_q95']).upper()}").touch()
else: (art/'SHAM__NOT_RUN').touch()
for name in ('NEW_ACTION_TARGETS__0','FEATURE_AUDIT_PROFILE_ROWS_EXAMINED__0','FEATURE_AUDIT_ACTION_VALUE_READS__0','OUTER_CONFIRM_ACTION_VALUE_READS__0','PATTERNEVAL_FITS__0','PRODUCTION_MODEL_FITS__0','STRENGTH_GAMES__0','NEW_SELFPLAY__0','FROZEN_READS__0','FEATURE_AUDIT_AUTHORIZED__FALSE','PRODUCTION_RULE_AUTHORIZED__FALSE','PROMOTION_AUTHORIZED__FALSE'):
 (art/name).touch()
PY_FINAL
VERDICT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
say "$VERDICT candidates=490 new_targets=0 feature_audit=0 confirm=0 production=false"
