#!/usr/bin/env bash
# Full-Jass causal CONTEXT_30 controls on immutable TURNOVER 2M.
#
# Reuses the certified ALIGNED model from cpx62-1340, reconstructs its exact
# aligned target, builds a stronger WDL-stratified SHUFFLED control, then fits
# only SHUFFLED and terminal OUTCOME.
# No games, frozen cohort, self-play, selection, child job or promotion here.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$IN" "$ART" "$GEOM"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

TURNOVER_ROOT="r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984"
L2LOW_ROOT="r2:jass-data/runs/cpx62-1164-l3-prior-dose-l2-refit-v1/20260803T060626Z-209eb56b"
ALIGNED_ROOT="r2:jass-data/runs/cpx62-1340-jass-megacorpus-comparative-fit-v1/20260814T123246Z-2ce07222"
ALIGNED_AUDIT_ROOT="r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/20260814T191555Z-18c38a33"
TURNOVER_JOB="home-0977-l3-pure-turnover1to1-train-v1"
L2LOW_JOB="cpx62-1164-l3-prior-dose-l2-refit-v1"
ALIGNED_JOB="cpx62-1340-jass-megacorpus-comparative-fit-v1"
ALIGNED_ATTEMPT="20260814T123246Z-2ce07222"
ALIGNED_CODE_SHA="2ce07222f86c1468a1081fbdc53e9e17a0c5326e"
ALIGNED_AUDIT_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
ALIGNED_AUDIT_ATTEMPT="20260814T191555Z-18c38a33"
ALIGNED_AUDIT_CODE_SHA="18c38a33ae78c9c2e8e2df62fca266da28dacead"
TARGET_BUILDER_BLOB="968b253084e272d69f61f952e47ec71471aaadf5"
TRAIN_STREAM_BLOB="12ed5f0f743dadc07ebaab6de1dd9a837297b6c0"
SPLITTER_BLOB="2147a14152814c0608886efe7319b9a7e388143d"
TURNOVER_CORPUS_SHA="9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
TURNOVER_META_SHA="acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
L2LOW_SHA="ec47e4b37fc7e95dcb390c0a5eddf207e98c0818c1708636d2df9e85b1d149b4"
EXPECTED_RECORDS=2000000; EXPECTED_HOLDOUT=199204; EXPECTED_EXTRAS=120
SPLIT_SEED=577215; HOLDOUT_MOD=10; MAXIT=2000; CHUNK=20000
TARGET_TIMEOUT=10800; FIT_TIMEOUT=21600
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
VENV_READY="$VENV/.jass-runtime-ready-v1"

MON=""
monitor(){
  ( t0=$(date +%s)
    while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        for arm in shuffled outcome; do
          [ -f "$W/fit-$arm.log" ] &&
            printf '%s_fit_log_lines=%s\n' "$arm" "$(wc -l < "$W/fit-$arm.log")"
        done
      } >"$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 120
    done ) &
  MON="$!"
}
finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
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
[[ "$JASS_JOB_ID" =~ ^cpx62-([0-9]+)-l3-context30-causal-fit-v1$ ]] ||
  die "invalid job nomenclature"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "explicit execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 20480 ] || die "less than 20 GiB free ($DFA MiB)"
say "host=$(hostname) nproc=$(nproc) free_mb=$DFA mode=context30_causal_controls"
monitor

stage fetch-four-immutable-source-certificates
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_ROOT" \
  --file artefacts/turnover1to1.jnnw.gz=turnover.jnnw.gz \
  --file artefacts/turnover1to1.jsm.gz=turnover.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-turnover.json" >"$W/fetch-turnover.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$L2LOW_ROOT" \
  --file artefacts/control.pjtw.gz=l2low.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-l2low.json" >"$W/fetch-l2low.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$ALIGNED_ROOT" \
  --file artefacts/current_2m.pjtw.gz=aligned.pjtw.gz \
  --file artefacts/current_2m-context30.npy.gz=source-aligned.npy.gz \
  --file artefacts/current_2m-conditional-targets.json=source-targets.json \
  --file artefacts/current_2m-target-consumption.json=source-consumption.json \
  --file artefacts/current_2m-manifest.json=source-split.json \
  --file artefacts/current_2m-optimizer.json=source-optimizer.json \
  --file artefacts/python-runtime.json=source-runtime.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=source-summary.json \
  --out-dir "$IN" --report "$ART/verified-aligned.json" >"$W/fetch-aligned.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$ALIGNED_AUDIT_ROOT" \
  --file artefacts/source-A-convergence.json=source-A-convergence.json \
  --out-dir "$IN" --report "$ART/verified-aligned-audit.json" >"$W/fetch-aligned-audit.log" 2>&1

