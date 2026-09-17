#!/usr/bin/env bash
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${LAUNCH_MODE:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"; GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$IN" "$ART" "$GEOM"
RES="$W/RESULTS.md"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }

ABC_JOB="cpx62-1340-jass-megacorpus-comparative-fit-v1"
ABC_ATTEMPT="20260814T123246Z-2ce07222"
ABC_CODE="2ce07222f86c1468a1081fbdc53e9e17a0c5326e"
ABC_ROOT="r2:jass-data/runs/$ABC_JOB/$ABC_ATTEMPT"
TURNOVER_JOB="home-0977-l3-pure-turnover1to1-train-v1"
TURNOVER_ATTEMPT="20260726T071254Z-336bb984"
TURNOVER_CODE="336bb98451a205266d6646c4d801027af4b30294"
TURNOVER_ROOT="r2:jass-data/runs/$TURNOVER_JOB/$TURNOVER_ATTEMPT"
CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE="18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_ROOT="r2:jass-data/runs/$CURRICULUM_JOB/$CURRICULUM_ATTEMPT"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
TURNOVER_CORPUS_SHA="9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
TURNOVER_META_SHA="acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
HOLDOUT_MOD=10; SPLIT_SEED=577215
RECORDS=2000000; TRAIN=1800796; HOLDOUT=199204
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"; PY="$VENV/bin/python"

finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  cp "$RES" "$ART/RESULTS.md" 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat "$W"/*.npy "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

[ "$(hostname)" = cpx62 ] || die "host must be cpx62"
[ "$(nproc)" -eq 16 ] || die "nproc must be 16"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree must be detached and clean"
[ -x "$PY" ] || die "numeric venv missing"
[ "$LAUNCH_MODE" = rehearsal ] || die "CLS-L normalization preflight is rehearsal-only"

say "# CLS-L source / normalization preflight"
say "job=$JASS_JOB_ID code=$EXPECTED_CODE_SHA mode=$LAUNCH_MODE"
say "science=frozen CURRENT_2M + CURRICULUM; fits=0 searches=0 strength_games=0"

# Fetch only the exact historical training source, aligned LOCAL target and parent.
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$ABC_ROOT" \
  --file artefacts/current_2m-context30.npy.gz=current-context30.npy.gz \
  --file artefacts/current_2m-manifest.json=current-manifest.json \
  --file artefacts/current_2m-conditional-targets.json=current-conditional-targets.json \
  --out-dir "$IN" --report "$ART/verified-abc.json" >"$W/fetch-abc.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_ROOT" \
  --file artefacts/turnover1to1.jnnw.gz=turnover.jnnw.gz \
  --file artefacts/turnover1to1.jsm.gz=turnover.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-turnover.json" >"$W/fetch-turnover.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" >"$W/fetch-curriculum.log" 2>&1

"$PY" - "$ART" "$ABC_JOB" "$ABC_ATTEMPT" "$ABC_CODE" "$TURNOVER_JOB" "$TURNOVER_ATTEMPT" "$TURNOVER_CODE" "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" "$CURRICULUM_CODE" <<'PY'
import json,sys
art=sys.argv[1]
items=[
 ('verified-abc.json',sys.argv[2],sys.argv[3],sys.argv[4]),
 ('verified-turnover.json',sys.argv[5],sys.argv[6],sys.argv[7]),
 ('verified-curriculum.json',sys.argv[8],sys.argv[9],sys.argv[10]),
]
for name,job,attempt,code in items:
 d=json.load(open(f'{art}/{name}'))
 got=(d.get('job_id'),d.get('attempt_id'),d.get('code_sha'),d.get('result_state'))
 if got!=(job,attempt,code,'completed'):
  raise SystemExit(f'{name} identity drift: {got}')
PY

gunzip -c "$IN/turnover.jnnw.gz" >"$W/turnover.raw.jnnw"
gunzip -c "$IN/turnover.jsm.gz" >"$W/turnover.raw.jsm"
[ "$(sha256sum "$W/turnover.raw.jnnw" | awk '{print $1}')" = "$TURNOVER_CORPUS_SHA" ] || die "TURNOVER corpus SHA drift"
[ "$(sha256sum "$W/turnover.raw.jsm" | awk '{print $1}')" = "$TURNOVER_META_SHA" ] || die "TURNOVER meta SHA drift"
python3 tools/selfplay_frontier.py split --data "$W/turnover.raw.jnnw" --meta "$W/turnover.raw.jsm" \
  --out-data "$W/current.jnnw" --out-meta "$W/current.jsm" --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$W/current-manifest-reproduced.json" >"$W/split.log" 2>&1
cmp "$W/current-manifest-reproduced.json" "$IN/current-manifest.json" || die "CURRENT_2M split/manifest drift"
read -r NR NT NH < <("$PY" - "$IN/current-manifest.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); print(d['records'],d['train_records'],d['holdout_records'])
PY
)
[ "$NR" -eq "$RECORDS" ] && [ "$NT" -eq "$TRAIN" ] && [ "$NH" -eq "$HOLDOUT" ] || die "CURRENT_2M cardinality drift"

gunzip -c "$IN/current-context30.npy.gz" >"$W/current-context30.npy"
gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
[ "$(sha256sum "$W/curriculum.pjtw" | awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM SHA drift"

# Production-compatible 8cf exact-fold/tempo representation; feature extraction is evaluation only, not search.
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
timeout 7200s "$W/build/jass" --dump-eval-features "$W/current.jnnw" "$W/current.feat" >"$W/features.log" 2>&1

env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools:." PYTHONUNBUFFERED=1 \
  "$PY" jobs/tools/cls_l_normalization_preflight.py \
    --data "$W/current.jnnw" --feat "$W/current.feat" \
    --local-targets "$W/current-context30.npy" --parent "$W/curriculum.pjtw" \
    --out "$ART/normalization-receipt.json" >"$W/normalization.log" 2>&1

"$PY" - "$ART" "$W" "$ABC_JOB" "$ABC_ATTEMPT" "$ABC_CODE" "$TURNOVER_JOB" "$TURNOVER_ATTEMPT" "$TURNOVER_CODE" "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" "$CURRICULUM_CODE" "$EXPECTED_CODE_SHA" <<'PY'
import hashlib,json,sys
art,w=sys.argv[1:3]
abcj,abca,abcc,tj,ta,tc,cj,ca,cc,code=sys.argv[3:]
sha=lambda p:hashlib.sha256(open(p,'rb').read()).hexdigest()
receipt=json.load(open(f'{art}/normalization-receipt.json'))
if receipt.get('terminal')!='CLS_L_SOURCE_NORMALIZATION_PREFLIGHT_READY_V1': raise SystemExit('normalization terminal drift')
if receipt.get('fits')!=0 or receipt.get('strength_games')!=0 or receipt.get('confirmation_target_reads')!=0: raise SystemExit('preflight side-effect drift')
source={
 'schema':'jass.cls_l_source_authentication.v1','authenticated':True,
 'abc':{'job_id':abcj,'attempt_id':abca,'code_sha':abcc,'receipt':json.load(open(f'{art}/verified-abc.json'))},
 'turnover':{'job_id':tj,'attempt_id':ta,'code_sha':tc,'receipt':json.load(open(f'{art}/verified-turnover.json'))},
 'curriculum':{'job_id':cj,'attempt_id':ca,'code_sha':cc,'receipt':json.load(open(f'{art}/verified-curriculum.json'))},
 'reproduced_current_manifest_sha256':sha(f'{w}/current-manifest-reproduced.json'),
 'training_target_sidecars_read':1,'confirmation_target_reads':0,
}
open(f'{art}/source-authentication.json','w').write(json.dumps(source,indent=2,sort_keys=True)+'\n')
summary=dict(receipt)
summary.update({'mode':'rehearsal','diagnostic_only':True,'scientific_verdict':None,'target_reads':0,'candidate_reads':0,'control_evaluations':0,'next_stage':'IMPLEMENT_CLS_L_THREE_ARM_FIT_HARNESS','code_sha':code})
open(f'{art}/scientific-summary.json','w').write(json.dumps(summary,indent=2,sort_keys=True)+'\n')
manifest={'schema':'jass.cls_l_source_normalization_manifest.v1','terminal':summary['terminal'],'mode':'rehearsal','code_sha':code,'source_jobs':[abcj,tj,cj],'records':summary['records'],'train_records':summary['train_records'],'holdout_records':summary['holdout_records'],'fits':0,'strength_games':0,'promotion_authorized':False,'bake_authorized':False}
open(f'{art}/manifest.json','w').write(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
PY

say "terminal=CLS_L_SOURCE_NORMALIZATION_PREFLIGHT_READY_V1"
say "sealed TRAIN-only LOCAL/WDL gradient norms at projected CURRICULUM; no fit, search, strength, alpha, promotion or bake"
cp "$RES" "$ART/RESULTS.md"
