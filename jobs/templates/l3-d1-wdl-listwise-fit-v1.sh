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
ABC_JOB="cpx62-1340-jass-megacorpus-comparative-fit-v1"
ABC_ATTEMPT="20260814T123246Z-2ce07222"
ABC_CODE="2ce07222f86c1468a1081fbdc53e9e17a0c5326e"
ABC_ROOT="r2:jass-data/runs/$ABC_JOB/$ABC_ATTEMPT"
TURNOVER_JOB="home-0977-l3-pure-turnover1to1-train-v1"
TURNOVER_ATTEMPT="20260726T071254Z-336bb984"
TURNOVER_ROOT="r2:jass-data/runs/$TURNOVER_JOB/$TURNOVER_ATTEMPT"
CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_ROOT="r2:jass-data/runs/$CURRICULUM_JOB/$CURRICULUM_ATTEMPT"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
TURNOVER_CORPUS_SHA="9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
TURNOVER_META_SHA="acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
HOLDOUT_MOD=10; SPLIT_SEED=577215; HOLDOUT=200000
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"; PY="$VENV/bin/python"
FIT_TIMEOUT="${D1_FIT_TIMEOUT_SECONDS:-14400}"

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

say "D1 start job=$JASS_JOB_ID code=$EXPECTED_CODE_SHA science=two_fits_no_games"

# Exact authenticated C dataset; no 1843/full-ladder artifact is fetched.
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$C_ROOT" \
  --file artefacts/sibling-dataset-v2.jsonl=c-dataset.jsonl \
  --file artefacts/sibling-dataset-v2-manifest.json=c-manifest.json \
  --file artefacts/sibling-dataset-v2-validation.json=c-validation.json \
  --file artefacts/scientific-summary.json=c-summary.json \
  --out-dir "$IN" --report "$ART/verified-c.json" >"$W/fetch-c.log" 2>&1

# Frozen CURRENT_2M source/target and CURRICULUM prior.
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$ABC_ROOT" \
  --file artefacts/current_2m-context30.npy.gz=current-context30.npy.gz \
  --file artefacts/current_2m-manifest.json=current-manifest.json \
  --out-dir "$IN" --report "$ART/verified-abc.json" >"$W/fetch-abc.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_ROOT" \
  --file artefacts/turnover1to1.jnnw.gz=turnover.jnnw.gz \
  --file artefacts/turnover1to1.jsm.gz=turnover.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-turnover.json" >"$W/fetch-turnover.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" >"$W/fetch-curriculum.log" 2>&1

