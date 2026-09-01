#!/usr/bin/env bash
# JFI-A/B: seven physical full fits on one frozen CURRENT_2M/Context30 design.
# D is also the lambda=1e-5 zero-centred arm. No force, fresh data or Scan read.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${BOUNDARY_ROOT:?}"; : "${EXPECTED_BOUNDARY_JOB:?}"; : "${EXPECTED_BOUNDARY_ATTEMPT:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"; mkdir -p "$W" "$IN" "$ART" "$GEOM"
RES="$W/RESULTS.txt"; STAGE="$W/.stage"; : >"$RES"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

TURNOVER_ROOT="r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984"
ABC_ROOT="r2:jass-data/runs/cpx62-1340-jass-megacorpus-comparative-fit-v1/20260814T123246Z-2ce07222"
CURRICULUM_ROOT="r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/20260814T191555Z-18c38a33"
TURNOVER_SHA="9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
TURNOVER_META_SHA="acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
SPLIT_SEED=577215; EXPECTED_RECORDS=2000000; EXPECTED_EXTRAS=120
MAXIT=2000; MAXCOR=20; GTOL=1e-4; CHUNK=20000
BOOTSTRAP_SAMPLES=100000; BOOTSTRAP_SEED=2026120101
FIT_TIMEOUT="${JFI_FIT_TIMEOUT_SECONDS:-86400}"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
PY="$VENV/bin/python"

finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  (cd "$W" && find . -maxdepth 1 -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat "$W"/*.npy "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-jfi-factorial-l2-fit-v1$ ]] || die "invalid job nomenclature"
[ "${GO_JFI_FIT:-0}" = 1 ] || die "GO JFI FIT authorization missing"
[ "${POST_FACTS_AUTHORIZED:-0}" = 1 ] || die "post-Boundary-A authorization missing"
[ "${NO_FRESH_OPENINGS:-0}" = 1 ] || die "NO_FRESH_OPENINGS guard missing"
[ "${NO_STRENGTH_GAMES:-0}" = 1 ] || die "NO_STRENGTH_GAMES guard missing"
[ "${NO_SCAN_READS:-0}" = 1 ] || die "NO_SCAN_READS guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX62 contract mismatch"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "numeric runtime absent"
"$PY" -c 'import numpy,scipy; assert numpy.__version__ and scipy.__version__'

stage authenticate-post-facts-boundary
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$BOUNDARY_ROOT" \
  --file artefacts/JFI_BOUNDARY_A_FACTS.json=boundary-facts.json \
  --file artefacts/FULL_FITS__0=FULL_FITS__0 \
  --file artefacts/FRESH_OPENINGS__0=FRESH_OPENINGS__0 \
  --file artefacts/STRENGTH_GAMES__0=STRENGTH_GAMES__0 \
  --file artefacts/SCAN_WEIGHT_READS__0=SCAN_WEIGHT_READS__0 \
  --file artefacts/SCAN_SCORE_READS__0=SCAN_SCORE_READS__0 \
  --file artefacts/NEXT_BOUNDARY__GO_JFI_FIT=NEXT_BOUNDARY__GO_JFI_FIT \
  --out-dir "$IN" --report "$ART/verified-boundary-a.json" >"$W/fetch-boundary.log" 2>&1
"$PY" - "$IN/boundary-facts.json" "$ART/verified-boundary-a.json" \
  "$EXPECTED_CODE_SHA" "$EXPECTED_BOUNDARY_JOB" "$EXPECTED_BOUNDARY_ATTEMPT" <<'PY'
import json,os,sys
facts=json.load(open(sys.argv[1])); verified=json.load(open(sys.argv[2]))
if facts.get('schema')!='jass.jfi.boundary_a_facts.v1' or facts.get('verdict')!='JFI_BOUNDARY_A_READY':
 raise SystemExit('Boundary-A verdict drift')
if facts.get('code_sha')!=sys.argv[3] or facts.get('next_boundary')!='GO JFI FIT':
 raise SystemExit('Boundary-A code/next-boundary drift')
zero={'FULL_FITS':0,'FRESH_OPENINGS':0,'STRENGTH_GAMES':0,'SCIENTIFIC_DECISION':False,
      'SCAN_WEIGHT_READS':0,'SCAN_SCORE_READS':0}
if facts.get('markers')!=zero: raise SystemExit('Boundary-A zero markers drift')
if (verified.get('job_id'),verified.get('attempt_id'),verified.get('result_state')) != \
   (sys.argv[4],sys.argv[5],'completed'): raise SystemExit('Boundary-A identity/state drift')
recorded=facts.get('numeric_env') or {}
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
 if recorded.get(key)!=os.environ.get(key): raise SystemExit(f'numeric env drift: {key}')
PY

stage authenticate-frozen-inputs
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_ROOT" \
  --file artefacts/turnover1to1.jnnw.gz=turnover.jnnw.gz \
  --file artefacts/turnover1to1.jsm.gz=turnover.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-turnover.json" >"$W/fetch-turnover.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$ABC_ROOT" \
  --file artefacts/current_2m-context30.npy.gz=context30.npy.gz \
  --file artefacts/current_2m-manifest.json=source-manifest.json \
  --out-dir "$IN" --report "$ART/verified-context30.json" >"$W/fetch-context30.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" >"$W/fetch-curriculum.log" 2>&1
gunzip -c "$IN/turnover.jnnw.gz" >"$W/turnover.raw.jnnw"
gunzip -c "$IN/turnover.jsm.gz" >"$W/turnover.raw.jsm"
gunzip -c "$IN/context30.npy.gz" >"$W/context30.npy"
gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
[ "$(sha256sum "$W/turnover.raw.jnnw"|awk '{print $1}')" = "$TURNOVER_SHA" ] || die "TURNOVER SHA drift"
[ "$(sha256sum "$W/turnover.raw.jsm"|awk '{print $1}')" = "$TURNOVER_META_SHA" ] || die "TURNOVER meta SHA drift"
[ "$(sha256sum "$W/curriculum.pjtw"|awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM SHA drift"

stage reproduce-shared-design
python3 tools/selfplay_frontier.py split --data "$W/turnover.raw.jnnw" --meta "$W/turnover.raw.jsm" \
  --out-data "$W/current.jnnw" --out-meta "$W/current.jsm" --holdout-mod 10 --seed "$SPLIT_SEED" \
  --manifest "$W/current-manifest.json" >"$W/split.log" 2>&1
cmp "$W/current-manifest.json" "$IN/source-manifest.json" || die "CURRENT split manifest drift"
read -r RECORDS TRAIN HOLDOUT < <("$PY" - "$W/current-manifest.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); print(d['records'],d['train_records'],d['holdout_records'])
PY
)
[ "$RECORDS" -eq "$EXPECTED_RECORDS" ] && [ "$TRAIN" -gt 0 ] && [ "$HOLDOUT" -gt 0 ] || die "CURRENT count drift"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
timeout 7200s "$W/build/jass" --dump-eval-features "$W/current.jnnw" "$W/current.feat" >"$W/features.log" 2>&1
K=$(python3 -c 'import struct,sys;f=open(sys.argv[1],"rb");assert f.read(4)==b"FEAT";print(struct.unpack("<II",f.read(8))[1])' "$W/current.feat")
[ "$K" -eq "$EXPECTED_EXTRAS" ] || die "feature width drift"

fit(){
  local arm="$1"; local l2="$2"; shift 2
  local raw=()
  [[ "$arm" =~ ^[ABCD]$ ]] && raw=(--raw-weights-out "$W/$arm.raw.npy")
  /usr/bin/time -f '%e' -o "$W/$arm.seconds" timeout "${FIT_TIMEOUT}s" env \
    JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" PYTHONUNBUFFERED=1 \
    "$PY" pattern_jass/tools/train_stream.py --data "$W/current.jnnw" --feat "$W/current.feat" \
    --out "$W/$arm.pjtw" --target external --target-values "$W/context30.npy" \
    --targets-report "$ART/$arm-targets.json" --loss logistic --exact-fold --tempo-stage \
    --holdout-count "$HOLDOUT" --l2 "$l2" --max-iter "$MAXIT" --chunk "$CHUNK" \
    --lbfgs-maxcor "$MAXCOR" --lbfgs-gtol "$GTOL" --prune \
    --optimizer-report "$ART/$arm-optimizer.json" "${raw[@]}" "$@" >"$W/$arm.log" 2>&1
  [ -s "$W/$arm.pjtw" ] || die "$arm produced no PJTW"
}

stage seven-physical-full-fits
fit A 1e-5 --prior-mean "$W/curriculum.pjtw" --prior-decay 0
fit B 1e-5 --prior-mean "$W/curriculum.pjtw" --prior-decay 0 --init-mode zero
fit C 1e-5 --init-mode file --init-file "$W/curriculum.pjtw"
fit D 1e-5 --init-mode zero
fit L2_0 0 --init-mode zero
fit L2_1E6 1e-6 --init-mode zero
fit L2_1E4 1e-4 --init-mode zero

stage verify-positive-lambda-convergence
for arm in A B C D L2_1E6 L2_1E4; do
  "$PY" jobs/tools/verify_optimizer_convergence.py --report "$ART/$arm-optimizer.json" --label "$arm" \
    --expected-max-iterations "$MAXIT" --expected-maxcor "$MAXCOR" --expected-gtol "$GTOL" \
    --receipt "$ART/$arm-convergence.json"
done

stage factorial-and-l2-readout
set +e
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
  "$PY" jobs/tools/jfi_fit_readout.py --data "$W/current.jnnw" --meta "$W/current.jsm" \
  --feat "$W/current.feat" --targets "$W/context30.npy" --train-count "$TRAIN" \
  --factorial-model A="$W/A.pjtw" --factorial-model B="$W/B.pjtw" \
  --factorial-model C="$W/C.pjtw" --factorial-model D="$W/D.pjtw" \
  --factorial-raw A="$W/A.raw.npy" --factorial-raw B="$W/B.raw.npy" \
  --factorial-raw C="$W/C.raw.npy" --factorial-raw D="$W/D.raw.npy" \
  --factorial-optimizer A="$ART/A-optimizer.json" --factorial-optimizer B="$ART/B-optimizer.json" \
  --factorial-optimizer C="$ART/C-optimizer.json" --factorial-optimizer D="$ART/D-optimizer.json" \
  --l2-model 0="$W/L2_0.pjtw" --l2-model 1e-6="$W/L2_1E6.pjtw" \
  --l2-model 1e-5="$W/D.pjtw" --l2-model 1e-4="$W/L2_1E4.pjtw" \
  --bootstrap-samples "$BOOTSTRAP_SAMPLES" --bootstrap-seed "$BOOTSTRAP_SEED" \
  --factorial-out "$ART/JFI_A_FACTORIAL_SUMMARY.json" \
  --path-out "$ART/JFI_A_PATH_INDEPENDENCE.json" --l2-out "$ART/JFI_B_L2_CURVE.json" \
  --out "$ART/JFI_A_B_READOUT.json" >"$W/readout.log" 2>&1
READOUT_RC=$?
set -e
[ "$READOUT_RC" -eq 0 ] || [ "$READOUT_RC" -eq 3 ] || die "readout technical failure rc=$READOUT_RC"
"$PY" - "$ART/JFI_B_L2_CURVE.json" "$ART/JFI_B_SELECTED_L2.txt" <<'PY'
import json,sys
value=json.load(open(sys.argv[1]))['selected_l2']
open(sys.argv[2],'w').write(f'{value:.17g}\n')
PY

if [ "$READOUT_RC" -eq 0 ]; then
  stage selected-model-identifiability
  SELECTED_MODEL=$("$PY" - "$ART/JFI_B_L2_CURVE.json" "$W" <<'PY'
import json,sys
value=json.load(open(sys.argv[1]))['selected_l2']
mapping={1e-6:'L2_1E6.pjtw',1e-5:'D.pjtw',1e-4:'L2_1E4.pjtw'}
if value not in mapping: raise SystemExit('selected lambda is not a positive frozen-grid point')
print(sys.argv[2]+'/'+mapping[value])
PY
  )
  SELECTED_L2=$(cat "$ART/JFI_B_SELECTED_L2.txt")
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
    "$PY" jobs/tools/jfi_patterneval_identifiability.py --data "$W/current.jnnw" \
    --feat "$W/current.feat" --targets "$W/context30.npy" --model "$SELECTED_MODEL" \
    --train-count "$TRAIN" --l2 "$SELECTED_L2" --chunk "$CHUNK" \
    --fisher-out "$W/JFI_B_FISHER.npy" --diagnostics-out "$ART/JFI_B_COORDINATES.npz" \
    --out "$ART/JFI_B_IDENTIFIABILITY.json" >"$W/identifiability.log" 2>&1
  gzip -n -c "$W/JFI_B_FISHER.npy" >"$ART/JFI_B_FISHER.npy.gz"
  printf 'GO JFI ACTIVE\n' >"$ART/NEXT_BOUNDARY__GO_JFI_ACTIVE"
  touch "$ART/VERDICT__JFI_OPTIMIZER_PATH_INDEPENDENCE_ESTABLISHED"
else
  touch "$ART/VERDICT__JFI_OPTIMIZER_PATH_DEPENDENCE_DETECTED"
fi

stage publish-certificate
for arm in A B C D L2_0 L2_1E6 L2_1E4; do gzip -n -c "$W/$arm.pjtw" >"$ART/$arm.pjtw.gz"; done
"$PY" - "$ART" "$EXPECTED_CODE_SHA" "$W/current-manifest.json" "$READOUT_RC" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
art=Path(sys.argv[1]); code=sys.argv[2]; manifest=json.load(open(sys.argv[3])); rc=int(sys.argv[4])
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1<<20),b''): h.update(block)
 return h.hexdigest()
models={name:sha(art/f'{name}.pjtw.gz') for name in ('A','B','C','D','L2_0','L2_1E6','L2_1E4')}
payload={'schema':'jass.jfi.a_b_certificate.v1','code_sha':code,'source_manifest':manifest,
 'full_fits':7,'physical_fit_arms':['A','B','C','D','L2_0','L2_1E6','L2_1E4'],
 'D_reused_as_l2_1e5':True,'model_gzip_sha256':models,
 'path_verdict':json.load(open(art/'JFI_A_PATH_INDEPENDENCE.json'))['verdict'],
 'selected_l2':json.load(open(art/'JFI_B_L2_CURVE.json'))['selected_l2'],
 'identifiability_published':rc==0,
 'markers':{'FULL_FITS':7,'FRESH_OPENINGS':0,'STRENGTH_GAMES':0,
            'SCAN_WEIGHT_READS':0,'SCAN_SCORE_READS':0,'SCAN_TARGET_READS':0,
            'PROMOTION_AUTHORIZED':False}}
(art/'JFI_A_B_CERTIFICATE.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY
printf '7\n' >"$ART/FULL_FITS__7"; printf '0\n' >"$ART/FRESH_OPENINGS__0"
printf '0\n' >"$ART/STRENGTH_GAMES__0"; printf '0\n' >"$ART/SCAN_READS__0"
printf 'FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"
stage complete
if [ "$READOUT_RC" -eq 0 ]; then
  say "JFI_OPTIMIZER_PATH_INDEPENDENCE_ESTABLISHED FULL_FITS=7 NEXT_BOUNDARY=GO_JFI_ACTIVE"
else
  say "JFI_OPTIMIZER_PATH_DEPENDENCE_DETECTED FULL_FITS=7 STOP"
fi