python3 - "$ART" "$IN" <<'PY'
import json, os, sys
from pathlib import Path
art, inp = Path(sys.argv[1]), Path(sys.argv[2])
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def ident(name, job, attempt=None, code=None):
    row=load(art/name)
    if row.get('job_id') != job or row.get('result_state') != 'completed' or row.get('exit_code') != 0:
        raise SystemExit(f'{name}: source identity/state drift')
    if attempt and row.get('attempt_id') != attempt: raise SystemExit(f'{name}: attempt drift')
    if code and row.get('code_sha') != code: raise SystemExit(f'{name}: code drift')
ident('verified-turnover.json', os.environ.get('TURNOVER_JOB','home-0977-l3-pure-turnover1to1-train-v1'))
ident('verified-l2low.json', os.environ.get('L2LOW_JOB','cpx62-1164-l3-prior-dose-l2-refit-v1'))
ident('verified-aligned.json','cpx62-1340-jass-megacorpus-comparative-fit-v1',
      '20260814T123246Z-2ce07222','2ce07222f86c1468a1081fbdc53e9e17a0c5326e')
ident('verified-aligned-audit.json','cpx62-1341-jass-megacorpus-arm-d-fit-v1',
      '20260814T191555Z-18c38a33','18c38a33ae78c9c2e8e2df62fca266da28dacead')
s=load(inp/'source-summary.json'); arm=s.get('arms',{}).get('CURRENT_2M',{})
if s.get('verdict') != 'JASS_MEGACORPUS_ABC_FITS_READY' or arm.get('target') != 'CONTEXT_30_ALIGNED':
    raise SystemExit('aligned source certificate drift')
if arm.get('records') != 2_000_000 or arm.get('holdout_records') != 199_204:
    raise SystemExit('aligned source sizing drift')
PY

gunzip -c "$IN/turnover.jnnw.gz" >"$W/turnover.raw.jnnw"
gunzip -c "$IN/turnover.jsm.gz" >"$W/turnover.raw.jsm"
gunzip -c "$IN/l2low.pjtw.gz" >"$W/l2low.pjtw"
gunzip -c "$IN/aligned.pjtw.gz" >"$W/aligned.pjtw"
gunzip -c "$IN/source-aligned.npy.gz" >"$W/source-aligned.npy"
[ "$(sha256sum "$W/turnover.raw.jnnw" | awk '{print $1}')" = "$TURNOVER_CORPUS_SHA" ] || die "TURNOVER data drift"
[ "$(sha256sum "$W/turnover.raw.jsm" | awk '{print $1}')" = "$TURNOVER_META_SHA" ] || die "TURNOVER meta drift"
[ "$(sha256sum "$W/l2low.pjtw" | awk '{print $1}')" = "$L2LOW_SHA" ] || die "L2LOW drift"

stage persistent-numeric-runtime
if [ ! -f "$VENV_READY" ]; then
  mkdir -p "$(dirname "$VENV")"
  python3 -m venv --clear "$VENV"
  "$VENV/bin/python" -m pip install --disable-pip-version-check --only-binary=:all: \
    numpy scipy >"$W/pip-bootstrap-once.log" 2>&1
  "$VENV/bin/python" - "$VENV_READY" "$JASS_JOB_ID" <<'PY'
import json,numpy,scipy,sys
open(sys.argv[1],'w').write(json.dumps({'schema':'jass.numeric_cache.v1','created_by':sys.argv[2],
 'numpy':numpy.__version__,'scipy':scipy.__version__},indent=2,sort_keys=True)+'\n')
