#!/usr/bin/env bash
# Target-blind shallow selection followed by stable d10+d12 all-sibling labels.
# No PatternEval fit, strength game, frozen read or promotion occurs here.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${SOURCE_JOB:?}"; : "${SOURCE_ATTEMPT:?}"; : "${SOURCE_CODE:?}"
: "${PREREG_JOB:?}"; : "${PREREG_ATTEMPT:?}"; : "${PREREG_CODE:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
PROFILES="$ART/profile-shards"; LABELS="$ART/label-shards"
mkdir -p "$W" "$IN" "$ART" "$PROFILES" "$LABELS"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }
NSH=16; MAX_PROJECTED_MINUTES=480; PREFLIGHT_ROWS_PER_SHARD=1; CACHE_MB=128
CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE="18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
CURRICULUM_ROOT="r2:jass-data/runs/$CURRICULUM_JOB/$CURRICULUM_ATTEMPT"

MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        printf 'profile_shards=%s/16\n' "$(find "$PROFILES" -name 'shard-*.json' 2>/dev/null | wc -l)"
        printf 'label_shards=%s/16\n' "$(find "$LABELS" -name 'shard-*.json' 2>/dev/null | wc -l)"
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
  rm -rf "$W/build" "$IN" "$W/preflight" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-loss-first-labels-v1$ ]] || die "invalid job nomenclature"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree contract mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${LABELING_ONLY:-0}" = 1 ] && [ "${NO_PATTERNEVAL_FIT:-0}" = 1 ] || die "label-only guards missing"
[ "${NO_STRENGTH_GAMES:-0}" = 1 ] && [ "${NO_SELFPLAY:-0}" = 1 ] && [ "${NO_FROZEN_READ:-0}" = 1 ] || die "forbidden action guards missing"
[ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] && [ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guards missing"
git merge-base --is-ancestor "$SOURCE_CODE" HEAD || die "source code is not an ancestor"
git diff --quiet "$SOURCE_CODE" HEAD -- CMakeLists.txt src pattern_jass/generated pattern_jass/tools/gen_patterns.py || die "engine implementation drift from source campaign"
say "experiment=CURRICULUM_ERROR_LOSS_FIRST_SIBLING_LABELS source=$SOURCE_JOB/$SOURCE_ATTEMPT prereg=$PREREG_JOB/$PREREG_ATTEMPT"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_curriculum_error_loss_first_sibling_labels.py
python3 -m unittest jobs.tests.test_l3_curriculum_error_loss_first_sibling_labels \
  jobs.tests.test_l3_curriculum_error_loss_first_sibling_rank_preregistration \
  jobs.tests.test_l3_curriculum_error_learning jobs.tests.test_l3_curriculum_error_residual_atlas \
  >"$W/tests.log" 2>&1

stage fetch-authenticate-source-preregistration-and-champion
timeout 1800s python3 jobs/tools/fetch_result_files.py \
  --prefix "r2:jass-data/runs/$SOURCE_JOB/$SOURCE_ATTEMPT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=source-summary.json \
  --file artefacts/error-selection.json=source-selection.json \
  --file artefacts/error-transitions.json=source-transitions.json \
  --file artefacts/search-params.txt=source-search-params.txt \
  --out-dir "$IN" --report "$ART/verified-source.json" --expected-state completed \
  >"$W/fetch-source.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py \
  --prefix "r2:jass-data/runs/$PREREG_JOB/$PREREG_ATTEMPT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=preregistration.json \
  --out-dir "$IN" --report "$ART/verified-preregistration.json" --expected-state completed \
  >"$W/fetch-preregistration.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" --expected-state completed \
  >"$W/fetch-curriculum.log" 2>&1
gunzip -t "$IN/curriculum.pjtw.gz"; gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
python3 - "$ART" "$IN" "$SOURCE_JOB" "$SOURCE_ATTEMPT" "$SOURCE_CODE" \
  "$PREREG_JOB" "$PREREG_ATTEMPT" "$PREREG_CODE" \
  "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" "$CURRICULUM_CODE" "$CURRICULUM_SHA" \
  >"$W/auth.log" 2>&1 <<'PY_AUTH'
import hashlib,json,sys
from pathlib import Path
art=Path(sys.argv[1]); inp=Path(sys.argv[2])
def receipt(name,want):
 r=json.load(open(art/name)); got=(r.get('job_id'),r.get('attempt_id'),r.get('code_sha'),r.get('result_state'),r.get('exit_code'))
 if got!=(*want,'completed',0): raise SystemExit(f'{name} identity/state drift got={got} want={want}')
receipt('verified-source.json',tuple(sys.argv[3:6])); receipt('verified-preregistration.json',tuple(sys.argv[6:9])); receipt('verified-curriculum.json',tuple(sys.argv[9:12]))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
if sha(inp.parent/'work'/'curriculum.pjtw')!=sys.argv[12]: raise SystemExit('CURRICULUM raw hash drift')
source=json.load(open(inp/'source-summary.json')); prereg=json.load(open(inp/'preregistration.json'))
if source.get('source_code_sha')!=sys.argv[5] or source.get('selection_sha256')!=sha(inp/'source-selection.json') or source.get('transitions_sha256')!=sha(inp/'source-transitions.json'):
 raise SystemExit('loss-first source content identity drift')
if source.get('preregistration_sha256')!=sha(inp/'preregistration.json'):
 raise SystemExit('source/preregistration hash drift')
if prereg.get('code_sha')!=sys.argv[8] or prereg.get('verdict')!='JASS_CURRICULUM_ERROR_LOSS_FIRST_SIBLING_RANK_PREREGISTERED' or prereg.get('passed') is not True:
 raise SystemExit('preregistration terminal drift')
PY_AUTH

stage build-byte-identical-exact-fold-tempo-engine
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }; done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON \
  -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests >"$W/build.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB ctest --test-dir "$W/build" --output-on-failure >"$W/ctest.log" 2>&1
