#!/usr/bin/env bash
# Sparse diagnostic cross-fit only.  It cannot emit a PatternEval production model.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${LABEL_JOB:?}"; : "${LABEL_ATTEMPT:?}"; : "${LABEL_CODE:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }
MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
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
  rm -rf "$IN" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-loss-first-crossfit-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree contract mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${CROSS_FIT_SCREEN_ONLY:-0}" = 1 ] && [ "${NO_PATTERNEVAL_FIT:-0}" = 1 ] || die "screen-only guards missing"
[ "${NO_STRENGTH_GAMES:-0}" = 1 ] && [ "${NO_SELFPLAY:-0}" = 1 ] && [ "${NO_FROZEN_READ:-0}" = 1 ] || die "forbidden action guards missing"
[ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"
git merge-base --is-ancestor "$LABEL_CODE" HEAD || die "label code is not an ancestor"
say "experiment=CURRICULUM_ERROR_LOSS_FIRST_SPARSE_JACOBIAN_CROSSFIT labels=$LABEL_JOB/$LABEL_ATTEMPT"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_curriculum_error_loss_first_crossfit.py
python3 -m unittest jobs.tests.test_l3_curriculum_error_loss_first_crossfit \
  jobs.tests.test_l3_curriculum_error_loss_first_sibling_labels \
  jobs.tests.test_l3_curriculum_error_loss_first_sibling_rank_preregistration \
  >"$W/tests.log" 2>&1
python3 - <<'PY_SCIPY'
import scipy
from scipy.optimize import minimize
print(scipy.__version__, minimize)
PY_SCIPY

stage fetch-and-authenticate-certified-loss-first-labels
timeout 1800s python3 jobs/tools/fetch_result_files.py \
  --prefix "r2:jass-data/runs/$LABEL_JOB/$LABEL_ATTEMPT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=label-summary.json \
  --file artefacts/loss-first-labels.json=loss-first-labels.json \
  --file artefacts/loss-first-matched-pairs.json=loss-first-matched-pairs.json \
  --out-dir "$IN" --report "$ART/verified-labels.json" --expected-state completed \
  >"$W/fetch-labels.log" 2>&1
python3 - "$ART/verified-labels.json" "$IN/label-summary.json" "$IN/loss-first-labels.json" "$IN/loss-first-matched-pairs.json" \
  "$LABEL_JOB" "$LABEL_ATTEMPT" "$LABEL_CODE" >"$W/auth.log" 2>&1 <<'PY_AUTH'
import hashlib,json,sys
receipt=json.load(open(sys.argv[1])); summary=json.load(open(sys.argv[2])); labels=json.load(open(sys.argv[3])); pairs=json.load(open(sys.argv[4]))
got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'),receipt.get('result_state'),receipt.get('exit_code'))
want=(sys.argv[5],sys.argv[6],sys.argv[7],'completed',0)
if got!=want: raise SystemExit(f'label receipt drift got={got} want={want}')
if summary.get('code_sha')!=sys.argv[7] or summary.get('verdict')!='JASS_CURRICULUM_ERROR_LOSS_FIRST_LABELS_READY' or summary.get('passed') is not True:
 raise SystemExit('label terminal summary drift')
if labels.get('verdict')!=summary.get('verdict') or labels.get('matched_pairs')!=len(pairs.get('pairs') or []):
 raise SystemExit('label payload/pair cardinality drift')
for key in ('anchored_local_refit_authorized','production_model_authorized','strength_gate_authorized','promotion_authorized','automatic_continuation'):
 if summary.get(key) is not False: raise SystemExit(f'upstream authorization drift {key}')
PY_AUTH

stage fit-pool1-evaluate-pool2-and-fit-pool2-evaluate-pool1-with-1000-shams
python3 jobs/tools/l3_curriculum_error_loss_first_crossfit.py \
  --labels "$IN/loss-first-labels.json" --pairs "$IN/loss-first-matched-pairs.json" \
  --bootstrap-samples 200000 --bootstrap-seed 2026082345 \
  --sham-replicates 1000 --sham-seed 2026082346 \
  --report "$ART/loss-first-crossfit.json" --models "$ART/loss-first-diagnostic-directions.json" \
  >"$W/crossfit.log" 2>&1

stage audit-and-publish-terminal-verdict
python3 - "$ART" "$EXPECTED_CODE_SHA" "$LABEL_JOB" "$LABEL_ATTEMPT" "$LABEL_CODE" <<'PY_FINAL'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); report=json.load(open(art/'loss-first-crossfit.json'))
if report.get('verdict') not in {'JASS_CURRICULUM_ERROR_LOSS_FIRST_SPARSE_JACOBIAN_CROSSFIT_READY','JASS_CURRICULUM_ERROR_LOSS_FIRST_SPARSE_JACOBIAN_NOT_ESTABLISHED'}:
 raise SystemExit('cross-fit verdict drift')
for key in ('pattern_eval_fits','production_model_fits','strength_games','new_selfplay_games','frozen_reads'):
 if int(report.get(key,-1))!=0: raise SystemExit(f'accounting drift {key}')
for key in ('production_model_authorized','strength_gate_authorized','promotion_authorized','automatic_continuation'):
 if report.get(key) is not False: raise SystemExit(f'authorization drift {key}')
if int(report['protocol']['bootstrap']['samples'])!=200000 or int(report['protocol']['shams']['replicates'])!=1000:
 raise SystemExit('resampling contract drift')
payload={**report,'schema':'jass.curriculum_error_loss_first_crossfit_terminal.v1','code_sha':sys.argv[2],
         'source':{'job':sys.argv[3],'attempt':sys.argv[4],'code_sha':sys.argv[5]}}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/report['verdict']).touch()
for name in ('PATTERNEVAL_FITS__0','PRODUCTION_MODEL_FITS__0','STRENGTH_GAMES__0','NEW_SELFPLAY__0','FROZEN_READS__0','PRODUCTION_MODEL_AUTHORIZED__FALSE','STRENGTH_GATE_AUTHORIZED__FALSE','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_CONTINUATION__FALSE'):
 (art/name).touch()
if report['passed']:
 (art/'ANCHORED_LOCAL_REFIT_AUTHORIZED__TRUE').touch(); (art/'NEXT__anchored_local_refit_with_exact_outside_region_invariance').touch()
else:
 (art/'ANCHORED_LOCAL_REFIT_AUTHORIZED__FALSE').touch()
PY_FINAL
VERDICT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
stage completed
say "$VERDICT diagnostic_only=true bootstrap=200000 shams=1000 production=0 force=0"
