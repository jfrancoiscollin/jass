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
PREFLIGHT_JOB="cpx62-2035-l3-cls-l-source-normalization-preflight-v8"
PREFLIGHT_ATTEMPT="20260917T172555Z-13f1c748"
PREFLIGHT_CODE="13f1c748fc088ff4bef5c4779eb3d8733c817041"
PREFLIGHT_ROOT="r2:jass-data/runs/$PREFLIGHT_JOB/$PREFLIGHT_ATTEMPT"
RECOVERY_JOB="cpx62-2040-l3-cls-l-2038-fit-log-diagnostic-v1"
RECOVERY_ATTEMPT="20260918T063103Z-d04b96d8"
RECOVERY_CODE="d04b96d8dd1b2f3b9f4961d706458a74c67022dc"
RECOVERY_ROOT="r2:jass-data/runs/$RECOVERY_JOB/$RECOVERY_ATTEMPT"
RECOVERY_RECEIPT_SHA="879946b1be6dcbcd2cfdaeaa2ba524726c499f247d3153b5ba1885a7ebd84807"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
TURNOVER_CORPUS_SHA="9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
TURNOVER_META_SHA="acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
HOLDOUT_MOD=10; SPLIT_SEED=577215
RECORDS=2000000; TRAIN=1800796; HOLDOUT=199204
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"; PY="$VENV/bin/python"

finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  cp "$RES" "$ART/RESULTS.md" 2>/dev/null || true
  (cd "$W" && find . -maxdepth 1 -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$GEOM" "$W/fit-out" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat "$W"/*.npy "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

[ "$(hostname)" = cpx62 ] || die "host must be cpx62"
[ "$(env -u OMP_NUM_THREADS -u OMP_THREAD_LIMIT nproc)" -eq 16 ] || die "nproc must be 16"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree must be detached and clean"
[ -x "$PY" ] || die "numeric venv missing"
case "$LAUNCH_MODE" in rehearsal|production) ;; *) die "LAUNCH_MODE must be rehearsal or production" ;; esac

say "# CLS-L evidence-gated valid-arm recovery after 2038"
say "job=$JASS_JOB_ID code=$EXPECTED_CODE_SHA mode=$LAUNCH_MODE"
say "science=LOCAL/WDL replay only; MIXED remains TECHNICAL_FAILED at frozen maxiter=2000; fits=2; searches=0 strength_games=0"

# Authenticate the exact historical source, parent, and the successful frozen normalization preflight.
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
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$PREFLIGHT_ROOT" \
  --file artefacts/normalization-receipt.json=normalization-receipt.json \
  --file artefacts/source-authentication.json=preflight-source-authentication.json \
  --file artefacts/scientific-summary.json=preflight-scientific-summary.json \
  --out-dir "$IN" --report "$ART/verified-preflight.json" >"$W/fetch-preflight.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$RECOVERY_ROOT" \
  --file artefacts/scientific-summary.json=recovery-2038-summary.json \
  --file artefacts/launch-receipt.json=recovery-launch-receipt.json \
  --out-dir "$IN" --report "$ART/verified-recovery.json" >"$W/fetch-recovery.log" 2>&1
[ "$(sha256sum "$IN/recovery-launch-receipt.json" | awk '{print $1}')" = "$RECOVERY_RECEIPT_SHA" ] || die "2040 launch receipt SHA drift"

