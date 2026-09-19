#!/usr/bin/env bash
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${LAUNCH_MODE:?}"; : "${CLS_HIER_ARM:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"; GEOM="$JASS_RESULT_DIR/geom8"
HIST="$JASS_RESULT_DIR/historical-1341-code"
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
HIST_TRAIN_STREAM_BLOB="12ed5f0f743dadc07ebaab6de1dd9a837297b6c0"
HIST_GEN_PATTERNS_BLOB="af5209654689521032bd56c2c328fd42d160e9d1"
HOLDOUT_MOD=10; SPLIT_SEED=577215; RECORDS=2000000; TRAIN=1800796; HOLDOUT=199204
MAXIT=2000; CHUNK=20000; L2="1e-5"; HIER_L2="1e-5"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"; PY="$VENV/bin/python"

finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  cp "$RES" "$ART/RESULTS.md" 2>/dev/null || true
  (cd "$W" && find . -maxdepth 1 -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$GEOM" "$HIST" 2>/dev/null || true
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
case "$CLS_HIER_ARM" in CONTROL|HIER) ;; *) die "CLS_HIER_ARM must be CONTROL or HIER" ;; esac

say "# CLS HIER-L2 next-candidate stage"
say "job=$JASS_JOB_ID code=$EXPECTED_CODE_SHA mode=$LAUNCH_MODE arm=$CLS_HIER_ARM"
say "science=one fit only; l2=1e-5; CONTROL hier_l2=0; HIER hier_l2=1e-5; searches=0 strength_games=0 alpha=0 promotion=0 bake=0"

# HIER is inadmissible until an exact CONTROL production has already reproduced CURRICULUM.
if [ "$CLS_HIER_ARM" = HIER ]; then
  : "${CLS_HIER_CONTROL_ROOT:?HIER requires authenticated CONTROL production root}"
  : "${CLS_HIER_CONTROL_JOB:?}"; : "${CLS_HIER_CONTROL_ATTEMPT:?}"; : "${CLS_HIER_CONTROL_CODE:?}"
  timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CLS_HIER_CONTROL_ROOT" \
    --file artefacts/scientific-summary.json=control-summary.json \
    --file artefacts/model.pjtw.gz=control-model.pjtw.gz \
    --out-dir "$IN" --report "$ART/verified-control-production.json" >"$W/fetch-control.log" 2>&1
  "$PY" - "$ART/verified-control-production.json" "$IN/control-summary.json" \
    "$CLS_HIER_CONTROL_JOB" "$CLS_HIER_CONTROL_ATTEMPT" "$CLS_HIER_CONTROL_CODE" "$CURRICULUM_SHA" <<'PY'
import json,sys
verify=json.load(open(sys.argv[1])); summary=json.load(open(sys.argv[2]))
want=(sys.argv[3],sys.argv[4],sys.argv[5],'completed')
got=(verify.get('job_id'),verify.get('attempt_id'),verify.get('code_sha'),verify.get('result_state'))
if got != want: raise SystemExit(f'CONTROL production identity drift: {got}')
if summary.get('terminal') != 'CLS_HIER_CONTROL_REPRODUCTION_READY_V1':
 raise SystemExit('CONTROL production terminal drift')
if summary.get('arm') != 'CONTROL' or summary.get('model_sha256') != sys.argv[6]:
 raise SystemExit('CONTROL production byte identity drift')
PY
fi

# Authenticate exact historical sources and the immutable production parent.
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$ABC_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=abc-summary.json \
  --file artefacts/mega_full_4m.pjtw.gz=C.pjtw.gz \
  --file artefacts/current_2m-context30.npy.gz=current-context30.npy.gz \
  --file artefacts/current_2m-manifest.json=current-manifest.json \
  --file artefacts/current_2m-conditional-targets.json=current-targets.json \
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
items=[('verified-abc.json',sys.argv[2],sys.argv[3],sys.argv[4]),
       ('verified-turnover.json',sys.argv[5],sys.argv[6],sys.argv[7]),
       ('verified-curriculum.json',sys.argv[8],sys.argv[9],sys.argv[10])]