J="$W/build/jass"; cp "$IN/source-search-params.txt" "$ART/search-params.txt"
printf 'hello\nquit\n' | timeout 60 "$J" --pattern "$W/curriculum.pjtw" --search-params "$(cat "$ART/search-params.txt")" >"$W/load.log" 2>&1
grep -q '^ready' "$W/load.log" || die "CURRICULUM does not load"

stage select-target-blind-candidates
python3 jobs/tools/l3_curriculum_error_loss_first_sibling_labels.py candidates \
  --selection "$IN/source-selection.json" --transitions "$IN/source-transitions.json" \
  --source-summary "$IN/source-summary.json" --preregistration "$IN/preregistration.json" \
  --jass "$J" --seed 2026082343 --out "$ART/loss-first-candidates.json" >"$W/candidates.log" 2>&1

stage profile-candidates-shallow-d6-d9
pids=()
for shard in $(seq 0 $((NSH-1))); do
  python3 jobs/tools/l3_curriculum_error_loss_first_sibling_labels.py profile-worker \
    --candidates "$ART/loss-first-candidates.json" --jass "$J" --champion "$W/curriculum.pjtw" \
    --search-params "$ART/search-params.txt" --shard "$shard" --nshards "$NSH" \
    --out "$PROFILES/shard-$shard.json" >"$W/profile-$shard.log" 2>&1 & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done
[ "$(find "$PROFILES" -name 'shard-*.json' | wc -l)" -eq "$NSH" ] || die "profile shard count drift"
profile_args=(); for shard in $(seq 0 $((NSH-1))); do profile_args+=(--profile-shard "$PROFILES/shard-$shard.json"); done
python3 jobs/tools/l3_curriculum_error_loss_first_sibling_labels.py select \
  --candidates "$ART/loss-first-candidates.json" "${profile_args[@]}" --seed 2026082343 \
  --out "$ART/loss-first-selection.json" >"$W/select.log" 2>&1

stage d10-d12-all-sibling-cost-preflight
mkdir -p "$W/preflight"; T0=$(date +%s); pids=()
for shard in $(seq 0 $((NSH-1))); do
  python3 jobs/tools/l3_curriculum_error_loss_first_sibling_labels.py label-worker \
    --selection "$ART/loss-first-selection.json" --jass "$J" --champion "$W/curriculum.pjtw" \
    --search-params "$ART/search-params.txt" --shard "$shard" --nshards "$NSH" \
    --max-rows "$PREFLIGHT_ROWS_PER_SHARD" --out "$W/preflight/shard-$shard.json" \
    >"$W/preflight-$shard.log" 2>&1 & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done