"$PY" - "$ART" "$ABC_JOB" "$ABC_ATTEMPT" "$ABC_CODE" "$TURNOVER_JOB" "$TURNOVER_ATTEMPT" "$TURNOVER_CODE" "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" "$CURRICULUM_CODE" "$PREFLIGHT_JOB" "$PREFLIGHT_ATTEMPT" "$PREFLIGHT_CODE" "$RECOVERY_JOB" "$RECOVERY_ATTEMPT" "$RECOVERY_CODE" <<'PY'
import json,sys
art=sys.argv[1]
items=[
 ('verified-abc.json',sys.argv[2],sys.argv[3],sys.argv[4]),
 ('verified-turnover.json',sys.argv[5],sys.argv[6],sys.argv[7]),
 ('verified-curriculum.json',sys.argv[8],sys.argv[9],sys.argv[10]),
 ('verified-preflight.json',sys.argv[11],sys.argv[12],sys.argv[13]),
 ('verified-recovery.json',sys.argv[14],sys.argv[15],sys.argv[16]),
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

# Reconstruct the exact common production-compatible geometry and FEAT bytes.
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
timeout 7200s "$W/build/jass" --dump-eval-features "$W/current.jnnw" "$W/current.feat" >"$W/features.log" 2>&1

mkdir -p "$W/fit-out"
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools:." PYTHONUNBUFFERED=1 \
  timeout 129600s "$PY" jobs/tools/cls_l_three_arm_fit.py \
    --data "$W/current.jnnw" --feat "$W/current.feat" \
    --local-targets "$W/current-context30.npy" --parent "$W/curriculum.pjtw" \
    --normalization-receipt "$IN/normalization-receipt.json" \
    --recovery-2038-summary "$IN/recovery-2038-summary.json" \
    --out-dir "$W/fit-out" >"$W/fit.log" 2>&1

# Seal all three model bytes and fit receipts. No arm is selected here.
for arm in LOCAL WDL; do
  gzip -n -c "$W/fit-out/$arm.pjtw" >"$ART/$arm.pjtw.gz"
  cp "$W/fit-out/$arm-fit-receipt.json" "$ART/$arm-fit-receipt.json"
done
cp "$W/fit-out/fit-report.json" "$ART/fit-report.json"
cp "$IN/normalization-receipt.json" "$ART/frozen-normalization-receipt.json"

"$PY" - "$ART" "$LAUNCH_MODE" "$EXPECTED_CODE_SHA" "$PREFLIGHT_JOB" "$PREFLIGHT_ATTEMPT" "$PREFLIGHT_CODE" <<'PY'
import hashlib,json,sys
art,mode,code,pjob,patt,pcode=sys.argv[1:]
sha=lambda p:hashlib.sha256(open(p,'rb').read()).hexdigest()
report=json.load(open(f'{art}/fit-report.json'))
if report.get('terminal')!='CLS_L_VALID_ARMS_RECOVERED_V1' or report.get('fits')!=2:
 raise SystemExit('recovery fit terminal/count drift')
if report.get('arm_order') != ['LOCAL','WDL'] or report.get('attribution_complete') is not False:
 raise SystemExit('recovery arm-order/attribution boundary drift')
if report.get('technical_failed_arms') != ['MIXED']:
 raise SystemExit('MIXED technical-failure boundary drift')
rec=report.get('recovery_2038') or {}
if rec.get('max_iterations_unchanged') != 2000 or rec.get('retuning_performed') is not False:
 raise SystemExit('recovery retuning guard drift')
if report.get('strength_games')!=0 or report.get('confirmation_target_reads')!=0 or report.get('promotions')!=0 or report.get('bakes')!=0:
 raise SystemExit('fit side-effect drift')
summary=dict(report)
summary.update({
 'mode':mode,'code_sha':code,'diagnostic_only':False,'scientific_verdict':None,
 'preflight':{'job_id':pjob,'attempt_id':patt,'code_sha':pcode,
              'normalization_receipt_sha256':sha(f'{art}/frozen-normalization-receipt.json')},
 'recovery_2038':report.get('recovery_2038'),
 'production_admitted': mode == 'production',
 'promotion_authorized':False,'bake_authorized':False,
})
open(f'{art}/scientific-summary.json','w').write(json.dumps(summary,indent=2,sort_keys=True)+'\n')
source={
 'schema':'jass.cls_l_three_arm_source_authentication.v1','authenticated':True,
 'preflight_job':pjob,'preflight_attempt':patt,'preflight_code_sha':pcode,
 'verified_abc':json.load(open(f'{art}/verified-abc.json')),
 'verified_turnover':json.load(open(f'{art}/verified-turnover.json')),
 'verified_curriculum':json.load(open(f'{art}/verified-curriculum.json')),
 'verified_preflight':json.load(open(f'{art}/verified-preflight.json')),
 'confirmation_target_reads':0,
}
open(f'{art}/source-authentication.json','w').write(json.dumps(source,indent=2,sort_keys=True)+'\n')
manifest={
 'schema':'jass.cls_l_valid_arms_recovery_manifest.v1','terminal':summary['terminal'],'mode':mode,
 'code_sha':code,'arm_order':['LOCAL','WDL'],'fits':2,'strength_games':0,
 'model_gz_sha256':{a:sha(f'{art}/{a}.pjtw.gz') for a in ('LOCAL','WDL')},
 'technical_failed_arms':['MIXED'],'attribution_complete':False,
 'promotion_authorized':False,'bake_authorized':False,
 'next_stage':'RUN_FROZEN_CLS_G0_PER_TECHNICALLY_VALID_ARM',
}
open(f'{art}/manifest.json','w').write(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
PY

# Emit Launch-V2 execution evidence only after all frozen scientific/model receipts are sealed.
"$PY" - "$ART" "$LAUNCH_MODE" <<'PY'
import sys
from pathlib import Path
from jobs.tools.launch_runtime_v2 import StageEvidence

evidence=StageEvidence(Path(sys.argv[1]),sys.argv[2])
evidence.begin('execute-cls-l-valid-arms-recovery')
evidence.record_effect('fits',2)
evidence.complete()
evidence.finish()
PY

say "terminal=CLS_L_VALID_ARMS_RECOVERED_V1"
say "sealed LOCAL/WDL model bytes; MIXED remains technical-failed at frozen cap; no search, strength, alpha, promotion or bake"
cp "$RES" "$ART/RESULTS.md"
