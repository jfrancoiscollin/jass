#!/usr/bin/env bash
# Corrected CTX3 paired alpha=.30 production fit.
# Scientific protocol and immutable inputs match certified 1418; only the
# proven dense-extras exact-fold defect is corrected inside the optimizer.
# No self-play, force games, frozen read, automatic continuation or promotion.
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
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; cp "$STAGE" "$ART/STAGE.txt"; }

CORPUS_ROOT="r2:jass-data/runs/cpx62-1409-l3-context2-intervention-corpus-v1/20260818T184956Z-3465ec72"
MAPPER_ROOT="r2:jass-data/runs/cpx62-1417-l3-context3-exact-tanh-mapper-screen-v1/20260819T072356Z-999091b3"
CURRICULUM_ROOT="r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/20260814T191555Z-18c38a33"
SMOKE1426_ROOT="r2:jass-data/runs/cpx62-1426-l3-context3-exact-extras-fit-smoke-v1/20260819T215156Z-040da98c"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
EXPECTED_RECORDS=2000000; EXPECTED_EXTRAS=120
SPLIT_SEED=577215; HOLDOUT_MOD=10; MAXIT=2000; CHUNK=20000
TARGET_TIMEOUT=3600; FIT_TIMEOUT=28800
MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        for arm in aligned shuffled; do
          [ -f "$W/fit-$arm.log" ] && printf '%s_fit_log_lines=%s\n' "$arm" "$(wc -l < "$W/fit-$arm.log")"
        done
      } >"$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120
    done ) & MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -maxdepth 1 -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$IN" "$W" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-([0-9]+)-l3-context3-paired-patterneval-exact-extras-v2$ ]] || die "invalid job nomenclature"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "explicit execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] || die "frozen-read guard missing"
[ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] || die "promotion guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "persistent numeric runtime absent; do not reinstall"
PY="$VENV/bin/python"; "$PY" -c 'import numpy,scipy; assert numpy.__version__ and scipy.__version__' || die "numeric runtime invalid"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 20480 ] || die "less than 20 GiB free ($DFA MiB)"
say "host=$(hostname) nproc=$(nproc) mode=ctx3_paired_patterneval_exact_extras_v2 eta_minutes=45-150"
say "records=2000000 alpha=0.30 arms=aligned,shuffled same_1418_protocol=1 corrected_dense_extras=1 selfplay=0 force=0 frozen=0"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_context3_paired_targets.py jobs/tools/verify_optimizer_convergence.py \
  pattern_jass/tools/exact_extras.py pattern_jass/tools/train_stream_exact.py
"$PY" -m unittest jobs.tests.test_l3_context3_paired_targets \
  jobs.tests.test_l3_context3_paired_patterneval_template \
  jobs.tests.test_exact_extras_fit_contract \
  jobs.tests.test_l3_context3_paired_patterneval_exact_template >"$W/tests.log" 2>&1

stage authenticate-mechanistic-prerequisite-1426
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$SMOKE1426_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=smoke1426-summary.json \
  --file artefacts/mechanistic-verification.json=smoke1426-mechanistic.json \
  --out-dir "$IN" --report "$ART/verified-1426.json" --expected-state completed >"$W/fetch-1426.log" 2>&1
"$PY" - "$ART/verified-1426.json" "$IN/smoke1426-summary.json" "$IN/smoke1426-mechanistic.json" <<'PY'
import json,sys
v,s,m=(json.load(open(p)) for p in sys.argv[1:4])
ident=(v.get('job_id'),v.get('attempt_id'),v.get('code_sha'),v.get('result_state'),v.get('exit_code'))
expected=('cpx62-1426-l3-context3-exact-extras-fit-smoke-v1','20260819T215156Z-040da98c','040da98c215bac82b5bc3c97ad1a144d35f7de53','completed',0)
if ident != expected: raise SystemExit(f'1426 immutable identity drift: {ident}')
for row in (s,m):
 if row.get('verdict')!='JASS_CONTEXT3_EXACT_EXTRAS_FIT_CONTRACT_VERIFIED': raise SystemExit('1426 verdict drift')
 if row.get('production_fit_performed') is not False or row.get('selfplay')!=0 or row.get('strength_games')!=0 or row.get('frozen_read') is not False or row.get('promotion_authorized') is not False:
  raise SystemExit('1426 safety certificate drift')
 for phase in ('mg','eg'):
  if row.get(phase,{}).get('max_abs') != 0: raise SystemExit(f'1426 {phase} residual drift')
PY