"$PY" - "$IN" "$ART" "$C_JOB" "$C_ATTEMPT" "$C_CODE" "$ABC_JOB" "$ABC_ATTEMPT" "$ABC_CODE" <<'PY'
import hashlib,json,sys
root,art,cj,ca,cc,aj,aa,ac=sys.argv[1:]
load=lambda p:json.load(open(p)); sha=lambda p:hashlib.sha256(open(p,'rb').read()).hexdigest()
cv=load(f'{art}/verified-c.json'); cs=load(f'{root}/c-summary.json'); cm=load(f'{root}/c-manifest.json'); vv=load(f'{root}/c-validation.json')
av=load(f'{art}/verified-abc.json')
if (cv.get('job_id'),cv.get('attempt_id'),cv.get('code_sha'),cv.get('result_state'))!=(cj,ca,cc,'completed'): raise SystemExit('C runner identity drift')
if (av.get('job_id'),av.get('attempt_id'),av.get('code_sha'),av.get('result_state'))!=(aj,aa,ac,'completed'): raise SystemExit('ABC runner identity drift')
if cs.get('verdict')!='C_SIBLING_DATASET_V2_AUTHENTICATED_V1' or cs.get('parents')!=4000 or cs.get('actions')!=38053: raise SystemExit('C summary drift')
if cs.get('full_ladder_reference_reads')!=0 or cs.get('reference_backfill') is not False: raise SystemExit('C information barrier drift')
if cm.get('verdict')!='C_SIBLING_DATASET_V2_AUTHENTICATED_V1' or vv.get('verdict')!='C_SIBLING_DATASET_V2_AUTHENTICATED_V1': raise SystemExit('C manifest/validation drift')
if cm.get('dataset',{}).get('sha256')!=sha(f'{root}/c-dataset.jsonl'): raise SystemExit('C dataset hash drift')
if cm.get('information_barrier',{}).get('full_ladder_reference_reads')!=0: raise SystemExit('C manifest reference read drift')
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
[ "$RECORDS" -eq 2000000 ] && [ "$TRAIN" -eq 1800000 ] && [ "$HOLD" -eq "$HOLDOUT" ] || die "CURRENT_2M cardinality drift"
gunzip -c "$IN/current-context30.npy.gz" >"$W/current-context30.npy"
gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
[ "$(sha256sum "$W/curriculum.pjtw" | awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM SHA drift"

# Production 8cf static feature path, dumped once and shared by both arms.
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
J="$W/build/jass"
timeout 7200s "$J" --dump-eval-features "$W/current.jnnw" "$W/current.feat" >"$W/features-current.log" 2>&1

# C children: production-verified child fingerprints only. No teacher score enters D.
"$PY" jobs/tools/d1_decision_prepare.py --dataset "$IN/c-dataset.jsonl" \
  --out-jnnw "$W/decision-children.jnnw" --out-groups "$W/decision-groups.json" \
  --out-receipt "$ART/D1_DECISION_PREPARE.json" >"$W/decision-prepare.log" 2>&1
timeout 1800s "$J" --dump-eval-features "$W/decision-children.jnnw" "$W/decision.feat" >"$W/features-decision.log" 2>&1
cp "$W/decision-groups.json" "$ART/D1_DECISION_GROUPS.json"

# Exactly two frozen fits. The command differs only by --arm/output/report.
for arm in WDL_CONTROL WDL_LISTWISE; do
  timeout "$FIT_TIMEOUT" env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools:." PYTHONUNBUFFERED=1 \
    "$PY" jobs/tools/d1_listwise_fit.py --arm "$arm" \
      --data "$W/current.jnnw" --feat "$W/current.feat" --target-values "$W/current-context30.npy" \
      --prior "$W/curriculum.pjtw" --decision-data "$W/decision-children.jnnw" \
      --decision-feat "$W/decision.feat" --decision-groups "$W/decision-groups.json" \
      --holdout-count "$HOLDOUT" --out "$W/$arm.pjtw" --report "$ART/$arm-fit.json" \
      >"$W/$arm-fit.log" 2>&1
  gzip -n -c "$W/$arm.pjtw" >"$ART/$arm.pjtw.gz"
done

"$PY" - "$ART/WDL_CONTROL-fit.json" "$ART/WDL_LISTWISE-fit.json" "$ART/D1_FIT_PAIR.json" <<'PY'
import json,sys
a,b=(json.load(open(p)) for p in sys.argv[1:3])
if a['objective']!=b['objective']: raise SystemExit('A/B common fit recipe differs')
if a['decision_train']['lambda']!=0.0 or b['decision_train']['lambda']!=1.0: raise SystemExit('D1 treatment lambda drift')
if not a['optimizer']['success'] or not b['optimizer']['success']: raise SystemExit('optimizer did not converge')
p={'schema':'jass.d1.fit_pair.v1','arms':['WDL_CONTROL','WDL_LISTWISE'],'full_fits':2,'only_treatment_difference':'selected_action_listwise_lambda_0_vs_1','strength_games':0,'promotion_authorized':False,'bake_authorized':False}
open(sys.argv[3],'w').write(json.dumps(p,indent=2,sort_keys=True)+'\n')
PY

# Terminal offline readout; C test is consumed here, once both model bytes are sealed.
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools:." \
  "$PY" jobs/tools/d1_postfit_readout.py \
    --wdl-data "$W/current.jnnw" --wdl-feat "$W/current.feat" --target-values "$W/current-context30.npy" \
    --decision-data "$W/decision-children.jnnw" --decision-feat "$W/decision.feat" \
    --decision-groups "$W/decision-groups.json" --control-model "$W/WDL_CONTROL.pjtw" \
    --listwise-model "$W/WDL_LISTWISE.pjtw" --control-report "$ART/WDL_CONTROL-fit.json" \
    --listwise-report "$ART/WDL_LISTWISE-fit.json" --out "$ART/D1_TRANSFER_READOUT.json" \
    >"$W/readout.log" 2>&1
cp "$ART/D1_TRANSFER_READOUT.json" "$ART/scientific-summary.json"
printf '2\n' >"$ART/FULL_FITS__2"
printf '0\n' >"$ART/STRENGTH_GAMES__0"
printf 'FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'FALSE\n' >"$ART/BAKE_AUTHORIZED__FALSE"
VERDICT=$("$PY" - "$ART/D1_TRANSFER_READOUT.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['verdict'])
PY
)
say "D1 terminal verdict=$VERDICT fits=2 strength_games=0 promotion=false bake=false"