PY
fi
PY="$VENV/bin/python"
"$PY" - "$IN/source-runtime.json" "$ART/python-runtime.json" "$VENV" <<'PY'
import json,numpy,scipy,sys
source=json.load(open(sys.argv[1]))
got={'numpy':numpy.__version__,'scipy':scipy.__version__}
if any(source.get(k) != v for k,v in got.items()):
 raise SystemExit(f'numeric stack differs from aligned fit: source={source} current={got}')
json.dump({'schema':'jass.python_runtime.v1','venv':sys.argv[3],**got,
 'matches_aligned_source':True,'pytorch_installed_or_required':False,
 'persistent_cache':True},open(sys.argv[2],'w'),indent=2,sort_keys=True)
open(sys.argv[2],'a').write('\n')
PY

stage repository-and-source-code-contracts
python3 -m py_compile jobs/tools/l3_conditional_targets.py jobs/tools/verify_optimizer_convergence.py
"$PY" -m unittest jobs.tests.test_jass_megacorpus_comparative_template \
  jobs.tests.test_l3_context30_causal_fit_template \
  jobs.tests.test_l3_context30_causal_protocol \
  jobs.tests.test_l3_context30_causal_targets >"$W/tests.log" 2>&1
[ "$(git hash-object jobs/tools/l3_conditional_targets.py)" = "$TARGET_BUILDER_BLOB" ] ||
  die "conditional target builder changed since aligned source fit"
[ "$(git hash-object pattern_jass/tools/train_stream.py)" = "$TRAIN_STREAM_BLOB" ] ||
  die "train_stream changed since aligned source fit"
[ "$(git hash-object tools/selfplay_frontier.py)" = "$SPLITTER_BLOB" ] ||
  die "splitter changed since aligned source fit"

stage reproduce-identical-opening-level-split
python3 tools/selfplay_frontier.py split \
  --data "$W/turnover.raw.jnnw" --meta "$W/turnover.raw.jsm" \
  --out-data "$W/current.jnnw" --out-meta "$W/current.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$ART/split.json" >"$W/split.log" 2>&1
read -r RECORDS TRAIN HOLDOUT < <("$PY" - \
  "$ART/split.json" "$IN/source-split.json" "$IN/source-targets.json" \
  "$W/current.jnnw" "$W/current.jsm" <<'PY'
import hashlib,json,sys
from pathlib import Path
current=json.load(open(sys.argv[1])); source=json.load(open(sys.argv[2]))
if current != source:
 raise SystemExit('split manifest drift')
targets=json.load(open(sys.argv[3]))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
for label,path,key in (('data',sys.argv[4],'data_sha256'),('meta',sys.argv[5],'meta_sha256')):
 if sha(path) != targets['source'][key]:
  raise SystemExit(f'split {label} hash drift')
print(current['records'],current['train_records'],current['holdout_records'])
PY
)
[ "$RECORDS" -eq "$EXPECTED_RECORDS" ] && [ "$HOLDOUT" -eq "$EXPECTED_HOLDOUT" ] || die "split sizing drift"

stage build-production-architecture-and-features
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] || die "8cf geometry drift"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
  -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "missing jass binary"
"$J" --dump-eval-features "$W/current.jnnw" "$W/current.feat" >"$W/features.log" 2>&1
K=$(python3 -c 'import struct,sys;f=open(sys.argv[1],"rb");assert f.read(4)==b"FEAT";print(struct.unpack("<II",f.read(8))[1])' "$W/current.feat")
[ "$K" -eq "$EXPECTED_EXTRAS" ] || die "architecture guard: extras=$K"

stage reconstruct-aligned-and-wdl-stratified-shuffled-targets
/usr/bin/time -f '%e' -o "$W/targets.seconds" timeout "$TARGET_TIMEOUT" \
  "$PY" jobs/tools/l3_conditional_targets.py \
    --data "$W/current.jnnw" --meta "$W/current.jsm" --feat "$W/current.feat" \
    --train-count "$TRAIN" --aligned-out "$W/aligned.npy" --shuffled-out "$W/shuffled.npy" \
    --report "$ART/conditional-targets.json" --alpha 0.30 --shuffle-within-wdl \
    >"$W/targets.log" 2>&1

