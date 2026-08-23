#!/usr/bin/env bash
# One-shot OOS audit of the fixed trace-gated residual; no refit and confirm sealed.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${TRAINING_SOURCE_JOB:?}"; : "${TRAINING_SOURCE_ATTEMPT:?}"; : "${TRAINING_SOURCE_CODE:?}"
: "${PREREG_SOURCE_JOB:?}"; : "${PREREG_SOURCE_ATTEMPT:?}"; : "${PREREG_SOURCE_CODE:?}"
: "${PAIRS_SOURCE_JOB:?}"; : "${PAIRS_SOURCE_ATTEMPT:?}"; : "${PAIRS_SOURCE_CODE:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
ATLAS="$ART/feature-audit-atlas-shards"
mkdir -p "$W" "$IN" "$ART" "$ATLAS"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE="18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
CURRICULUM_ROOT="r2:jass-data/runs/$CURRICULUM_JOB/$CURRICULUM_ATTEMPT"
TRAINING_ROOT="r2:jass-data/runs/$TRAINING_SOURCE_JOB/$TRAINING_SOURCE_ATTEMPT"
PREREG_ROOT="r2:jass-data/runs/$PREREG_SOURCE_JOB/$PREREG_SOURCE_ATTEMPT"
PAIRS_ROOT="r2:jass-data/runs/$PAIRS_SOURCE_JOB/$PAIRS_SOURCE_ATTEMPT"
NSH=16
CACHE_MB=128

MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        printf 'feature_audit_atlas_shards=%s/16\n' "$(find "$ATLAS" -name 'shard-*.json' 2>/dev/null | wc -l)"
      } >"$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 120
    done ) & MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-trace-residual-feature-audit-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree contract mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "${ONE_SHOT_FEATURE_AUDIT:-0}" = 1 ] && [ "${NO_RESIDUAL_REFIT:-0}" = 1 ] && [ "${NO_OUTER_CONFIRM_TARGETS:-0}" = 1 ] || die "OOS isolation guards missing"
[ "${NO_SELFPLAY:-0}" = 1 ] && [ "${NO_PATTERNEVAL_FIT:-0}" = 1 ] && [ "${NO_STRENGTH_GAMES:-0}" = 1 ] || die "forbidden-compute guards missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] && [ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"
say "experiment=CURRICULUM_ERROR_TRACE_RESIDUAL_FEATURE_AUDIT training=$TRAINING_SOURCE_JOB/$TRAINING_SOURCE_ATTEMPT"
say "one_shot_OOS=1 residual_refit=0 outer_confirm_targets=0 PatternEval_fit=0 force=0 frozen=0 promotion=false"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_curriculum_error_trace_residual_feature_audit.py
python3 -m unittest \
  jobs.tests.test_l3_curriculum_error_trace_residual_feature_audit \
  jobs.tests.test_l3_curriculum_error_trace_residual_feature_audit_template \
  jobs.tests.test_l3_curriculum_error_trace_residual_training \
  jobs.tests.test_l3_curriculum_search_error_atlas >"$W/tests.log" 2>&1

stage fetch-authenticate-fixed-model-sealed-split-and-curriculum
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$TRAINING_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=training-summary.json \
  --file artefacts/trace-residual-training.json=training-report.json \
  --file artefacts/trace-residual-model.json=training-model.json \
  --file artefacts/gate-fit-pairs.json=gate-fit-pairs.json \
  --file artefacts/sealed-audit-manifest.json=sealed-audit-manifest.json \
  --out-dir "$IN" --report "$ART/verified-training-source.json" --expected-state completed \
  >"$W/fetch-training.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$PREREG_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=preregistration.json \
  --out-dir "$IN" --report "$ART/verified-preregistration.json" --expected-state completed \
  >"$W/fetch-preregistration.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$PAIRS_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=pairs-summary.json \
  --file artefacts/matched-pairs.json=matched-pairs.json \
  --file artefacts/search-params.txt=search-params.txt \
  --out-dir "$IN" --report "$ART/verified-pairs-source.json" --expected-state completed \
  >"$W/fetch-pairs.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=curriculum-summary.json \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" --expected-state completed \
  >"$W/fetch-curriculum.log" 2>&1
