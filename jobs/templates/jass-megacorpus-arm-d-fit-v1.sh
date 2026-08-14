#!/usr/bin/env bash
# Fit D = C-prior then CURRENT_2M, and read A/B/C/D on one shared holdout.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${ABC_PREFIX:?}"; : "${EXPECTED_ABC_JOB:?}"; : "${EXPECTED_ABC_ATTEMPT:?}"
: "${EXPECTED_ABC_CODE_SHA:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$IN" "$ART" "$GEOM"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

TURNOVER_ROOT="r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984"
TURNOVER_JOB="home-0977-l3-pure-turnover1to1-train-v1"
TURNOVER_CORPUS_SHA="9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
TURNOVER_META_SHA="acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
HOLDOUT_MOD=10; SPLIT_SEED=577215; MAXIT=2000; CHUNK=20000
FIT_TIMEOUT=14400; EXPECTED_EXTRAS=120
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
VENV_READY="$VENV/.jass-runtime-ready-v1"

MON=""
monitor(){
  ( t0=$(date +%s)
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
        [ -f "$W/fit-D.log" ] && printf 'fit_log_lines=%s\n' "$(wc -l < "$W/fit-D.log")"
      } >"$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 120
    done ) &
  MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -maxdepth 1 -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" 2>/dev/null || true
  rm -f "$W"/*.feat "$W"/*.npy "$W"/*.jnnw "$W"/*.jsm "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-([0-9]+)-jass-megacorpus-arm-d-fit-v1$ ]] ||
  die "invalid job nomenclature"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "explicit execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX contract mismatch"
[ -f "$VENV_READY" ] || die "persistent numeric runtime absent; do not reinstall in this job"
PY="$VENV/bin/python"
"$PY" -c 'import numpy, scipy; assert numpy.__version__; assert scipy.__version__' ||
  die "persistent numeric runtime invalid"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/jass_megacorpus_static_readout.py \
  jobs/tools/verify_optimizer_convergence.py
"$PY" -m unittest jobs.tests.test_jass_megacorpus_abcd >"$W/tests.log" 2>&1

stage fetch-authenticated-abc-and-current-source
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$ABC_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=abc-summary.json \
  --file artefacts/current_2m-optimizer.json=A-optimizer.json \
  --file artefacts/mega_eq_2m-optimizer.json=B-optimizer.json \
  --file artefacts/mega_full_4m-optimizer.json=C-optimizer.json \
  --file artefacts/current_2m.pjtw.gz=A.pjtw.gz \
  --file artefacts/mega_eq_2m.pjtw.gz=B.pjtw.gz \
  --file artefacts/mega_full_4m.pjtw.gz=C.pjtw.gz \
  --file artefacts/current_2m-context30.npy.gz=current-context30.npy.gz \
  --file artefacts/current_2m-manifest.json=current-manifest.json \
  --file artefacts/current_2m-conditional-targets.json=current-targets.json \
  --file artefacts/current_2m-target-consumption.json=current-consumption.json \
  --out-dir "$IN" --report "$ART/verified-abc.json" >"$W/fetch-abc.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_ROOT" \
  --file artefacts/turnover1to1.jnnw.gz=turnover.jnnw.gz \
  --file artefacts/turnover1to1.jsm.gz=turnover.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-turnover.json" >"$W/fetch-turnover.log" 2>&1
"$PY" - "$IN/abc-summary.json" "$ART/verified-abc.json" "$ART/verified-turnover.json" \
  "$EXPECTED_ABC_JOB" "$EXPECTED_ABC_ATTEMPT" "$EXPECTED_ABC_CODE_SHA" "$TURNOVER_JOB" <<'PY'
import json,sys
summary,abc,turn=(json.load(open(path)) for path in sys.argv[1:4])
if summary.get('verdict')!='JASS_MEGACORPUS_ABC_FITS_READY': raise SystemExit('ABC verdict drift')
if (abc.get('job_id'),abc.get('attempt_id'),abc.get('code_sha'),abc.get('result_state')) != \
   (sys.argv[4],sys.argv[5],sys.argv[6],'completed'): raise SystemExit('ABC identity/state drift')
if turn.get('job_id')!=sys.argv[7] or turn.get('result_state')!='completed':
 raise SystemExit('TURNOVER identity/state drift')
recipe=summary.get('fixed_recipe') or {}
if (recipe.get('architecture'),recipe.get('target'),recipe.get('l2'),recipe.get('max_iterations')) != \
   ('8cf_exact_fold_tempo_120_extras','CONTEXT_30_ALIGNED_alpha_0.30',1e-5,2000):
 raise SystemExit('ABC recipe drift')
PY
"$PY" - "$IN/abc-summary.json" "$IN/A-optimizer.json" \
  "$IN/B-optimizer.json" "$IN/C-optimizer.json" <<'PY'
import json,sys
summary=json.load(open(sys.argv[1]))
for label,path in zip(('CURRENT_2M','MEGA_EQ_2M','MEGA_FULL_4M'),sys.argv[2:]):
 report=json.load(open(path))
 if summary['arms'][label].get('optimizer') != report:
  raise SystemExit(f'{label}: optimizer report differs from ABC certificate')
PY
for arm in A B C; do
  "$PY" jobs/tools/verify_optimizer_convergence.py \
    --report "$IN/$arm-optimizer.json" --label "source-$arm" \
    --expected-max-iterations 2000 --expected-maxcor 20 \
    --expected-gtol 1e-4 --receipt "$ART/source-$arm-convergence.json"
done

for arm in A B C; do gunzip -c "$IN/$arm.pjtw.gz" >"$W/$arm.pjtw"; done
gunzip -c "$IN/current-context30.npy.gz" >"$W/current-context30.npy"
gunzip -c "$IN/turnover.jnnw.gz" >"$W/turnover.raw.jnnw"
gunzip -c "$IN/turnover.jsm.gz" >"$W/turnover.raw.jsm"
"$PY" - "$IN/abc-summary.json" "$W" <<'PY'
import hashlib,json,sys
from pathlib import Path
summary=json.load(open(sys.argv[1])); root=Path(sys.argv[2])
for file,label in (('A.pjtw','CURRENT_2M'),('B.pjtw','MEGA_EQ_2M'),('C.pjtw','MEGA_FULL_4M')):
 digest=hashlib.sha256((root/file).read_bytes()).hexdigest()
 if digest != summary['arms'][label]['model_raw_sha256']:
  raise SystemExit(f'{file}: model hash differs from ABC certificate')
PY
[ "$(sha256sum "$W/turnover.raw.jnnw" | awk '{print $1}')" = "$TURNOVER_CORPUS_SHA" ] ||
  die "TURNOVER corpus hash drift"
[ "$(sha256sum "$W/turnover.raw.jsm" | awk '{print $1}')" = "$TURNOVER_META_SHA" ] ||
  die "TURNOVER metadata hash drift"

stage reproduce-current-split-and-features
python3 tools/selfplay_frontier.py split \
  --data "$W/turnover.raw.jnnw" --meta "$W/turnover.raw.jsm" \
  --out-data "$W/current.jnnw" --out-meta "$W/current.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$W/current-manifest-reproduced.json" >"$W/split.log" 2>&1
cmp "$W/current-manifest-reproduced.json" "$IN/current-manifest.json" ||
  die "CURRENT split manifest does not reproduce ABC"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
  -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
J="$W/build/jass"
timeout 5400s "$J" --dump-eval-features "$W/current.jnnw" "$W/current.feat" \
  >"$W/features.log" 2>&1
read -r RECORDS TRAIN HOLDOUT < <("$PY" - "$IN/current-manifest.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); print(d['records'],d['train_records'],d['holdout_records'])
PY
)
[ "$RECORDS" -eq 2000000 ] && [ "$TRAIN" -gt 0 ] && [ "$HOLDOUT" -gt 0 ] ||
  die "CURRENT counts drift"

stage fit-D-C-prior-then-current
/usr/bin/time -f '%e' -o "$W/fit-D.seconds" timeout "$FIT_TIMEOUT" \
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" PYTHONUNBUFFERED=1 \
  "$PY" pattern_jass/tools/train_stream.py \
    --data "$W/current.jnnw" --feat "$W/current.feat" --out "$W/D.pjtw" \
    --target external --target-values "$W/current-context30.npy" \
    --targets-report "$ART/D-target-consumption.json" \
    --loss logistic --exact-fold --tempo-stage \
    --prior-mean "$W/C.pjtw" --prior-decay 0 \
    --holdout-count "$HOLDOUT" --l2 1e-5 --max-iter "$MAXIT" \
    --chunk "$CHUNK" --lbfgs-maxcor 20 --lbfgs-gtol 1e-4 --prune \
    --optimizer-report "$ART/D-optimizer.json" >"$W/fit-D.log" 2>&1
[ -s "$W/D.pjtw" ] || die "D produced no PJTW"
"$PY" jobs/tools/verify_optimizer_convergence.py \
  --report "$ART/D-optimizer.json" --label D \
  --expected-max-iterations "$MAXIT" --expected-maxcor 20 \
  --expected-gtol 1e-4 --receipt "$ART/D-convergence.json"
gzip -n -c "$W/D.pjtw" >"$ART/D-c-prior-then-current.pjtw.gz"

stage common-opening-disjoint-static-readout
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
  "$PY" jobs/tools/jass_megacorpus_static_readout.py \
    --data "$W/current.jnnw" --meta "$W/current.jsm" --feat "$W/current.feat" \
    --context-targets "$W/current-context30.npy" --train-count "$TRAIN" \
    --model A="$W/A.pjtw" --model B="$W/B.pjtw" --model C="$W/C.pjtw" --model D="$W/D.pjtw" \
    --contrast B:A --contrast C:B --contrast D:A --contrast D:C --contrast C:A --contrast D:B \
    --bootstrap-samples 5000 --bootstrap-seed 20260814 \
    --out "$ART/abcd-static-readout.json" >"$W/static-readout.log" 2>&1

stage publish-D-certificate
"$PY" - "$W" "$ART" "$IN/abc-summary.json" "$EXPECTED_CODE_SHA" "$ABC_PREFIX" <<'PY'
import hashlib,json,re,struct,sys
from pathlib import Path
w,art=Path(sys.argv[1]),Path(sys.argv[2]); abc=json.load(open(sys.argv[3])); code=sys.argv[4]
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1<<20),b''): h.update(block)
 return h.hexdigest()
opt=json.load(open(art/'D-optimizer.json')); static=json.load(open(art/'abcd-static-readout.json'))
consumed=json.load(open(art/'D-target-consumption.json'))
source=json.load(open(sys.argv[3].replace('abc-summary.json','current-targets.json')))
if consumed['source']['sha256'] != source['outputs']['aligned_sha256']:
 raise SystemExit('D target consumption drift')
raw=(w/'D.pjtw').read_bytes()[:20]; magic,version,scale,n_pat,n_ext=struct.unpack('<5I',raw)
if magic!=0x57544A50 or (version&0xff)!=3 or n_pat!=4251528 or n_ext!=120:
 raise SystemExit('D PJTW structure drift')
log=(w/'fit-D.log').read_text(errors='replace')
hm=re.search(r'HOLDOUT_LOGLOSS\s+([0-9.]+)',log); tm=list(re.finditer(r'train_loss=([0-9.]+)',log))
payload={'schema':'jass.megacorpus.arm_d_fit.v1','verdict':'JASS_MEGACORPUS_ARM_D_FIT_READY',
 'code_sha':code,'abc_prefix':sys.argv[5],
 'arm':{'label':'D','name':'C_PRIOR_THEN_CURRENT_2M','pretrain_model':'MEGA_FULL_4M',
  'recenter_corpus':'CURRENT_2M','target':'CONTEXT_30_ALIGNED','model_raw_sha256':sha(w/'D.pjtw'),
  'model_gz_sha256':sha(art/'D-c-prior-then-current.pjtw.gz'),'optimizer':opt,
  'train_loss':float(tm[-1].group(1)) if tm else None,
  'own_current_holdout_logloss':float(hm.group(1)) if hm else None,
  'fit_seconds':float((w/'fit-D.seconds').read_text())},
 'objective':{'data_term':'CURRENT_2M_CONTEXT30_logistic_CE',
  'prior_mean':'C_MEGA_FULL_4M','prior_decay':0,'prior_precision':1e-5,
  'formula':'CE_Current + 0.5e-5*||w-C||^2','max_iterations':2000,'gtol':1e-4,
  'plain_warm_start_rejected_as_scientifically_empty':True},
 'static_readout':static,'common_strength_evaluation_required':True,
 'frozen_cohorts_read':0,'new_selfplay_generated':False,'promotion_authorized':False,
 'automatic_next_job':None}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY
touch "$ART/VERDICT__JASS_MEGACORPUS_ARM_D_FIT_READY"
touch "$ART/PROMOTION_AUTHORIZED__FALSE" "$ART/AUTOMATIC_NEXT_JOB__NULL"
say "JASS_MEGACORPUS_ARM_D_FIT_READY static_abcd=true strength_pending=true promotion=false"
