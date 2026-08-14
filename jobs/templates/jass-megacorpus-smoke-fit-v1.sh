#!/usr/bin/env bash
# Jass MegaCorpus P2/P3 — authenticated 4M-ish UNIFORM smoke + CONTEXT_30 fit.
# No frozen set, strength result, new self-play, automatic continuation or promotion.
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

UNIFORM_ROOT="r2:jass-data/runs/home-1044-l3-pure-hard-replay-large-source-v1/20260729T070032Z-477da64d"
L2LOW_ROOT="r2:jass-data/runs/cpx62-1164-l3-prior-dose-l2-refit-v1/20260803T060626Z-209eb56b"
UNIFORM_JOB="home-1044-l3-pure-hard-replay-large-source-v1"
UNIFORM_ATTEMPT="20260729T070032Z-477da64d"
UNIFORM_CODE_SHA="477da64da2dea09c8ceb1f1e8e79e2c54d023a5a"
L2LOW_JOB="cpx62-1164-l3-prior-dose-l2-refit-v1"
L2LOW_SHA="ec47e4b37fc7e95dcb390c0a5eddf207e98c0818c1708636d2df9e85b1d149b4"
SOURCE_RECORDS=40000000; EXPECTED_EXTRAS=120
SAMPLE_MOD=10; SAMPLE_RESIDUE=0; SAMPLE_SEED=20260814
HOLDOUT_MOD=10; SPLIT_SEED=577215; MAXIT=25; CHUNK=20000
TARGET_TIMEOUT=10800; FIT_TIMEOUT=10800
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
        [ -f "$W/mega-manifest.json" ] &&
          python3 - "$W/mega-manifest.json" <<'PY' 2>/dev/null || true