"$PY" - "$ART/conditional-targets.json" "$IN/source-targets.json" \
  "$IN/source-consumption.json" "$W/aligned.npy" "$W/source-aligned.npy" <<'PY'
import hashlib,json,sys
from pathlib import Path
def load(p): return json.load(open(p))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
new,src,cons=map(load,sys.argv[1:4])
if new['outputs']['aligned_sha256'] != src['outputs']['aligned_sha256']:
 raise SystemExit('reconstructed aligned target differs from source')
if sha(sys.argv[4]) != sha(sys.argv[5]) or sha(sys.argv[4]) != src['outputs']['aligned_sha256']:
 raise SystemExit('published aligned sidecar drift')
if cons['source']['sha256'] != src['outputs']['aligned_sha256']:
 raise SystemExit('aligned source model consumed another target')
if not new['mapping']['all_games_fold_disjoint'] or new['mapping']['train_holdout_game_overlap'] != 0:
 raise SystemExit('conditional mapper leakage guard failed')
sh=new['shuffle_control']
if (sh['fixed_point_count'] != 0 or not sh['all_cohort_fold_marginals_preserved']
    or sh.get('stratification') != 'terminal_wdl_black'
    or not sh.get('all_sources_within_same_stratum')
    or not sh.get('all_final_target_marginals_preserved')):
 raise SystemExit('shuffled causal control invalid')
PY
gzip -n -c "$W/aligned.npy" >"$ART/aligned-target.npy.gz"
gzip -n -c "$W/shuffled.npy" >"$ART/shuffled-target.npy.gz"

stage reauthenticate-aligned-source-convergence
"$PY" jobs/tools/verify_optimizer_convergence.py \
  --report "$IN/source-optimizer.json" --label ALIGNED_SOURCE \
  --expected-max-iterations "$MAXIT" --expected-maxcor 20 --expected-gtol 1e-4 \
  --receipt "$ART/aligned-source-convergence-recheck.json"
cp "$IN/source-A-convergence.json" "$ART/aligned-source-convergence-1341.json"
cp "$IN/aligned.pjtw.gz" "$ART/aligned.pjtw.gz"

fit_control(){
  local arm="$1"; shift
  stage "fit-$arm"
  /usr/bin/time -f '%e' -o "$W/fit-$arm.seconds" timeout "$FIT_TIMEOUT" \
    env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" PYTHONUNBUFFERED=1 \
    "$PY" pattern_jass/tools/train_stream.py \
      --data "$W/current.jnnw" --feat "$W/current.feat" --out "$W/$arm.pjtw" \
      "$@" --loss logistic --exact-fold --tempo-stage \
      --prior-mean "$W/l2low.pjtw" --prior-decay 0 \
      --holdout-count "$HOLDOUT" --l2 1e-5 --max-iter "$MAXIT" \
      --chunk "$CHUNK" --lbfgs-maxcor 20 --lbfgs-gtol 1e-4 --prune \
      --optimizer-report "$ART/$arm-optimizer.json" >"$W/fit-$arm.log" 2>&1
  [ -s "$W/$arm.pjtw" ] || die "$arm produced no model"
  "$PY" jobs/tools/verify_optimizer_convergence.py \
    --report "$ART/$arm-optimizer.json" --label "$arm" \
    --expected-max-iterations "$MAXIT" --expected-maxcor 20 --expected-gtol 1e-4 \
    --receipt "$ART/$arm-convergence.json"
  gzip -n -c "$W/$arm.pjtw" >"$ART/$arm.pjtw.gz"
}

stage sequential-contention-free-control-fits
fit_control shuffled --target external --target-values "$W/shuffled.npy" \
  --targets-report "$ART/shuffled-target-consumption.json"
fit_control outcome --target wdl

