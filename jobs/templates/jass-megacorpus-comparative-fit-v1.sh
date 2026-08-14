#!/usr/bin/env bash
# Comparative CURRENT_2M / MEGA_EQ_2M / MEGA_FULL_4M fits on CPX.
# Checkpoints only: no frozen cohort, games, selection, child job or promotion.
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
UNIFORM_ROOT="r2:jass-data/runs/home-1044-l3-pure-hard-replay-large-source-v1/20260729T070032Z-477da64d"
L2LOW_ROOT="r2:jass-data/runs/cpx62-1164-l3-prior-dose-l2-refit-v1/20260803T060626Z-209eb56b"
SMOKE_ROOT="r2:jass-data/runs/cpx62-1332-jass-megacorpus-smoke-fit-v1/20260814T065405Z-7902ce59"
TURNOVER_JOB="home-0977-l3-pure-turnover1to1-train-v1"
UNIFORM_JOB="home-1044-l3-pure-hard-replay-large-source-v1"
UNIFORM_ATTEMPT="20260729T070032Z-477da64d"
UNIFORM_CODE_SHA="477da64da2dea09c8ceb1f1e8e79e2c54d023a5a"
L2LOW_JOB="cpx62-1164-l3-prior-dose-l2-refit-v1"
SMOKE_JOB="cpx62-1332-jass-megacorpus-smoke-fit-v1"
TURNOVER_CORPUS_SHA="9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
TURNOVER_META_SHA="acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
L2LOW_SHA="ec47e4b37fc7e95dcb390c0a5eddf207e98c0818c1708636d2df9e85b1d149b4"
UNIFORM_RECORDS=40000000; CURRENT_RECORDS=2000000; EXPECTED_EXTRAS=120
SAMPLE_SEED=20260814; HOLDOUT_MOD=10; SPLIT_SEED=577215
MAXIT=2000; CHUNK=20000; TARGET_TIMEOUT=10800; FIT_TIMEOUT=14400
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
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        for arm in current_2m mega_eq_2m mega_full_4m; do
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
  rm -f "$W"/*.feat "$W"/*.npy "$W"/*.jnnw "$W"/*.jsm 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-([0-9]+)-jass-megacorpus-comparative-fit-v1$ ]] ||
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
say "host=$(hostname) nproc=$(nproc) free_mb=$DFA mode=megacorpus_abc_fit"
monitor

stage persistent-numeric-runtime
if [ ! -f "$VENV_READY" ]; then
  mkdir -p "$(dirname "$VENV")"
  python3 -m venv --clear "$VENV"
  "$VENV/bin/python" -m pip install --disable-pip-version-check --only-binary=:all: \
    numpy scipy >"$W/pip-bootstrap-once.log" 2>&1
  "$VENV/bin/python" - "$VENV_READY" "$JASS_JOB_ID" <<'PY'
import json,numpy,scipy,sys
open(sys.argv[1],'w').write(json.dumps({
 'schema':'jass.numeric_cache.v1','created_by':sys.argv[2],
 'numpy':numpy.__version__,'scipy':scipy.__version__,
},indent=2,sort_keys=True)+'\n')
PY
fi
PY="$VENV/bin/python"
"$PY" -c 'import numpy, scipy; assert numpy.__version__; assert scipy.__version__' ||
  die "persistent numeric venv mismatch"
"$PY" - "$ART/python-runtime.json" "$VENV" <<'PY'
import json,numpy,scipy,sys
open(sys.argv[1],'w').write(json.dumps({
 'schema':'jass.python_runtime.v1','venv':sys.argv[2],
 'stack':'current-compatible-cpx','numpy':numpy.__version__,'scipy':scipy.__version__,
 'pytorch_installed_or_required':False,'persistent_cache':True,
},indent=2,sort_keys=True)+'\n')
PY

stage repository-contract-tests
python3 -m py_compile jobs/tools/jass_megacorpus_materialize.py \
  jobs/tools/l3_conditional_targets.py jobs/tools/verify_optimizer_convergence.py
"$PY" -m unittest jobs.tests.test_jass_megacorpus_materialize \
  jobs.tests.test_jass_megacorpus_smoke_template \
  jobs.tests.test_jass_megacorpus_comparative_template >"$W/tests.log" 2>&1

stage fetch-four-immutable-input-certificates
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_ROOT" \
  --file artefacts/turnover1to1.jnnw.gz=turnover.jnnw.gz \
  --file artefacts/turnover1to1.jsm.gz=turnover.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-turnover.json" >"$W/fetch-turnover.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$UNIFORM_ROOT" \
  --file artefacts/uniform.jnnw.gz=uniform.jnnw.gz \
  --file artefacts/uniform.jsm.gz=uniform.jsm.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=uniform-summary.json \
  --out-dir "$IN" --report "$ART/verified-uniform.json" >"$W/fetch-uniform.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$L2LOW_ROOT" \
  --file artefacts/control.pjtw.gz=l2low.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-l2low.json" >"$W/fetch-l2low.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$SMOKE_ROOT" \
  --file artefacts/mega-manifest.json=smoke-mega-manifest.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=smoke-summary.json \
  --out-dir "$IN" --report "$ART/verified-smoke.json" >"$W/fetch-smoke.log" 2>&1
python3 - "$ART" "$IN/uniform-summary.json" "$TURNOVER_JOB" "$UNIFORM_JOB" \
  "$UNIFORM_ATTEMPT" "$UNIFORM_CODE_SHA" "$L2LOW_JOB" "$SMOKE_JOB" "$UNIFORM_RECORDS" <<'PY'
import json,sys
art=sys.argv[1]
turn=json.load(open(f'{art}/verified-turnover.json'))
uni=json.load(open(f'{art}/verified-uniform.json'))
l2=json.load(open(f'{art}/verified-l2low.json'))
smoke=json.load(open(f'{art}/verified-smoke.json'))
summary=json.load(open(sys.argv[2])); records=int(sys.argv[9])
if turn.get('job_id') != sys.argv[3]: raise SystemExit('TURNOVER identity drift')
if (uni.get('job_id'),uni.get('attempt_id'),uni.get('code_sha')) != tuple(sys.argv[4:7]):
 raise SystemExit('UNIFORM identity drift')
if l2.get('job_id') != sys.argv[7]: raise SystemExit('L2LOW identity drift')
if smoke.get('job_id') != sys.argv[8]: raise SystemExit('smoke identity drift')
arm=(summary.get('arms') or {}).get('uniform') or {}; policy=summary.get('policy') or {}
if summary.get('verdict') != 'L3_PURE_HARD_REPLAY_LARGE_SOURCE_READY':
 raise SystemExit('UNIFORM verdict drift')
if summary.get('external_teacher_inputs') != 0 or policy.get('name') != 'uniform':
 raise SystemExit('UNIFORM is not autonomous general self-play')
if arm.get('records') != records or (arm.get('generation') or {}).get('topk_ranked_plies') != 0:
 raise SystemExit('UNIFORM policy/size drift')
for key in ('data_raw_sha256','meta_raw_sha256'):
 if not isinstance(arm.get(key),str) or len(arm[key]) != 64: raise SystemExit(f'missing {key}')
PY
gunzip -c "$IN/turnover.jnnw.gz" >"$W/turnover.raw.jnnw"
gunzip -c "$IN/turnover.jsm.gz" >"$W/turnover.raw.jsm"
gunzip -c "$IN/uniform.jnnw.gz" >"$W/uniform.raw.jnnw"
gunzip -c "$IN/uniform.jsm.gz" >"$W/uniform.raw.jsm"
gunzip -c "$IN/l2low.pjtw.gz" >"$W/l2low.pjtw"
[ "$(sha256sum "$W/turnover.raw.jnnw" | awk '{print $1}')" = "$TURNOVER_CORPUS_SHA" ] ||
  die "TURNOVER corpus hash drift"
[ "$(sha256sum "$W/turnover.raw.jsm" | awk '{print $1}')" = "$TURNOVER_META_SHA" ] ||
  die "TURNOVER metadata hash drift"
[ "$(sha256sum "$W/l2low.pjtw" | awk '{print $1}')" = "$L2LOW_SHA" ] ||
  die "L2LOW hash drift"

stage materialize-current-reference
python3 tools/selfplay_frontier.py split \
  --data "$W/turnover.raw.jnnw" --meta "$W/turnover.raw.jsm" \
  --out-data "$W/current_2m.jnnw" --out-meta "$W/current_2m.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$ART/current_2m-manifest.json" >"$W/split-current.log" 2>&1
python3 - "$ART/current_2m-manifest.json" "$CURRENT_RECORDS" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); expected=int(sys.argv[2])
if d.get('records') != expected or d.get('train_records',0) <= 0 or d.get('holdout_records',0) <= 0:
 raise SystemExit(f'CURRENT_2M split drift: {d}')
PY

make_mega_arm(){
  local arm="$1" modulus="$2"
  python3 - "$IN/uniform-summary.json" "$ART/verified-uniform.json" \
    "$W/$arm-source-selection.json" "$W/uniform.raw.jnnw" "$W/uniform.raw.jsm" \
    "$UNIFORM_ROOT" "$modulus" "$SAMPLE_SEED" <<'PY'
import json,sys
summary=json.load(open(sys.argv[1])); verified=json.load(open(sys.argv[2])); arm=summary['arms']['uniform']
doc={'schema':'jass.megacorpus.source_selection.v1',
 'selection_policy':'authenticated post-fix general UNIFORM; complete-game nested comparative sample',
 'sources':[{'source_id':1,'name':'HOME1044_UNIFORM40M_POST_FIX',
  'data_path':sys.argv[4],'meta_path':sys.argv[5],
  'expected_data_raw_sha256':arm['data_raw_sha256'],'expected_meta_raw_sha256':arm['meta_raw_sha256'],
  'expected_records':arm['records'],'source_uri':sys.argv[6],
  'source_job':verified['job_id'],'source_attempt':verified['attempt_id'],'source_code_sha':verified['code_sha'],
  'generation_date':'2026-07-29','generator_model':summary['parent'],'selfplay':summary['policy'],
  'quality_class':'authenticated_general_post_drawn_root_fix',
  'sampling':{'mode':'game_hash_mod','modulus':int(sys.argv[7]),'residue':0,'seed':int(sys.argv[8])}}]}
open(sys.argv[3],'w').write(json.dumps(doc,indent=2,sort_keys=True)+'\n')
PY
  timeout 3600s "$PY" jobs/tools/jass_megacorpus_materialize.py \
    --source-spec "$W/$arm-source-selection.json" \
    --out-data "$W/$arm.jnnw" --out-meta "$W/$arm.jsm" \
    --origin-source-out "$W/$arm-origin-source.npy" \
    --origin-index-out "$W/$arm-origin-index.npy" \
    --source-table-out "$ART/$arm-source-table.json" \
    --manifest "$ART/$arm-manifest.json" \
    --holdout-mod "$HOLDOUT_MOD" --split-seed "$SPLIT_SEED" \
    >"$W/materialize-$arm.log" 2>&1
  cp "$W/$arm-source-selection.json" "$ART/$arm-source-selection.json"
}
stage materialize-nested-mega-samples
make_mega_arm mega_eq_2m 20
make_mega_arm mega_full_4m 10

stage prove-equal-volume-arm-is-subset-of-full-arm
"$PY" - "$W" "$ART/nested-sample-proof.json" "$IN/smoke-mega-manifest.json" <<'PY'
import json,sys
from pathlib import Path
import numpy as np
w=Path(sys.argv[1]); out=Path(sys.argv[2]); prior=json.load(open(sys.argv[3]))
b=np.load(w/'mega_eq_2m-origin-index.npy',mmap_mode='r')
c=np.load(w/'mega_full_4m-origin-index.npy',mmap_mode='r')
ordered=np.sort(np.asarray(c))
at=np.searchsorted(ordered,b)
ok=bool(np.all(at < len(ordered)) and np.array_equal(ordered[at],b))
if not ok: raise SystemExit('B is not a record subset of C')
def load(name): return json.load(open(out.parent/name))
bm=load('mega_eq_2m-manifest.json'); cm=load('mega_full_4m-manifest.json')
if not 1_500_000 < bm['records'] < 2_500_000: raise SystemExit('B volume outside guard')
if not 3_000_000 < cm['records'] < 5_000_000: raise SystemExit('C volume outside guard')
for key in ('data','meta','origin_source_id','origin_record_index'):
 if cm['files'][key]['sha256'] != prior['files'][key]['sha256']:
  raise SystemExit(f'C does not reproduce certified 1332 materialization: {key}')
payload={'schema':'jass.megacorpus.nested_sample_proof.v1','B_is_record_subset_of_C':True,
 'B_records':int(len(b)),'C_records':int(len(c)),'B_fraction_of_C':float(len(b)/len(c)),
 'selection':'same game hash and seed; modulus 20 residue 0 nested in modulus 10 residue 0',
 'C_reproduces_smoke_1332_data_meta_and_provenance_sha256':True}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY

stage build-production-120-extra-features
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] ||
  die "8cf geometry mismatch"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
  -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "missing jass binary"
for arm in current_2m mega_eq_2m mega_full_4m; do
  timeout 5400s "$J" --dump-eval-features "$W/$arm.jnnw" "$W/$arm.feat" >"$W/features-$arm.log" 2>&1
  K=$(python3 -c 'import struct,sys;f=open(sys.argv[1],"rb");assert f.read(4)==b"FEAT";print(struct.unpack("<II",f.read(8))[1])' "$W/$arm.feat")
  [ "$K" -eq "$EXPECTED_EXTRAS" ] || die "$arm architecture guard: extras=$K"
done

arm_counts(){
  local arm="$1" manifest
  if [ "$arm" = current_2m ]; then
    manifest="$ART/current_2m-manifest.json"
  else
    manifest="$ART/$arm-manifest.json"
  fi
  python3 - "$manifest" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
print(d['records'],d['records']-d['holdout_records'],d['holdout_records'])
PY
}

stage reconstruct-independent-aligned-context30-targets
for arm in current_2m mega_eq_2m mega_full_4m; do
  read -r records train holdout < <(arm_counts "$arm")
  [ "$records" -gt 0 ] && [ "$train" -gt 0 ] && [ "$holdout" -gt 0 ] || die "$arm empty split"
  /usr/bin/time -f '%e' -o "$W/targets-$arm.seconds" timeout "$TARGET_TIMEOUT" \
    "$PY" jobs/tools/l3_conditional_targets.py \
      --data "$W/$arm.jnnw" --meta "$W/$arm.jsm" --feat "$W/$arm.feat" \
      --train-count "$train" --aligned-out "$W/$arm-context30.npy" \
      --shuffled-out "$W/$arm-shuffled.npy" --report "$ART/$arm-conditional-targets.json" \
      --alpha 0.30 >"$W/targets-$arm.log" 2>&1
  rm -f "$W/$arm-shuffled.npy"
done

fit_arm(){
  local arm="$1" records train holdout
  read -r records train holdout < <(arm_counts "$arm")
  stage "fit-$arm"
  /usr/bin/time -f '%e' -o "$W/fit-$arm.seconds" timeout "$FIT_TIMEOUT" \
    env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" PYTHONUNBUFFERED=1 \
    "$PY" pattern_jass/tools/train_stream.py \
      --data "$W/$arm.jnnw" --feat "$W/$arm.feat" --out "$W/$arm.pjtw" \
      --target external --target-values "$W/$arm-context30.npy" \
      --targets-report "$ART/$arm-target-consumption.json" \
      --loss logistic --exact-fold --tempo-stage \
      --prior-mean "$W/l2low.pjtw" --prior-decay 0 \
      --holdout-count "$holdout" --l2 1e-5 --max-iter "$MAXIT" \
      --chunk "$CHUNK" --lbfgs-maxcor 20 --lbfgs-gtol 1e-4 --prune \
      --optimizer-report "$ART/$arm-optimizer.json" >"$W/fit-$arm.log" 2>&1
  [ -s "$W/$arm.pjtw" ] || die "$arm fit produced no PJTW"
  "$PY" jobs/tools/verify_optimizer_convergence.py \
    --report "$ART/$arm-optimizer.json" --label "$arm" \
    --expected-max-iterations "$MAXIT" --expected-maxcor 20 \
    --expected-gtol 1e-4 --receipt "$ART/$arm-convergence.json"
  gzip -n -c "$W/$arm.pjtw" >"$ART/$arm.pjtw.gz"
  gzip -n -c "$W/$arm-context30.npy" >"$ART/$arm-context30.npy.gz"
}

stage sequential-contention-free-abc-fits
for arm in current_2m mega_eq_2m mega_full_4m; do
  fit_arm "$arm"
done

stage publish-comparative-fit-certificate
"$PY" - "$W" "$ART" "$EXPECTED_CODE_SHA" "$MAXIT" <<'PY'
import hashlib,json,re,struct,sys
from pathlib import Path
w,art=Path(sys.argv[1]),Path(sys.argv[2]); code_sha=sys.argv[3]; maxit=int(sys.argv[4])
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1<<20),b''): h.update(block)
 return h.hexdigest()
def manifest(arm):
 name='current_2m-manifest.json' if arm=='current_2m' else f'{arm}-manifest.json'
 return json.load(open(art/name))
def validate_model(path):
 with path.open('rb') as f: header=f.read(20)
 if len(header)!=20: raise SystemExit(f'{path}: truncated PJTW')
 magic,version,scale,n_pat,n_ext=struct.unpack('<5I',header)
 expected=20+4*2*(n_pat+n_ext)
 if (magic!=0x57544A50 or (version&0xFF)!=3 or version&~(0xFF|0x100|0x200)
     or scale<=0 or n_pat!=4251528 or n_ext!=120 or path.stat().st_size!=expected):
  raise SystemExit(f'{path}: invalid PJTW structure')
 return {'version':version,'scale':scale,'n_pat':n_pat,'n_ext':n_ext,
         'size_bytes':path.stat().st_size,'weight_count':2*(n_pat+n_ext)}
labels={'current_2m':'CURRENT_2M','mega_eq_2m':'MEGA_EQ_2M','mega_full_4m':'MEGA_FULL_4M'}
arms={}
for arm,label in labels.items():
 m=manifest(arm); opt=json.load(open(art/f'{arm}-optimizer.json'))
 targets=json.load(open(art/f'{arm}-conditional-targets.json'))
 consumed=json.load(open(art/f'{arm}-target-consumption.json'))
 log=(w/f'fit-{arm}.log').read_text(errors='replace')
 hm=re.search(r'HOLDOUT_LOGLOSS\s+([0-9.]+)',log)
 tm=list(re.finditer(r'train_loss=([0-9.]+)',log))
 if consumed['source']['sha256'] != targets['outputs']['aligned_sha256']:
  raise SystemExit(f'{arm}: target consumption drift')
 model=w/f'{arm}.pjtw'
 arms[label]={'records':m['records'],'train_records':m['records']-m['holdout_records'],
  'holdout_records':m['holdout_records'],'target':'CONTEXT_30_ALIGNED',
  'context_oof_mse_gain_vs_state_blind':targets['mapping']['oof_mse_gain_vs_state_blind'],
  'target_builder_seconds':float((w/f'targets-{arm}.seconds').read_text()),
  'fit_seconds':float((w/f'fit-{arm}.seconds').read_text()),
  'optimizer':opt,'train_loss':float(tm[-1].group(1)) if tm else None,
  'own_distribution_holdout_logloss':float(hm.group(1)) if hm else None,
  'own_distribution_holdout_is_not_cross_arm_ranking_metric':True,
  'model_raw_sha256':sha(model),'model_gz_sha256':sha(art/f'{arm}.pjtw.gz'),
  'model_header':validate_model(model)}
proof=json.load(open(art/'nested-sample-proof.json'))
payload={'schema':'jass.megacorpus.comparative_fit.v1',
 'verdict':'JASS_MEGACORPUS_ABC_FITS_READY','code_sha':code_sha,'arms':arms,
 'fixed_recipe':{'architecture':'8cf_exact_fold_tempo_120_extras',
  'target':'CONTEXT_30_ALIGNED_alpha_0.30','parent':'L2LOW','prior_decay':0,
  'l2':1e-5,'max_iterations':maxit,'lbfgs_maxcor':20,'gtol':1e-4,'chunk':20000},
 'nested_sample_proof':proof,'execution':'sequential_on_same_CPX_to_avoid_contention',
 'raw_own_holdout_losses_cross_comparable':False,'common_independent_evaluation_required':True,
 'frozen_cohorts_read':0,'new_selfplay_generated':False,'scientific_strength_verdict':None,
 'promotion_authorized':False,'automatic_next_job':None,
 'next_step':'common_independent_static_and_paired_strength_evaluation'}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY
touch "$ART/VERDICT__JASS_MEGACORPUS_ABC_FITS_READY"
touch "$ART/PROMOTION_AUTHORIZED__FALSE" "$ART/AUTOMATIC_NEXT_JOB__NULL"
say "JASS_MEGACORPUS_ABC_FITS_READY arms=CURRENT_2M,MEGA_EQ_2M,MEGA_FULL_4M promotion=false"