gunzip -t "$IN/curriculum.pjtw.gz"; gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
python3 - "$IN" "$ART" "$TRAINING_SOURCE_JOB" "$TRAINING_SOURCE_ATTEMPT" "$TRAINING_SOURCE_CODE" \
  "$PREREG_SOURCE_JOB" "$PREREG_SOURCE_ATTEMPT" "$PREREG_SOURCE_CODE" \
  "$PAIRS_SOURCE_JOB" "$PAIRS_SOURCE_ATTEMPT" "$PAIRS_SOURCE_CODE" \
  "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" "$CURRICULUM_CODE" "$CURRICULUM_SHA" <<'PY_AUTH'
import json,sys
from pathlib import Path
src,art=map(Path,sys.argv[1:3]); values=sys.argv[3:]; expected=[tuple(values[i:i+3]) for i in range(0,12,3)]; champion=values[12]
for name,want in zip(('verified-training-source.json','verified-preregistration.json','verified-pairs-source.json','verified-curriculum.json'),expected,strict=True):
 receipt=json.load(open(art/name)); got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'))
 if got!=want or receipt.get('result_state')!='completed' or receipt.get('exit_code')!=0: raise SystemExit(f'{name} identity/state drift got={got} want={want}')
summary=json.load(open(src/'training-summary.json')); report=json.load(open(src/'training-report.json')); model=json.load(open(src/'training-model.json'))
if summary.get('verdict')!='JASS_CURRICULUM_ERROR_TRACE_RESIDUAL_TRAINING_READY' or report.get('passed') is not True: raise SystemExit('training verdict drift')
if model.get('authorized_for_feature_audit') is not True or model.get('authorized_for_production') is not False: raise SystemExit('model authorization drift')
for row,name in ((summary,'summary'),(report,'report')):
 for key in ('feature_audit_action_value_reads','outer_confirm_action_value_reads','pattern_eval_fits','strength_games','new_selfplay_games','frozen_reads'):
  if row.get(key)!=0: raise SystemExit(f'training {name} forbidden counter drift {key}')