import json,sys
d=json.load(open(sys.argv[1]))
print(f"records={d['records']}")
print(f"train_records={d['train_records']}")
print(f"holdout_records={d['holdout_records']}")
PY
        [ -f "$W/fit.log" ] && printf 'fit_log_lines=%s\n' "$(wc -l < "$W/fit.log")"
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
  rm -f "$W"/*.feat "$W"/shuffled.npy 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-([0-9]+)-jass-megacorpus-smoke-fit-v1$ ]] ||
  die "invalid job nomenclature"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "explicit execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 20480 ] || die "less than 20 GiB free (${DFA} MiB)"
say "host=$(hostname) nproc=$(nproc) free_mb=$DFA mode=megacorpus_smoke_fit"
monitor

stage persistent-numeric-runtime
if [ ! -f "$VENV_READY" ]; then
  mkdir -p "$(dirname "$VENV")"
  # A failed bootstrap leaves no READY marker.  The next attempt repairs this
  # single versioned cache in place instead of trusting a partial environment.
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
python3 -m py_compile jobs/tools/jass_megacorpus_materialize.py jobs/tools/l3_conditional_targets.py
"$PY" -m unittest jobs.tests.test_jass_megacorpus_materialize \
  jobs.tests.test_jass_megacorpus_smoke_template >"$W/tests.log" 2>&1

stage fetch-authenticated-historical-source-and-parent
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$UNIFORM_ROOT" \
  --file artefacts/uniform.jnnw.gz=uniform.jnnw.gz \
  --file artefacts/uniform.jsm.gz=uniform.jsm.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=uniform-summary.json \
  --out-dir "$IN" --report "$ART/verified-uniform-source.json" >"$W/fetch-uniform.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$L2LOW_ROOT" \
  --file artefacts/control.pjtw.gz=l2low.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-l2low.json" >"$W/fetch-l2low.log" 2>&1
python3 - "$ART/verified-uniform-source.json" "$ART/verified-l2low.json" \
  "$IN/uniform-summary.json" "$UNIFORM_JOB" "$UNIFORM_ATTEMPT" "$UNIFORM_CODE_SHA" \
  "$L2LOW_JOB" "$SOURCE_RECORDS" <<'PY'
import json,sys
uniform, parent, summary = map(lambda p: json.load(open(p)), sys.argv[1:4])
expected_job, expected_attempt, expected_code, parent_job = sys.argv[4:8]
records = int(sys.argv[8])
if (uniform.get('job_id'), uniform.get('attempt_id'), uniform.get('code_sha')) != (
        expected_job, expected_attempt, expected_code):
    raise SystemExit('UNIFORM result identity drift')
if parent.get('job_id') != parent_job:
    raise SystemExit('L2LOW result identity drift')
arm = (summary.get('arms') or {}).get('uniform') or {}
policy = summary.get('policy') or {}
generation = arm.get('generation') or {}
if summary.get('verdict') != 'L3_PURE_HARD_REPLAY_LARGE_SOURCE_READY':
    raise SystemExit('UNIFORM source verdict mismatch')
if summary.get('external_teacher_inputs') != 0 or policy.get('name') != 'uniform':
    raise SystemExit('UNIFORM source is not autonomous general self-play')
if arm.get('records') != records or generation.get('topk_ranked_plies') != 0:
    raise SystemExit('UNIFORM source size/policy drift')
verified = {row['local_name']: row['sha256'] for row in uniform['files']}
if (verified.get('uniform.jnnw.gz') != arm.get('data_gz_sha256') or
        verified.get('uniform.jsm.gz') != arm.get('meta_gz_sha256')):
    raise SystemExit('UNIFORM certificate/inventory compressed SHA mismatch')
for key in ('data_raw_sha256','meta_raw_sha256'):
    value=arm.get(key)
    if not isinstance(value,str) or len(value)!=64:
        raise SystemExit(f'missing {key}')
PY
gunzip -c "$IN/uniform.jnnw.gz" >"$W/uniform.raw.jnnw"
gunzip -c "$IN/uniform.jsm.gz" >"$W/uniform.raw.jsm"
gunzip -c "$IN/l2low.pjtw.gz" >"$W/l2low.pjtw"
[ "$(sha256sum "$W/l2low.pjtw" | awk '{print $1}')" = "$L2LOW_SHA" ] ||
  die "L2LOW raw SHA drift"

stage freeze-source-selection-and-materialize
python3 - "$IN/uniform-summary.json" "$ART/verified-uniform-source.json" \
  "$W/source-selection.json" "$W/uniform.raw.jnnw" "$W/uniform.raw.jsm" \
  "$UNIFORM_ROOT" "$SAMPLE_MOD" "$SAMPLE_RESIDUE" "$SAMPLE_SEED" <<'PY'
import json,sys
summary=json.load(open(sys.argv[1])); verified=json.load(open(sys.argv[2]))
arm=summary['arms']['uniform']
doc={
 'schema':'jass.megacorpus.source_selection.v1',
 'selection_policy':'P2 smoke: authenticated post-fix general UNIFORM only; specialists, teachers, frozen and known biased legacy corpora excluded',
 'sources':[{
   'source_id':1,
   'name':'HOME1044_UNIFORM40M_POST_FIX',
   'data_path':sys.argv[4], 'meta_path':sys.argv[5],
   'expected_data_raw_sha256':arm['data_raw_sha256'],
   'expected_meta_raw_sha256':arm['meta_raw_sha256'],
   'expected_records':arm['records'],
   'source_uri':sys.argv[6],
   'source_job':verified['job_id'], 'source_attempt':verified['attempt_id'],
   'source_code_sha':verified['code_sha'], 'generation_date':'2026-07-29',
   'generator_model':summary['parent'], 'selfplay':summary['policy'],
   'quality_class':'authenticated_general_post_drawn_root_fix',
   'sampling':{'mode':'game_hash_mod','modulus':int(sys.argv[7]),
               'residue':int(sys.argv[8]),'seed':int(sys.argv[9])},
 }],
}
open(sys.argv[3],'w').write(json.dumps(doc,indent=2,sort_keys=True)+'\n')
PY
timeout 3600s "$VENV/bin/python" jobs/tools/jass_megacorpus_materialize.py \
  --source-spec "$W/source-selection.json" \
  --out-data "$W/mega.fit.jnnw" --out-meta "$W/mega.fit.jsm" \
  --origin-source-out "$W/origin_source_id.npy" \
  --origin-index-out "$W/origin_record_index.npy" \
  --source-table-out "$W/source-table.json" --manifest "$W/mega-manifest.json" \
  --holdout-mod "$HOLDOUT_MOD" --split-seed "$SPLIT_SEED" \
  >"$W/materialize.log" 2>&1
read -r RECORDS TRAIN_COUNT HOLDOUT < <(python3 - "$W/mega-manifest.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); print(d['records'],d['train_records'],d['holdout_records'])
PY
)
[ "$RECORDS" -gt 3000000 ] && [ "$RECORDS" -lt 5000000 ] ||
  die "unexpected 1/10 game sample volume: $RECORDS"
[ "$TRAIN_COUNT" -gt 0 ] && [ "$HOLDOUT" -gt 0 ] || die "empty split"

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
timeout 3600s "$J" --dump-eval-features "$W/mega.fit.jnnw" "$W/mega.feat" \
  >"$W/features.log" 2>&1
K=$(python3 -c 'import struct,sys;f=open(sys.argv[1],"rb");assert f.read(4)==b"FEAT";print(struct.unpack("<II",f.read(8))[1])' "$W/mega.feat")
[ "$K" -eq "$EXPECTED_EXTRAS" ] || die "architecture guard: extras=$K"

stage reconstruct-aligned-context30
/usr/bin/time -f '%e' -o "$W/targets.seconds" timeout "$TARGET_TIMEOUT" \
  "$PY" jobs/tools/l3_conditional_targets.py \
    --data "$W/mega.fit.jnnw" --meta "$W/mega.fit.jsm" \
    --feat "$W/mega.feat" --train-count "$TRAIN_COUNT" \
    --aligned-out "$W/context30.npy" --shuffled-out "$W/shuffled.npy" \
    --report "$ART/conditional-targets.json" --alpha 0.30 \
    >"$W/targets.log" 2>&1

stage fit-megacorpus-context30-smoke
/usr/bin/time -f '%e' -o "$W/fit.seconds" timeout "$FIT_TIMEOUT" \
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
  "$PY" pattern_jass/tools/train_stream.py \
    --data "$W/mega.fit.jnnw" --feat "$W/mega.feat" \
    --out "$W/mega-context30-smoke.pjtw" \
    --target external --target-values "$W/context30.npy" \
    --targets-report "$ART/target-consumption.json" \
    --loss logistic --exact-fold --tempo-stage \
    --prior-mean "$W/l2low.pjtw" --prior-decay 0 \
    --holdout-count "$HOLDOUT" --l2 1e-5 --max-iter "$MAXIT" \
    --chunk "$CHUNK" --lbfgs-maxcor 20 --lbfgs-gtol 1e-4 --prune \
    --optimizer-report "$ART/optimizer.json" >"$W/fit.log" 2>&1
[ -s "$W/mega-context30-smoke.pjtw" ] || die "fit produced no PJTW"

stage publish-reproducible-fit-ready-bundle
cp "$W/source-selection.json" "$ART/source-selection.json"
cp "$W/source-table.json" "$ART/source-table.json"
cp "$W/mega-manifest.json" "$ART/mega-manifest.json"
gzip -n -c "$W/mega.fit.jnnw" >"$ART/mega.fit.jnnw.gz"
gzip -n -c "$W/mega.fit.jsm" >"$ART/mega.fit.jsm.gz"
gzip -n -c "$W/origin_source_id.npy" >"$ART/origin_source_id.npy.gz"
gzip -n -c "$W/origin_record_index.npy" >"$ART/origin_record_index.npy.gz"
gzip -n -c "$W/context30.npy" >"$ART/context30.npy.gz"
gzip -n -c "$W/mega-context30-smoke.pjtw" >"$ART/mega-context30-smoke.pjtw.gz"
python3 - "$W" "$ART" "$RECORDS" "$TRAIN_COUNT" "$HOLDOUT" "$EXPECTED_CODE_SHA" <<'PY'
import hashlib,json,re,struct,sys
from pathlib import Path
w,art=Path(sys.argv[1]),Path(sys.argv[2])
records,train,holdout=map(int,sys.argv[3:6]); code_sha=sys.argv[6]
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1<<20),b''): h.update(block)
 return h.hexdigest()
material=json.load(open(w/'mega-manifest.json'))
targets=json.load(open(art/'conditional-targets.json'))
consumed=json.load(open(art/'target-consumption.json'))
optimizer=json.load(open(art/'optimizer.json'))
if material['records'] != records or targets['records'] != records:
 raise SystemExit('record accounting drift')
if targets['train_records'] != train or targets['holdout_records'] != holdout:
 raise SystemExit('conditional split drift')
if consumed['source']['sha256'] != targets['outputs']['aligned_sha256']:
 raise SystemExit('fit did not consume the certified aligned target')
if consumed['aligned_inputs']['data_sha256'] != material['files']['data']['sha256']:
 raise SystemExit('fit data differs from materialized MegaCorpus')
if int(optimizer.get('iterations',0)) <= 0:
 raise SystemExit('fit performed zero optimizer iterations')
model=w/'mega-context30-smoke.pjtw'
with model.open('rb') as handle:
 header=handle.read(20)
if len(header) != 20:
 raise SystemExit('PJTW export has a truncated header')
magic,version,scale,n_pat,n_ext=struct.unpack('<5I',header)
known_bits=0xFF|0x100|0x200
expected_size=20+4*2*(n_pat+n_ext)
if (magic != 0x57544A50 or (version & 0xFF) != 3 or version & ~known_bits
        or scale <= 0 or n_pat != 4251528 or n_ext != 120
        or model.stat().st_size != expected_size):
 raise SystemExit(f'PJTW structural guard failed: header={(magic,version,scale,n_pat,n_ext)} size={model.stat().st_size} expected={expected_size}')
model_header={'magic':'PJTW','version':version,'scale':scale,'n_pat':n_pat,
              'n_ext':n_ext,'weight_count':2*(n_pat+n_ext),
              'size_bytes':model.stat().st_size}
fit_log=(w/'fit.log').read_text(errors='replace')
holdout_match=re.search(r'HOLDOUT_LOGLOSS\s+([0-9.]+)',fit_log)
train_match=re.search(r'train_loss=([0-9.]+)',fit_log)
payload={
 'schema':'jass.megacorpus.smoke_fit.v1',
 'verdict':'JASS_MEGACORPUS_SMOKE_FIT_READY',
 'code_sha':code_sha,
 'records':records,'train_records':train,'holdout_records':holdout,
 'source_count':material['source_count'],
 'source_record_counts':material['source_record_counts'],
 'target':'CONTEXT_30_ALIGNED','feature_width':targets['feature_width'],
 'context_oof_mse_gain_vs_state_blind':targets['mapping']['oof_mse_gain_vs_state_blind'],
 'target_builder_seconds':float((w/'targets.seconds').read_text().strip()),
 'fit_seconds':float((w/'fit.seconds').read_text().strip()),
 'fit_iterations':int(optimizer['iterations']),
 'fit_converged':bool(optimizer.get('success')),
 'optimizer':optimizer,
 'train_loss':float(train_match.group(1)) if train_match else None,
 'holdout_logloss':float(holdout_match.group(1)) if holdout_match else None,
 'model_raw_sha256':sha(model),
 'model_header':model_header,
 'model_gz_sha256':sha(art/'mega-context30-smoke.pjtw.gz'),
 'fit_ready_bundle':{
   name:{'sha256':sha(art/name),'size_bytes':(art/name).stat().st_size}
   for name in ('mega.fit.jnnw.gz','mega.fit.jsm.gz','origin_source_id.npy.gz',
                'origin_record_index.npy.gz','context30.npy.gz')
 },
 'frozen_cohorts_read':0,'strength_or_loss_used_for_source_selection':False,
 'new_selfplay_generated':False,'scientific_strength_verdict':None,
 'promotion_authorized':False,'automatic_next_job':None,
}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY
touch "$ART/VERDICT__JASS_MEGACORPUS_SMOKE_FIT_READY"
touch "$ART/PROMOTION_AUTHORIZED__FALSE" "$ART/AUTOMATIC_NEXT_JOB__NULL"
say "JASS_MEGACORPUS_SMOKE_FIT_READY records=$RECORDS train=$TRAIN_COUNT holdout=$HOLDOUT promotion=false"