for name,job,attempt,code in items:
 d=json.load(open(f'{art}/{name}'))
 got=(d.get('job_id'),d.get('attempt_id'),d.get('code_sha'),d.get('result_state'))
 if got != (job,attempt,code,'completed'): raise SystemExit(f'{name} identity drift: {got}')
PY

gunzip -c "$IN/turnover.jnnw.gz" >"$W/turnover.raw.jnnw"
gunzip -c "$IN/turnover.jsm.gz" >"$W/turnover.raw.jsm"
gunzip -c "$IN/C.pjtw.gz" >"$W/C.pjtw"
gunzip -c "$IN/current-context30.npy.gz" >"$W/current-context30.npy"
gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
[ "$(sha256sum "$W/turnover.raw.jnnw" | awk '{print $1}')" = "$TURNOVER_CORPUS_SHA" ] || die "TURNOVER corpus SHA drift"
[ "$(sha256sum "$W/turnover.raw.jsm" | awk '{print $1}')" = "$TURNOVER_META_SHA" ] || die "TURNOVER metadata SHA drift"
[ "$(sha256sum "$W/curriculum.pjtw" | awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM SHA drift"
"$PY" - "$IN/abc-summary.json" "$W/C.pjtw" <<'PY'
import hashlib,json,sys
summary=json.load(open(sys.argv[1])); raw=open(sys.argv[2],'rb').read(); got=hashlib.sha256(raw).hexdigest()
arm=(summary.get('arms') or {}).get('MEGA_FULL_4M') or {}
if got != arm.get('model_raw_sha256'): raise SystemExit('MEGA_FULL_4M C model SHA drift')
recipe=summary.get('fixed_recipe') or {}
want=('8cf_exact_fold_tempo_120_extras','CONTEXT_30_ALIGNED_alpha_0.30',1e-5,2000)
got_recipe=(recipe.get('architecture'),recipe.get('target'),recipe.get('l2'),recipe.get('max_iterations'))
if got_recipe != want: raise SystemExit(f'1340 fixed recipe drift: {got_recipe}')
PY

# 2051 proved that the current-code CONTROL path does not reproduce 1341 bytes.
# The preregistration requires the historical 1341 recipe mechanics, not a newer
# feature/trainer implementation. Materialize that exact code tree and use it for
# BOTH CONTROL and HIER; the sole fit-axis difference remains --hier-l2 1e-5.
rm -rf "$HIST"; mkdir -p "$HIST"
git cat-file -e "${CURRICULUM_CODE}^{commit}" || die "historical 1341 commit unavailable"
[ "$(git rev-parse "$CURRICULUM_CODE:pattern_jass/tools/train_stream.py")" = "$HIST_TRAIN_STREAM_BLOB" ] || die "historical train_stream blob drift"
[ "$(git rev-parse "$CURRICULUM_CODE:pattern_jass/tools/gen_patterns.py")" = "$HIST_GEN_PATTERNS_BLOB" ] || die "historical gen_patterns blob drift"
git archive --format=tar "$CURRICULUM_CODE" | tar -xf - -C "$HIST"
[ -f "$HIST/pattern_jass/tools/train_stream.py" ] || die "historical trainer missing after archive"
[ -f "$HIST/tools/selfplay_frontier.py" ] || die "historical split tool missing after archive"
grep -Fq -- "--hier-l2" "$HIST/pattern_jass/tools/train_stream.py" || die "historical trainer lacks preregistered hier-l2 support"
"$PY" - "$ART/runtime-authentication.json" "$CURRICULUM_CODE" "$HIST_TRAIN_STREAM_BLOB" "$HIST_GEN_PATTERNS_BLOB" <<'PY'
import json,platform,sys
import numpy,scipy
out,code,trainer_blob,patterns_blob=sys.argv[1:]
payload={
 'schema':'jass.cls_hier_l2_runtime_authentication.v1',
 'historical_recipe_code_sha':code,
 'historical_train_stream_blob_sha':trainer_blob,
 'historical_gen_patterns_blob_sha':patterns_blob,
 'python':sys.version,
 'python_executable':sys.executable,
 'platform':platform.platform(),
 'numpy':numpy.__version__,
 'scipy':scipy.__version__,
}
open(out,'w').write(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY

# Reproduce the exact CURRENT_2M split and feature geometry with the authoritative
# 1341 code, then use the same historical trainer in both arms.
python3 "$HIST/tools/selfplay_frontier.py" split --data "$W/turnover.raw.jnnw" --meta "$W/turnover.raw.jsm" \
  --out-data "$W/current.jnnw" --out-meta "$W/current.jsm" --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$W/current-manifest-reproduced.json" >"$W/split.log" 2>&1
cmp "$W/current-manifest-reproduced.json" "$IN/current-manifest.json" || die "CURRENT_2M split/manifest drift"
read -r NR NT NH < <("$PY" - "$IN/current-manifest.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); print(d['records'],d['train_records'],d['holdout_records'])
PY
)
[ "$NR" -eq "$RECORDS" ] && [ "$NT" -eq "$TRAIN" ] && [ "$NH" -eq "$HOLDOUT" ] || die "CURRENT_2M cardinality drift"

(cd "$HIST" && python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1)
cp "$HIST/pattern_jass/tools/patterns.py" "$GEOM/patterns.py"
cmake -S "$HIST" -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
timeout 7200s "$W/build/jass" --dump-eval-features "$W/current.jnnw" "$W/current.feat" >"$W/features.log" 2>&1

HIER_ARGS=()
[ "$CLS_HIER_ARM" = CONTROL ] || HIER_ARGS=(--hier-l2 "$HIER_L2")
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:$HIST/pattern_jass/tools:$HIST" PYTHONUNBUFFERED=1 \
  timeout 14400s "$PY" "$HIST/pattern_jass/tools/train_stream.py" \
    --data "$W/current.jnnw" --feat "$W/current.feat" --out "$W/model.pjtw" \
    --target external --target-values "$W/current-context30.npy" \
    --targets-report "$ART/target-consumption.json" \
    --loss logistic --exact-fold --tempo-stage \
    --prior-mean "$W/C.pjtw" --prior-decay 0 \
    --holdout-count "$HOLDOUT" --l2 "$L2" --max-iter "$MAXIT" \
    --chunk "$CHUNK" --lbfgs-maxcor 20 --lbfgs-gtol 1e-4 --prune \
    "${HIER_ARGS[@]}" --optimizer-report "$ART/optimizer.json" >"$W/fit.log" 2>&1
[ -s "$W/model.pjtw" ] || die "fit produced no PJTW"
"$PY" jobs/tools/verify_optimizer_convergence.py --report "$ART/optimizer.json" --label "$CLS_HIER_ARM" \
  --expected-max-iterations "$MAXIT" --expected-maxcor 20 --expected-gtol 1e-4 --receipt "$ART/fit-receipt.json"
MODEL_SHA="$(sha256sum "$W/model.pjtw" | awk '{print $1}')"
if [ "$CLS_HIER_ARM" = CONTROL ] && [ "$MODEL_SHA" != "$CURRICULUM_SHA" ]; then
  die "CONTROL_BYTE_IDENTITY_MISMATCH actual=$MODEL_SHA expected=$CURRICULUM_SHA"
fi
gzip -n -c "$W/model.pjtw" >"$ART/model.pjtw.gz"

"$PY" - "$ART" "$IN" "$CLS_HIER_ARM" "$LAUNCH_MODE" "$EXPECTED_CODE_SHA" "$MODEL_SHA" "$CURRICULUM_SHA" "$CURRICULUM_CODE" <<'PY'
import hashlib,json,sys
art,inp,arm,mode,code,model_sha,parent_sha,historical_code=sys.argv[1:]
sha=lambda p:hashlib.sha256(open(p,'rb').read()).hexdigest()
terminal='CLS_HIER_CONTROL_REPRODUCTION_READY_V1' if arm=='CONTROL' else 'CLS_HIER_CANDIDATE_FIT_READY_V1'
summary={
 'schema':'jass.cls_hier_l2_next_candidate.v1','state':'completed','terminal':terminal,
 'arm':arm,'mode':mode,'code_sha':code,'historical_recipe_code_sha':historical_code,'model_sha256':model_sha,
 'direct_parent_sha256':parent_sha,'fixed_curriculum_anchor_sha256':parent_sha,
 'varied_factor':'hier_l2','l2':1e-5,'hier_l2':0.0 if arm=='CONTROL' else 1e-5,
 'fits':1,'target_reads':0,'confirmation_target_reads':0,'new_jass_searches':0,'new_scan_searches':0,
 'selfplay_games':0,'strength_games':0,'alpha_spent':0,'promotions':0,'bakes':0,
 'promotion_authorized':False,'bake_authorized':False,
 'next_stage':'FIT_HIER_AFTER_CONTROL_PRODUCTION' if arm=='CONTROL' else 'RUN_FROZEN_CLS_G0',
}
open(f'{art}/scientific-summary.json','w').write(json.dumps(summary,indent=2,sort_keys=True)+'\n')
source={
 'schema':'jass.cls_hier_l2_source_authentication.v1','authenticated':True,
 'verified_abc':json.load(open(f'{art}/verified-abc.json')),
 'verified_turnover':json.load(open(f'{art}/verified-turnover.json')),
 'verified_curriculum':json.load(open(f'{art}/verified-curriculum.json')),
 'curriculum_sha256':parent_sha,
 'historical_recipe_code_sha':historical_code,
 'runtime_authentication_sha256':sha(f'{art}/runtime-authentication.json'),
 'current_manifest_sha256':sha(f'{inp}/current-manifest.json'),
 'context30_gzip_sha256':sha(f'{inp}/current-context30.npy.gz'),
 'confirmation_target_reads':0,
}
if arm=='HIER': source['verified_control_production']=json.load(open(f'{art}/verified-control-production.json'))
open(f'{art}/source-authentication.json','w').write(json.dumps(source,indent=2,sort_keys=True)+'\n')
manifest={
 'schema':'jass.cls_hier_l2_manifest.v1','arm':arm,'model_raw_sha256':model_sha,
 'model_gzip_sha256':sha(f'{art}/model.pjtw.gz'),'fit_receipt_sha256':sha(f'{art}/fit-receipt.json'),
 'source_authentication_sha256':sha(f'{art}/source-authentication.json'),
 'runtime_authentication_sha256':sha(f'{art}/runtime-authentication.json'),
}
open(f'{art}/manifest.json','w').write(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
PY

# 2059 completed the frozen CONTROL fit and sealed every scientific output, but
# Launch-V2 rejected the run at OUTPUTS because this direct shell stage omitted
# its required execution-evidence.json. Record exactly the completed fit phase
# only after all frozen scientific outputs have been sealed.
"$PY" - "$ART" "$LAUNCH_MODE" <<'PY'
import sys
from pathlib import Path
from jobs.tools.launch_runtime_v2 import StageEvidence

evidence = StageEvidence(Path(sys.argv[1]), sys.argv[2])
evidence.begin('execute-cls-hier-l2-next-candidate')
evidence.record_effect('fits', 1)
evidence.complete()
evidence.finish()
PY

say "terminal=$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["terminal"])' "$ART/scientific-summary.json")"
say "model_sha256=$MODEL_SHA"
