#!/usr/bin/env bash
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"; GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$IN" "$ART" "$GEOM"
RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }

C_JOB="cpx62-1845-l3-decision-math-c-sibling-dataset-v2-v1"
C_ATTEMPT="20260906T191758Z-4ae3fca8"
C_CODE="4ae3fca82f19338132911811978761b91bd39573"
C_ROOT="r2:jass-data/runs/$C_JOB/$C_ATTEMPT"
D1_JOB="cpx62-1849-l3-decision-math-d1-wdl-listwise-fit-stage-env-recovery-requeue-v1"
D1_ATTEMPT="20260906T222203Z-08fd187a"
D1_CODE="08fd187aa187f26bd7179df2c68056a74e28355d"
D1_ROOT="r2:jass-data/runs/$D1_JOB/$D1_ATTEMPT"
ABC_JOB="cpx62-1340-jass-megacorpus-comparative-fit-v1"
ABC_ATTEMPT="20260814T123246Z-2ce07222"
ABC_CODE="2ce07222f86c1468a1081fbdc53e9e17a0c5326e"
ABC_ROOT="r2:jass-data/runs/$ABC_JOB/$ABC_ATTEMPT"
TURNOVER_JOB="home-0977-l3-pure-turnover1to1-train-v1"
TURNOVER_ATTEMPT="20260726T071254Z-336bb984"
TURNOVER_ROOT="r2:jass-data/runs/$TURNOVER_JOB/$TURNOVER_ATTEMPT"
TURNOVER_CORPUS_SHA="9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
TURNOVER_META_SHA="acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
HOLDOUT_MOD=10; SPLIT_SEED=577215
HOLDOUT=199204; TRAIN_EXPECTED=1800796; RECORDS_EXPECTED=2000000
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"; PY="$VENV/bin/python"
FIT_TIMEOUT="${D2_FIT_TIMEOUT_SECONDS:-14400}"

finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  (cd "$W" && find . -maxdepth 1 -name '*.log' -type f -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat "$W"/*.npy "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX62 contract mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree must be detached and clean"
[ -x "$PY" ] || die "numeric venv missing: $PY"

say "D2 start job=$JASS_JOB_ID code=$EXPECTED_CODE_SHA science=one_240d_fit_no_games"
say "CURRENT historical split records=$RECORDS_EXPECTED train=$TRAIN_EXPECTED holdout=$HOLDOUT mod=$HOLDOUT_MOD seed=$SPLIT_SEED"

# Authenticated C dataset. No 1843/full-ladder artefact is fetched.
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$C_ROOT" \
  --file artefacts/sibling-dataset-v2.jsonl=c-dataset.jsonl \
  --file artefacts/sibling-dataset-v2-manifest.json=c-manifest.json \
  --file artefacts/sibling-dataset-v2-validation.json=c-validation.json \
  --file artefacts/scientific-summary.json=c-summary.json \
  --out-dir "$IN" --report "$ART/verified-c.json" >"$W/fetch-c.log" 2>&1

# Exact sealed WDL_CONTROL base from terminal D1.
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$D1_ROOT" \
  --file artefacts/WDL_CONTROL.pjtw.gz=wdl-control.pjtw.gz \
  --file artefacts/WDL_CONTROL-fit.json=wdl-control-fit.json \
  --file artefacts/D1_TRANSFER_READOUT.json=d1-readout.json \
  --file artefacts/scientific-summary.json=d1-summary.json \
  --out-dir "$IN" --report "$ART/verified-d1.json" >"$W/fetch-d1.log" 2>&1

# Frozen CURRENT_2M source and target.
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$ABC_ROOT" \
  --file artefacts/current_2m-context30.npy.gz=current-context30.npy.gz \
  --file artefacts/current_2m-manifest.json=current-manifest.json \
  --out-dir "$IN" --report "$ART/verified-abc.json" >"$W/fetch-abc.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_ROOT" \
  --file artefacts/turnover1to1.jnnw.gz=turnover.jnnw.gz \
  --file artefacts/turnover1to1.jsm.gz=turnover.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-turnover.json" >"$W/fetch-turnover.log" 2>&1

"$PY" - "$IN" "$ART" "$C_JOB" "$C_ATTEMPT" "$C_CODE" "$D1_JOB" "$D1_ATTEMPT" "$D1_CODE" "$ABC_JOB" "$ABC_ATTEMPT" "$ABC_CODE" <<'PY'
import hashlib,json,sys
root,art,cj,ca,cc,dj,da,dc,aj,aa,ac=sys.argv[1:]
load=lambda p:json.load(open(p)); sha=lambda p:hashlib.sha256(open(p,'rb').read()).hexdigest()
cv=load(f'{art}/verified-c.json'); dv=load(f'{art}/verified-d1.json'); av=load(f'{art}/verified-abc.json')
cs=load(f'{root}/c-summary.json'); cm=load(f'{root}/c-manifest.json'); vv=load(f'{root}/c-validation.json'); ds=load(f'{root}/d1-summary.json')
if (cv.get('job_id'),cv.get('attempt_id'),cv.get('code_sha'),cv.get('result_state'))!=(cj,ca,cc,'completed'): raise SystemExit('C runner identity drift')
if (dv.get('job_id'),dv.get('attempt_id'),dv.get('code_sha'),dv.get('result_state'))!=(dj,da,dc,'completed'): raise SystemExit('D1 runner identity drift')
if (av.get('job_id'),av.get('attempt_id'),av.get('code_sha'),av.get('result_state'))!=(aj,aa,ac,'completed'): raise SystemExit('ABC runner identity drift')
if cs.get('verdict')!='C_SIBLING_DATASET_V2_AUTHENTICATED_V1' or cs.get('parents')!=4000 or cs.get('actions')!=38053: raise SystemExit('C summary drift')
if cs.get('full_ladder_reference_reads')!=0 or cs.get('reference_backfill') is not False: raise SystemExit('C information barrier drift')
if cm.get('verdict')!='C_SIBLING_DATASET_V2_AUTHENTICATED_V1' or vv.get('verdict')!='C_SIBLING_DATASET_V2_AUTHENTICATED_V1': raise SystemExit('C manifest/validation drift')
if cm.get('dataset',{}).get('sha256')!=sha(f'{root}/c-dataset.jsonl'): raise SystemExit('C dataset hash drift')
if ds.get('verdict')!='D1_DECISION_TRANSFER_NOT_ESTABLISHED_V1' or ds.get('equal_node_gate_authorized') is not False or ds.get('next_stage')!='STOP': raise SystemExit('D1 terminal contract drift')
PY

gunzip -c "$IN/turnover.jnnw.gz" >"$W/turnover.raw.jnnw"
gunzip -c "$IN/turnover.jsm.gz" >"$W/turnover.raw.jsm"
[ "$(sha256sum "$W/turnover.raw.jnnw" | awk '{print $1}')" = "$TURNOVER_CORPUS_SHA" ] || die "TURNOVER corpus drift"
[ "$(sha256sum "$W/turnover.raw.jsm" | awk '{print $1}')" = "$TURNOVER_META_SHA" ] || die "TURNOVER meta drift"
python3 tools/selfplay_frontier.py split --data "$W/turnover.raw.jnnw" --meta "$W/turnover.raw.jsm" \
  --out-data "$W/current.jnnw" --out-meta "$W/current.jsm" --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$W/current-manifest-reproduced.json" >"$W/split.log" 2>&1
cmp "$W/current-manifest-reproduced.json" "$IN/current-manifest.json" || die "CURRENT split drift"
read -r RECORDS TRAIN HOLD < <("$PY" - "$IN/current-manifest.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); print(d['records'],d['train_records'],d['holdout_records'])
PY
)
[ "$RECORDS" -eq "$RECORDS_EXPECTED" ] && [ "$TRAIN" -eq "$TRAIN_EXPECTED" ] && [ "$HOLD" -eq "$HOLDOUT" ] || die "CURRENT_2M cardinality drift"
gunzip -c "$IN/current-context30.npy.gz" >"$W/current-context30.npy"
gunzip -c "$IN/wdl-control.pjtw.gz" >"$W/wdl-control.pjtw"

"$PY" - "$W/wdl-control.pjtw" "$ART/D2_BASE_AUTH.json" "$D1_JOB" "$D1_ATTEMPT" <<'PY'
import hashlib,json,struct,sys
p,out,job,attempt=sys.argv[1:]
raw=open(p,'rb').read(); h=hashlib.sha256(raw).hexdigest()
magic,version,scale,npat,next_=struct.unpack_from('<IIIII',raw,0)
if magic!=0x57544A50 or (version&0xff)!=3 or scale!=1000 or next_!=120: raise SystemExit('WDL_CONTROL PJTW layout drift')
r={'schema':'jass.d2.base_auth.v1','source_job':job,'source_attempt':attempt,'base_sha256':h,'n_patterns':npat,'n_extras':next_,'scale':scale,'valid_test_reads':0,'wdl_holdout_reads':0}
open(out,'w').write(json.dumps(r,indent=2,sort_keys=True)+'\n')
PY

# Production feature path shared by WDL and C children.
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
J="$W/build/jass"
timeout 7200s "$J" --dump-eval-features "$W/current.jnnw" "$W/current.feat" >"$W/features-current.log" 2>&1

"$PY" jobs/tools/d2_decision_prepare.py --dataset "$IN/c-dataset.jsonl" \
  --out-jnnw "$W/decision-children.jnnw" --out-groups "$W/d2-groups.json" \
  --out-receipt "$ART/D2_DECISION_PREPARE.json" >"$W/d2-prepare.log" 2>&1
timeout 1800s "$J" --dump-eval-features "$W/decision-children.jnnw" "$W/decision.feat" >"$W/features-decision.log" 2>&1
cp "$W/d2-groups.json" "$ART/D2_DECISION_GROUPS.json"

# One raw 240-parameter residual fit + WDL-train-only feasibility projection.
timeout "$FIT_TIMEOUT" env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools:." PYTHONUNBUFFERED=1 \
  "$PY" jobs/tools/d2_constrained_dense_residual_fit.py \
    --wdl-data "$W/current.jnnw" --wdl-feat "$W/current.feat" --target-values "$W/current-context30.npy" \
    --base-model "$W/wdl-control.pjtw" --decision-data "$W/decision-children.jnnw" \
    --decision-feat "$W/decision.feat" --decision-groups "$W/d2-groups.json" --holdout-count "$HOLDOUT" \
    --out "$W/D2.pjtw" --report "$ART/D2_FIT_REPORT.json" --seal "$ART/D2_CANDIDATE_SEAL.json" \
    >"$W/d2-fit.log" 2>&1
gzip -n -c "$W/D2.pjtw" >"$ART/D2.pjtw.gz"

# Heldout data is first consumed only after the candidate seal exists.
[ -s "$ART/D2_CANDIDATE_SEAL.json" ] || die "candidate seal missing"
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools:." \
  "$PY" jobs/tools/d2_constrained_dense_residual_readout.py \
    --wdl-data "$W/current.jnnw" --wdl-feat "$W/current.feat" --target-values "$W/current-context30.npy" \
    --decision-data "$W/decision-children.jnnw" --decision-feat "$W/decision.feat" --decision-groups "$W/d2-groups.json" \
    --base-model "$W/wdl-control.pjtw" --candidate-model "$W/D2.pjtw" \
    --fit-report "$ART/D2_FIT_REPORT.json" --seal "$ART/D2_CANDIDATE_SEAL.json" \
    --out "$ART/D2_TRANSFER_READOUT.json" >"$W/d2-readout.log" 2>&1
cp "$ART/D2_TRANSFER_READOUT.json" "$ART/scientific-summary.json"
printf '1\n' >"$ART/FITS__1"
printf '0\n' >"$ART/MODEL_SEARCHES__0"
printf '0\n' >"$ART/TEACHER_SEARCHES__0"
printf '0\n' >"$ART/STRENGTH_GAMES__0"
printf 'FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'FALSE\n' >"$ART/BAKE_AUTHORIZED__FALSE"
VERDICT=$("$PY" - "$ART/D2_TRANSFER_READOUT.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['verdict'])
PY
)
say "D2 terminal verdict=$VERDICT fits=1 strength_games=0 promotion=false bake=false"