stage fetch-authenticated-immutable-scientific-inputs
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CORPUS_ROOT" \
  --file artefacts/context2-intervention-2m.jnnw.gz=intervention.jnnw.gz \
  --file artefacts/context2-intervention-2m.jsm.gz=intervention.jsm.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=corpus-summary.json \
  --out-dir "$IN" --report "$ART/verified-corpus.json" --expected-state completed >"$W/fetch-corpus.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$MAPPER_ROOT" \
  --file artefacts/context3-exact-tanh-mapper-screen.json=mapper-report.json \
  --file artefacts/ctx3-aligned-mapper-prediction.npy=aligned-prediction.npy \
  --file artefacts/JASS_CONTROL_SUMMARY.json=mapper-summary.json \
  --file artefacts/split.json=mapper-split.json \
  --out-dir "$IN" --report "$ART/verified-mapper.json" --expected-state completed >"$W/fetch-mapper.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=curriculum-summary.json \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" --expected-state completed >"$W/fetch-curriculum.log" 2>&1

"$PY" - "$ART" "$IN" <<'PY'
import json,sys
from pathlib import Path
art,src=map(Path,sys.argv[1:3])
expected={
 'verified-corpus.json':('cpx62-1409-l3-context2-intervention-corpus-v1','20260818T184956Z-3465ec72','3465ec720eb37c5c9368f2df048831f7381c5839'),
 'verified-mapper.json':('cpx62-1417-l3-context3-exact-tanh-mapper-screen-v1','20260819T072356Z-999091b3','999091b34cbbaf4ab1b61e94f70647da21e7ddc1'),
 'verified-curriculum.json':('cpx62-1341-jass-megacorpus-arm-d-fit-v1','20260814T191555Z-18c38a33','18c38a33ae78c9c2e8e2df62fca266da28dacead')}
for name,identity in expected.items():
 row=json.load(open(art/name)); got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha'))
 if got!=identity or row.get('result_state')!='completed' or row.get('exit_code')!=0: raise SystemExit(f'{name}: identity/state drift {got}')
if json.load(open(src/'corpus-summary.json')).get('verdict')!='JASS_CONTEXT2_INTERVENTION_CORPUS_READY': raise SystemExit('corpus verdict drift')
mapper=json.load(open(src/'mapper-summary.json'))
if mapper.get('verdict')!='JASS_CONTEXT3_EXACT_TANH_MAPPER_SCREEN_PASSED' or not mapper.get('screen_passed') or not all((mapper.get('guards') or {}).values()): raise SystemExit('mapper gate did not pass')
if json.load(open(src/'curriculum-summary.json')).get('verdict')!='JASS_MEGACORPUS_ARM_D_FIT_READY': raise SystemExit('CURRICULUM certificate drift')
PY

gunzip -c "$IN/intervention.jnnw.gz" >"$W/source.jnnw"
gunzip -c "$IN/intervention.jsm.gz" >"$W/source.jsm"
gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
[ "$(sha256sum "$W/curriculum.pjtw" | awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM drift"

stage reconstruct-identical-1418-opening-split
python3 tools/selfplay_frontier.py split --data "$W/source.jnnw" --meta "$W/source.jsm" \
  --out-data "$W/intervention.jnnw" --out-meta "$W/intervention.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" --manifest "$ART/split.json" >"$W/split.log" 2>&1
read -r RECORDS TRAIN HOLDOUT < <("$PY" - "$ART/split.json" "$IN/mapper-split.json" <<'PY'
import json,sys
a,b=(json.load(open(p)) for p in sys.argv[1:3])
for key in ('records','train_records','holdout_records','data_sha256','meta_sha256'):
 if a.get(key)!=b.get(key): raise SystemExit(f'split drift {key}')
print(a['records'],a['train_records'],a['holdout_records'])
PY
)
[ "$RECORDS" -eq "$EXPECTED_RECORDS" ] && [ "$TRAIN" -gt 0 ] && [ "$HOLDOUT" -gt 0 ] || die "split sizing drift"
rm -f "$W/source.jnnw" "$W/source.jsm"

stage build-identical-1418-production-pattern-features
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] || die "8cf geometry drift"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass jass_tests >"$W/build.log" 2>&1
"$W/build/jass_tests" >"$W/cpp-tests.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "missing jass binary"
timeout 7200s "$J" --dump-eval-features "$W/intervention.jnnw" "$W/intervention.feat" >"$W/features.log" 2>&1
K=$(python3 -c 'import struct,sys;f=open(sys.argv[1],"rb");assert f.read(4)==b"FEAT";print(struct.unpack("<II",f.read(8))[1])' "$W/intervention.feat")
[ "$K" -eq "$EXPECTED_EXTRAS" ] || die "architecture guard extras=$K"