stage publish-causal-model-certificate
"$PY" - "$W" "$ART" "$IN/source-summary.json" "$ART/conditional-targets.json" "$EXPECTED_CODE_SHA" <<'PY'
import hashlib,json,struct,sys
from pathlib import Path
w,art=Path(sys.argv[1]),Path(sys.argv[2]); source=json.load(open(sys.argv[3])); targets=json.load(open(sys.argv[4]))
code=sys.argv[5]
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def structure(p):
 magic,version,scale,n_pat,n_ext=struct.unpack('<5I',Path(p).read_bytes()[:20])
 expected=20+4*2*(n_pat+n_ext)
 if (magic!=0x57544A50 or (version&0xff)!=3 or version&~(0xff|0x100|0x200)
     or scale<=0 or n_pat!=4251528 or n_ext!=120 or Path(p).stat().st_size!=expected):
  raise SystemExit(f'{p}: PJTW structure drift')
 return {'version':version,'scale':scale,'n_patterns':n_pat,'n_extras':n_ext,
  'size_bytes':Path(p).stat().st_size}
models={}
for arm in ('aligned','shuffled','outcome'):
 p=w/f'{arm}.pjtw'; models[arm]={'model_raw_sha256':sha(p),'structure':structure(p)}
 gz=art/f'{arm}.pjtw.gz'; models[arm]['model_gz_sha256']=sha(gz)
if len({row['model_raw_sha256'] for row in models.values()}) != 3:
 raise SystemExit('causal arms are not three distinct models')
expected=source['arms']['CURRENT_2M']['model_raw_sha256']
if models['aligned']['model_raw_sha256'] != expected:
 raise SystemExit('aligned source model hash drift')
cons=json.load(open(art/'shuffled-target-consumption.json'))
if cons['source']['sha256'] != targets['outputs']['shuffled_sha256']:
 raise SystemExit('shuffled fit consumed wrong target')
for arm in ('shuffled','outcome'):
 models[arm]['optimizer']=json.load(open(art/f'{arm}-optimizer.json'))
 models[arm]['convergence']=json.load(open(art/f'{arm}-convergence.json'))
 models[arm]['fit_seconds']=float((w/f'fit-{arm}.seconds').read_text())
payload={'schema':'jass.l3_context30_causal_models.v1',
 'verdict':'JASS_CONTEXT30_CAUSAL_MODELS_READY','code_sha':code,
 'corpus':'TURNOVER_CURRENT_2M','parent':'L2LOW','records':2_000_000,
 'split':{'seed':577215,'holdout_mod':10,'holdout_records':199_204},
 'architecture':'8cf_exact_fold_tempo_120_extras',
 'recipe':{'prior_mean':'L2LOW','prior_decay':0,'l2':1e-5,'gtol':1e-4,'max_iterations':2000},
 'arms':{
  'ALIGNED':{**models['aligned'],'target':'CONTEXT_30_ALIGNED_alpha_0.30','reused_from':'cpx62-1340'},
  'SHUFFLED':{**models['shuffled'],'target':'CONTEXT_30_SHUFFLED_WDL_STRATIFIED_MARGINAL_MATCHED_alpha_0.30'},
  'OUTCOME':{**models['outcome'],'target':'TERMINAL_WDL'}},
 'target_certificate':{'aligned_sha256':targets['outputs']['aligned_sha256'],
  'shuffled_sha256':targets['outputs']['shuffled_sha256'],
  'fixed_points':targets['shuffle_control']['fixed_point_count'],
  'shuffle_stratification':targets['shuffle_control']['stratification'],
  'all_cohort_fold_marginals_preserved':targets['shuffle_control']['all_cohort_fold_marginals_preserved'],
  'all_final_target_marginals_preserved':targets['shuffle_control']['all_final_target_marginals_preserved']},
 'primary_contrast':'ALIGNED_vs_SHUFFLED_on_two_fresh_disjoint_opening_pools',
 'secondary_contrast':'ALIGNED_vs_OUTCOME_only_if_primary_passes',
 'new_selfplay_generated':False,'frozen_cohorts_read':0,
 'strength_games_played':0,'promotion_authorized':False,'automatic_next_job':None}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/'VERDICT__JASS_CONTEXT30_CAUSAL_MODELS_READY').touch()
(art/'PROMOTION_AUTHORIZED__FALSE').touch(); (art/'AUTOMATIC_NEXT_JOB__NULL').touch()
print(json.dumps(payload,sort_keys=True))
PY
say "JASS_CONTEXT30_CAUSAL_MODELS_READY selfplay=0 frozen=0 strength_games=0 promotion=false"