if summary.get('champion_sha256')!=champion or report.get('champion_sha256')!=champion or model.get('champion_sha256')!=champion: raise SystemExit('champion identity drift')
PY_AUTH
[ "$(sha256sum "$W/curriculum.pjtw" | awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM raw hash drift"
[ "$(tr ',' '\n' <"$IN/search-params.txt" | wc -l)" -eq 63 ] || die "Q00 key count drift"
cp "$IN/search-params.txt" "$ART/search-params.txt"

stage reproduce-and-materialize-one-shot-feature-audit-only
python3 jobs/tools/l3_curriculum_error_trace_residual_feature_audit.py materialize \
  --pairs "$IN/matched-pairs.json" --preregistration "$IN/preregistration.json" \
  --split-manifest "$IN/sealed-audit-manifest.json" --gate-fit-pairs "$IN/gate-fit-pairs.json" \
  --training-report "$IN/training-report.json" --model "$IN/training-model.json" \
  --feature-audit-pairs "$ART/feature-audit-pairs.json" \
  --certificate "$ART/feature-audit-materialization.json" >"$W/materialize.log" 2>&1

stage build-current-exact-fold-tempo-engine
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON \
  -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests >"$W/build.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB ctest --test-dir "$W/build" --output-on-failure >"$W/ctest.log" 2>&1
J="$W/build/jass"
printf 'hello\nquit\n' | timeout 60 "$J" --pattern "$W/curriculum.pjtw" --search-params "$(cat "$ART/search-params.txt")" >"$W/load.log" 2>&1
grep -q '^ready' "$W/load.log" || die "CURRICULUM does not load"

stage exact-targets-on-feature-audit-once
pids=()
for shard in $(seq 0 $((NSH-1))); do
  python3 jobs/tools/l3_curriculum_search_error_atlas.py atlas \
    --pairs "$ART/feature-audit-pairs.json" --jass "$J" --champion "$W/curriculum.pjtw" \
    --search-params "$ART/search-params.txt" --judge-depth 12 \
    --shard "$shard" --nshards "$NSH" --out "$ATLAS/shard-$shard.json" \
    >"$W/atlas-$shard.log" 2>&1 & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done
[ "$(find "$ATLAS" -name 'shard-*.json' | wc -l)" -eq "$NSH" ] || die "feature-audit atlas shard count drift"

stage apply-fixed-model-once-without-refit
atlas_args=(); for shard in $(seq 0 $((NSH-1))); do atlas_args+=(--atlas-shard "$ATLAS/shard-$shard.json"); done
python3 jobs/tools/l3_curriculum_error_trace_residual_feature_audit.py audit \
  --preregistration "$IN/preregistration.json" --training-report "$IN/training-report.json" \
  --model "$IN/training-model.json" --pairs "$ART/feature-audit-pairs.json" \
  "${atlas_args[@]}" --report "$ART/trace-residual-feature-audit.json" >"$W/audit.log" 2>&1

stage audit-and-publish-one-shot-oos-verdict
python3 - "$ART" "$EXPECTED_CODE_SHA" "$TRAINING_SOURCE_JOB" "$TRAINING_SOURCE_ATTEMPT" "$TRAINING_SOURCE_CODE" "$CURRICULUM_SHA" <<'PY_FINAL'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); code=sys.argv[2]; source=tuple(sys.argv[3:6]); champion=sys.argv[6]
report=json.load(open(art/'trace-residual-feature-audit.json')); material=json.load(open(art/'feature-audit-materialization.json'))
if report.get('verdict') not in {'JASS_CURRICULUM_ERROR_TRACE_RESIDUAL_FEATURE_AUDIT_READY','JASS_CURRICULUM_ERROR_TRACE_RESIDUAL_FEATURE_AUDIT_NOT_ESTABLISHED'}: raise SystemExit('audit verdict drift')
if report.get('champion_sha256')!=champion: raise SystemExit('audit champion drift')
for key in ('outer_confirm_profile_rows_examined','outer_confirm_action_value_reads','residual_fits','pattern_eval_fits','strength_games','new_selfplay_games','frozen_reads'):
 if report.get(key)!=0: raise SystemExit(f'audit forbidden counter drift {key}')
if material.get('feature_audit_action_value_reads')!=0 or material.get('outer_confirm_action_value_reads')!=0 or any(material.get('overlap',{}).values()): raise SystemExit('materialization leakage drift')
payload={**report,'schema':'jass.curriculum_error_trace_residual_feature_audit_terminal.v1','code_sha':code,
 'training_source':{'job':source[0],'attempt':source[1],'code_sha':source[2]},
 'weights_bit_identical':True,'automatic_continuation':False,'promotion_authorized':False}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/report['verdict']).touch()
for name,value in report['gates'].items(): (art/f"GATE__{name.upper()}__{str(value).upper()}").touch()
for name in ('OUTER_CONFIRM_PROFILE_ROWS_EXAMINED__0','OUTER_CONFIRM_ACTION_VALUE_READS__0','RESIDUAL_FITS__0','PATTERNEVAL_FITS__0','STRENGTH_GAMES__0','NEW_SELFPLAY__0','FROZEN_READS__0','PRODUCTION_RULE_AUTHORIZED__FALSE','PROMOTION_AUTHORIZED__FALSE'):
 (art/name).touch()
PY_FINAL
VERDICT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
stage completed-one-shot-feature-audit
say "$VERDICT residual_refit=0 outer_confirm_targets=0 PatternEval_fit=0 strength=0 production=false"