stage build-identical-1418-paired-ctx3-alpha30-targets
timeout "$TARGET_TIMEOUT" "$PY" jobs/tools/l3_context3_paired_targets.py \
  --data "$W/intervention.jnnw" --meta "$W/intervention.jsm" \
  --prediction "$IN/aligned-prediction.npy" --mapper-report "$IN/mapper-report.json" \
  --train-count "$TRAIN" --aligned-out "$W/aligned.npy" --shuffled-out "$W/shuffled.npy" \
  --report "$ART/context3-paired-targets.json" --alpha 0.30 \
  --fold-seed 20260811 --shuffle-seed 2026081906 >"$W/targets.log" 2>&1
"$PY" - "$ART/context3-paired-targets.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); s=r['shuffle_control']
if r.get('verdict')!='JASS_CONTEXT3_PAIRED_TARGETS_READY' or r['target'].get('alpha')!=0.30: raise SystemExit('paired-target verdict drift')
if s.get('fixed_point_count')!=0 or not s.get('all_final_target_marginals_preserved') or not s.get('all_sources_within_same_fold') or not s.get('all_sources_within_same_stratum'): raise SystemExit('causal shuffle drift')
PY
gzip -n -c "$W/aligned.npy" >"$ART/ctx3-aligned-target.npy.gz"
gzip -n -c "$W/shuffled.npy" >"$ART/ctx3-shuffled-target.npy.gz"

certify_exact_extras(){
  local arm="$1"
  "$PY" - "$W/$arm.pjtw" "$ART/$arm-exact-extras.json" <<'PY'
import json,struct,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,'pattern_jass/tools')
from exact_extras import exact_extras_residuals
p,out=Path(sys.argv[1]),Path(sys.argv[2]); raw=p.read_bytes()
magic,ver,scale,np_,ne=struct.unpack_from('<5I',raw,0)
if magic!=0x57544A50 or (ver&255)!=3 or ne!=120: raise SystemExit(f'PJTW architecture drift {(hex(magic),ver,scale,np_,ne)}')
base=20+2*np_*4
mg=np.frombuffer(raw,dtype='<i4',count=ne,offset=base).copy(); eg=np.frombuffer(raw,dtype='<i4',count=ne,offset=base+ne*4).copy()
a={'mg':exact_extras_residuals(mg),'eg':exact_extras_residuals(eg)}
if a['mg']['max_abs']!=0 or a['eg']['max_abs']!=0: raise SystemExit(f'serialized dense exact residual {a}')
out.write_text(json.dumps(a,indent=2,sort_keys=True)+'\n')
PY
}

fit_arm(){
  local arm="$1"
  stage "fit-$arm-patterneval-corrected-exact-extras"
  /usr/bin/time -f '%e' -o "$W/fit-$arm.seconds" timeout "$FIT_TIMEOUT" \
    env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" PYTHONUNBUFFERED=1 \
    "$PY" pattern_jass/tools/train_stream_exact.py \
      --data "$W/intervention.jnnw" --feat "$W/intervention.feat" --out "$W/$arm.pjtw" \
      --target external --target-values "$W/$arm.npy" \
      --targets-report "$ART/$arm-target-consumption.json" \
      --loss logistic --exact-fold --tempo-stage \
      --prior-mean "$W/curriculum.pjtw" --prior-decay 0 \
      --holdout-count "$HOLDOUT" --l2 1e-5 --max-iter "$MAXIT" \
      --chunk "$CHUNK" --lbfgs-maxcor 20 --lbfgs-gtol 1e-4 --prune \
      --optimizer-report "$ART/$arm-optimizer.json" >"$W/fit-$arm.log" 2>&1
  [ -s "$W/$arm.pjtw" ] || die "$arm produced no model"
  "$PY" jobs/tools/verify_optimizer_convergence.py --report "$ART/$arm-optimizer.json" \
    --label "$arm" --expected-max-iterations "$MAXIT" --expected-maxcor 20 \
    --expected-gtol 1e-4 --receipt "$ART/$arm-convergence.json"
  certify_exact_extras "$arm"
  gzip -n -c "$W/$arm.pjtw" >"$ART/$arm.pjtw.gz"
}

stage sequential-contention-free-corrected-paired-fits
fit_arm aligned
fit_arm shuffled

stage publish-corrected-paired-model-certificate
"$PY" - "$W" "$ART" "$EXPECTED_CODE_SHA" "$CURRICULUM_SHA" <<'PY' | tee -a "$RES"
import hashlib,json,struct,sys
from pathlib import Path
w,art=Path(sys.argv[1]),Path(sys.argv[2]); code=sys.argv[3]; parent_sha=sys.argv[4]
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1<<20),b''): h.update(block)
 return h.hexdigest()