T1=$(date +%s)
python3 - "$ART/loss-first-selection.json" "$W/preflight" "$ART/cost-preflight.json" "$((T1-T0))" "$MAX_PROJECTED_MINUTES" <<'PY_COST'
import json,sys
from pathlib import Path
selection=json.load(open(sys.argv[1])); root=Path(sys.argv[2]); out=Path(sys.argv[3]); elapsed=max(int(sys.argv[4]),1); maximum=int(sys.argv[5])
rows=sum(len(json.load(open(path))['rows']) for path in root.glob('shard-*.json')); total=int(selection['selected'])
if rows<=0: raise SystemExit('label cost preflight produced zero rows')
projected=elapsed*total/rows/60; payload={'schema':'jass.loss_first_sibling_label_cost_preflight.v1','sample_rows':rows,'total_rows':total,'elapsed_seconds':elapsed,'projected_minutes':projected,'maximum_minutes':maximum,'passed':projected<=maximum}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
if projected>maximum: raise SystemExit(f'projected labeling {projected:.1f} min exceeds {maximum}')
PY_COST

stage label-all-legal-siblings-d10-d12-exact-symmetry
pids=()
for shard in $(seq 0 $((NSH-1))); do
  python3 jobs/tools/l3_curriculum_error_loss_first_sibling_labels.py label-worker \
    --selection "$ART/loss-first-selection.json" --jass "$J" --champion "$W/curriculum.pjtw" \
    --search-params "$ART/search-params.txt" --shard "$shard" --nshards "$NSH" \
    --out "$LABELS/shard-$shard.json" >"$W/label-$shard.log" 2>&1 & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done
[ "$(find "$LABELS" -name 'shard-*.json' | wc -l)" -eq "$NSH" ] || die "label shard count drift"

stage match-errors-controls-and-publish
label_args=(); for shard in $(seq 0 $((NSH-1))); do label_args+=(--label-shard "$LABELS/shard-$shard.json"); done
python3 jobs/tools/l3_curriculum_error_loss_first_sibling_labels.py aggregate \
  --selection "$ART/loss-first-selection.json" "${label_args[@]}" --match-seed 2026082344 \
  --report "$ART/loss-first-labels.json" --pairs "$ART/loss-first-matched-pairs.json" >"$W/aggregate.log" 2>&1
python3 - "$ART" "$EXPECTED_CODE_SHA" "$SOURCE_JOB" "$SOURCE_ATTEMPT" "$SOURCE_CODE" <<'PY_FINAL'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); code=sys.argv[2]; report=json.load(open(art/'loss-first-labels.json'))
if report.get('verdict') not in {'JASS_CURRICULUM_ERROR_LOSS_FIRST_LABELS_READY','JASS_CURRICULUM_ERROR_LOSS_FIRST_LABEL_SUPPORT_NOT_ESTABLISHED'}: raise SystemExit('label verdict drift')
for key in ('pattern_eval_fits','production_model_fits','strength_games','new_selfplay_games','frozen_reads'):
 if int(report.get(key,-1))!=0: raise SystemExit(f'accounting drift {key}')
for key in ('anchored_local_refit_authorized','production_model_authorized','strength_gate_authorized','promotion_authorized','automatic_continuation'):
 if report.get(key) is not False: raise SystemExit(f'authorization drift {key}')
payload={**report,'schema':'jass.curriculum_error_loss_first_labels_terminal.v1','code_sha':code,'source':{'job':sys.argv[3],'attempt':sys.argv[4],'code_sha':sys.argv[5]}}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n'); (art/report['verdict']).touch()
for name in ('PATTERNEVAL_FITS__0','PRODUCTION_MODEL_FITS__0','STRENGTH_GAMES__0','NEW_SELFPLAY__0','FROZEN_READS__0','ANCHORED_REFIT_AUTHORIZED__FALSE','PRODUCTION_MODEL_AUTHORIZED__FALSE','STRENGTH_GATE_AUTHORIZED__FALSE','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_CONTINUATION__FALSE'): (art/name).touch()
if report['passed']: (art/'NEXT__loss_first_sparse_jacobian_crossfit_screen').touch()
PY_FINAL
VERDICT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
stage completed
say "$VERDICT target_blind=true d10_d12=true all_legal=true fits=0 force=0"