def structure(path):
 path=Path(path); magic,version,scale,n_pat,n_ext=struct.unpack('<5I',path.read_bytes()[:20])
 expected=20+8*(n_pat+n_ext)
 if (magic!=0x57544A50 or (version&0xff)!=3 or scale<=0 or n_pat!=4251528 or n_ext!=120 or path.stat().st_size!=expected): raise SystemExit(f'{path}: PJTW drift')
 return {'version':version,'scale':scale,'n_patterns':n_pat,'n_extras':n_ext,'size_bytes':path.stat().st_size}
targets=json.load(open(art/'context3-paired-targets.json')); models={}
for arm in ('aligned','shuffled'):
 consumption=json.load(open(art/f'{arm}-target-consumption.json'))
 if consumption['source']['sha256']!=targets['outputs'][f'{arm}_sha256']: raise SystemExit(f'{arm}: consumed wrong target')
 exact=json.load(open(art/f'{arm}-exact-extras.json'))
 if exact['mg']['max_abs']!=0 or exact['eg']['max_abs']!=0: raise SystemExit(f'{arm}: exact extras certificate drift')
 model=w/f'{arm}.pjtw'
 models[arm]={'model_raw_sha256':sha(model),'model_gz_sha256':sha(art/f'{arm}.pjtw.gz'),
  'structure':structure(model),'optimizer':json.load(open(art/f'{arm}-optimizer.json')),
  'convergence':json.load(open(art/f'{arm}-convergence.json')),'exact_extras':exact,
  'target_sha256':targets['outputs'][f'{arm}_sha256'],'fit_seconds':float((w/f'fit-{arm}.seconds').read_text())}
if models['aligned']['model_raw_sha256']==models['shuffled']['model_raw_sha256']: raise SystemExit('paired models unexpectedly identical')
payload={'schema':'jass.l3_context3_paired_patterneval_models_exact_extras.v2',
 'verdict':'JASS_CONTEXT3_PAIRED_PATTERNEVAL_EXACT_EXTRAS_MODELS_READY','code_sha':code,
 'mechanistic_prerequisite':{'job_id':'cpx62-1426-l3-context3-exact-extras-fit-smoke-v1','attempt_id':'20260819T215156Z-040da98c','verdict':'JASS_CONTEXT3_EXACT_EXTRAS_FIT_CONTRACT_VERIFIED'},
 'scientific_protocol_reference':'cpx62-1418-l3-context3-paired-patterneval-fit-v1/20260819T074026Z-1e718553',
 'corpus':'CTX2_INTERVENTION_1409_2M','records':targets['records'],
 'train_records':targets['train_records'],'holdout_records':targets['holdout_records'],
 'parent':{'label':'CURRICULUM','model_raw_sha256':parent_sha,'prior_source_unchanged':True,'dense_extras_projected_inside_fit':True},
 'selected_candidate':targets['selected_candidate'],'alpha':targets['target']['alpha'],
 'recipe':{'architecture':'8cf_exact_fold_tempo_120_extras','prior_mean':'CURRICULUM','prior_decay':0,
  'l2':1e-5,'gtol':1e-4,'max_iterations':2000,'lbfgs_maxcor':20,
  'dense_extras_constraint':'rot180_colour_swap_projected_design_and_projected_prior'},
 'arms':{'ALIGNED':models['aligned'],'SHUFFLED':models['shuffled']},
 'target_certificate':targets,'primary_contrast':'ALIGNED_vs_SHUFFLED_on_two_fresh_disjoint_opening_pools',
 'fresh_force_pools_required':True,'reuse_1419_force_pools_forbidden':True,
 'strength_games_played':0,'frozen_cohorts_read':0,'new_selfplay_generated':False,
 'promotion_authorized':False,'automatic_next_job':None}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/'VERDICT__JASS_CONTEXT3_PAIRED_PATTERNEVAL_EXACT_EXTRAS_MODELS_READY').touch()
for name in ('SELFPLAY_GENERATED__FALSE','STRENGTH_GAMES_PLAYED__0','FROZEN_READ__FALSE','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_NEXT_JOB__NULL','PATTERNEVAL_PRODUCTION_FITS__2'):
 (art/name).touch()
print(json.dumps(payload,sort_keys=True))
PY
say "JASS_CONTEXT3_PAIRED_PATTERNEVAL_EXACT_EXTRAS_MODELS_READY arms=aligned,shuffled exact_extras=1 force=0 frozen=0 promotion=false"
