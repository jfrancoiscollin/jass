#!/usr/bin/env bash
# Refit the complete certified Curriculum recipe with aligned CTX2 alpha=1.
# No games, frozen cohort, force decision, child job, or promotion.
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
ABC_ROOT="r2:jass-data/runs/cpx62-1340-jass-megacorpus-comparative-fit-v1/20260814T123246Z-2ce07222"
CURRICULUM_ROOT="r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/20260814T191555Z-18c38a33"
TURNOVER_SHA="9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
META_SHA="acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
L2LOW_SHA="ec47e4b37fc7e95dcb390c0a5eddf207e98c0818c1708636d2df9e85b1d149b4"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
UNIFORM_RECORDS=40000000; CURRENT_RECORDS=2000000; EXPECTED_EXTRAS=120
EXPECTED_CONTEXT=30; SAMPLE_SEED=20260814; HOLDOUT_MOD=10; SPLIT_SEED=577215
MAXIT=2000; CHUNK=20000; TARGET_TIMEOUT=28800; FIT_TIMEOUT=28800
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
        for arm in mega_full_4m current_2m; do
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
[[ "$JASS_JOB_ID" =~ ^cpx62-([0-9]+)-l3-context2-curriculum-full-relabel-fit-v1$ ]] ||
  die "invalid job nomenclature"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "explicit execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 24576 ] || die "less than 24 GiB free ($DFA MiB)"
[ -f "$VENV_READY" ] || die "persistent numeric runtime absent; do not reinstall"
PY="$VENV/bin/python"
"$PY" -c 'import numpy, scipy; assert numpy.__version__; assert scipy.__version__' ||
  die "persistent numeric runtime invalid"
say "host=$(hostname) nproc=$(nproc) free_mb=$DFA mode=ctx2_curriculum_full_relabel"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/jass_megacorpus_materialize.py \
  jobs/tools/l3_conditional_targets.py jobs/tools/verify_optimizer_convergence.py
"$PY" -m unittest jobs.tests.test_l3_context2_curriculum_full_relabel_protocol \
  >"$W/protocol-tests.log" 2>&1

stage fetch-authenticated-immutable-sources
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
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$ABC_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=abc-summary.json \
  --file artefacts/current_2m-manifest.json=source-current-manifest.json \
  --file artefacts/mega_full_4m-manifest.json=source-mega-manifest.json \
  --out-dir "$IN" --report "$ART/verified-abc.json" >"$W/fetch-abc.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=curriculum-summary.json \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" >"$W/fetch-curriculum.log" 2>&1

"$PY" - "$ART" "$IN/uniform-summary.json" "$IN/abc-summary.json" \
  "$IN/curriculum-summary.json" <<'PY'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); uniform=json.load(open(sys.argv[2])); abc=json.load(open(sys.argv[3]))
curr=json.load(open(sys.argv[4]))
expected={
 'verified-turnover.json':('home-0977-l3-pure-turnover1to1-train-v1',None,None),
 'verified-uniform.json':('home-1044-l3-pure-hard-replay-large-source-v1','20260729T070032Z-477da64d','477da64da2dea09c8ceb1f1e8e79e2c54d023a5a'),
 'verified-l2low.json':('cpx62-1164-l3-prior-dose-l2-refit-v1',None,None),
 'verified-abc.json':('cpx62-1340-jass-megacorpus-comparative-fit-v1','20260814T123246Z-2ce07222','2ce07222f86c1468a1081fbdc53e9e17a0c5326e'),
 'verified-curriculum.json':('cpx62-1341-jass-megacorpus-arm-d-fit-v1','20260814T191555Z-18c38a33','18c38a33ae78c9c2e8e2df62fca266da28dacead')}
for name,(job,attempt,code) in expected.items():
 row=json.load(open(art/name))
 if row.get('job_id')!=job or row.get('result_state')!='completed' or row.get('exit_code')!=0:
  raise SystemExit(f'{name}: identity/state drift')
 if attempt and row.get('attempt_id')!=attempt: raise SystemExit(f'{name}: attempt drift')
 if code and row.get('code_sha')!=code: raise SystemExit(f'{name}: code drift')
arm=(uniform.get('arms') or {}).get('uniform') or {}
if (uniform.get('verdict')!='L3_PURE_HARD_REPLAY_LARGE_SOURCE_READY'
    or arm.get('records')!=40_000_000 or uniform.get('external_teacher_inputs')!=0):
 raise SystemExit('UNIFORM source policy/size drift')
if abc.get('verdict')!='JASS_MEGACORPUS_ABC_FITS_READY': raise SystemExit('ABC certificate drift')
if curr.get('verdict')!='JASS_MEGACORPUS_ARM_D_FIT_READY': raise SystemExit('Curriculum certificate drift')
PY

gunzip -c "$IN/turnover.jnnw.gz" >"$W/turnover.raw.jnnw"
gunzip -c "$IN/turnover.jsm.gz" >"$W/turnover.raw.jsm"
gunzip -c "$IN/uniform.jnnw.gz" >"$W/uniform.raw.jnnw"
gunzip -c "$IN/uniform.jsm.gz" >"$W/uniform.raw.jsm"
gunzip -c "$IN/l2low.pjtw.gz" >"$W/l2low.pjtw"
gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
[ "$(sha256sum "$W/turnover.raw.jnnw" | awk '{print $1}')" = "$TURNOVER_SHA" ] || die "TURNOVER data drift"
[ "$(sha256sum "$W/turnover.raw.jsm" | awk '{print $1}')" = "$META_SHA" ] || die "TURNOVER meta drift"
[ "$(sha256sum "$W/l2low.pjtw" | awk '{print $1}')" = "$L2LOW_SHA" ] || die "L2LOW drift"
[ "$(sha256sum "$W/curriculum.pjtw" | awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM drift"

stage reproduce-current-2m
python3 tools/selfplay_frontier.py split \
  --data "$W/turnover.raw.jnnw" --meta "$W/turnover.raw.jsm" \
  --out-data "$W/current_2m.jnnw" --out-meta "$W/current_2m.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$ART/current_2m-manifest.json" >"$W/split-current.log" 2>&1
cmp "$ART/current_2m-manifest.json" "$IN/source-current-manifest.json" ||
  die "reproduced current manifest drift"

stage reproduce-mega-full-4m
"$PY" - "$IN/uniform-summary.json" "$ART/verified-uniform.json" \
  "$W/mega-source-selection.json" "$W/uniform.raw.jnnw" "$W/uniform.raw.jsm" \
  "$UNIFORM_ROOT" "$SAMPLE_SEED" <<'PY'
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
  'sampling':{'mode':'game_hash_mod','modulus':10,'residue':0,'seed':int(sys.argv[7])}}]}
open(sys.argv[3],'w').write(json.dumps(doc,indent=2,sort_keys=True)+'\n')
PY
timeout 5400s "$PY" jobs/tools/jass_megacorpus_materialize.py \
  --source-spec "$W/mega-source-selection.json" \
  --out-data "$W/mega_full_4m.jnnw" --out-meta "$W/mega_full_4m.jsm" \
  --origin-source-out "$W/mega_full_4m-origin-source.npy" \
  --origin-index-out "$W/mega_full_4m-origin-index.npy" \
  --source-table-out "$ART/mega_full_4m-source-table.json" \
  --manifest "$ART/mega_full_4m-manifest.json" \
  --holdout-mod "$HOLDOUT_MOD" --split-seed "$SPLIT_SEED" \
  >"$W/materialize-mega.log" 2>&1
cp "$W/mega-source-selection.json" "$ART/mega_full_4m-source-selection.json"
"$PY" - "$ART/mega_full_4m-manifest.json" "$IN/source-mega-manifest.json" <<'PY'
import json,sys
got,source=(json.load(open(p)) for p in sys.argv[1:])
if (got.get('records'),got.get('holdout_records')) != (source.get('records'),source.get('holdout_records')):
 raise SystemExit('reproduced mega manifest drift: sizing')
for key in ('data','meta','origin_source_id','origin_record_index'):
 if got['files'][key]['sha256'] != source['files'][key]['sha256']:
  raise SystemExit(f'reproduced mega manifest drift: {key}')
PY

stage build-exact-fold-tempo-architecture
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] ||
  die "8cf geometry drift"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
  -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass jass_tests >"$W/build.log" 2>&1
"$W/build/jass_tests" >"$W/cpp-tests.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "missing jass binary"

stage dump-production-and-ctx2-features
for arm in mega_full_4m current_2m; do
  timeout 7200s "$J" --dump-eval-features "$W/$arm.jnnw" "$W/$arm.feat" >"$W/eval-features-$arm.log" 2>&1
  timeout 7200s "$J" --dump-conditional-context-v2 "$W/$arm.jnnw" "$W/$arm.ctx2.feat" >"$W/context-features-$arm.log" 2>&1
  read -r K C < <("$PY" - "$W/$arm.feat" "$W/$arm.ctx2.feat" <<'PY'
import struct,sys
def width(path):
 with open(path,'rb') as f:
  assert f.read(4)==b'FEAT'; return struct.unpack('<II',f.read(8))[1]
print(width(sys.argv[1]),width(sys.argv[2]))
PY
  )
  [ "$K" -eq "$EXPECTED_EXTRAS" ] && [ "$C" -eq "$EXPECTED_CONTEXT" ] ||
    die "$arm feature widths drift: production=$K context=$C"
done

arm_counts(){
  local arm="$1" manifest
  manifest="$ART/$arm-manifest.json"
  "$PY" - "$manifest" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); holdout=d['holdout_records']
print(d['records'],d.get('train_records',d['records']-holdout),holdout)
PY
}

stage build-aligned-ctx2-alpha100-targets
for arm in mega_full_4m current_2m; do
  read -r records train holdout < <(arm_counts "$arm")
  /usr/bin/time -f '%e' -o "$W/targets-$arm.seconds" timeout "$TARGET_TIMEOUT" \
    "$PY" jobs/tools/l3_conditional_targets.py \
      --data "$W/$arm.jnnw" --meta "$W/$arm.jsm" --feat "$W/$arm.ctx2.feat" \
      --context-schema ctx2-phase-tactical-30 --group-by opening_id \
      --row-weighting game_equal --require-convergence \
      --train-count "$train" --aligned-out "$W/$arm-target.npy" \
      --shuffled-out "$W/$arm-shuffled.npy" --report "$ART/$arm-conditional-targets.json" \
      --alpha 1.00 --shuffle-within-wdl --shuffle-phase-bins 4 \
      --fold-count 5 --fold-seed 20260811 --shuffle-seed 20260812 \
      --ridge 1e-4 --max-iterations 100 --tolerance 1e-8 --line-search-steps 20 \
      >"$W/targets-$arm.log" 2>&1
  rm -f "$W/$arm-shuffled.npy"
  gzip -n -c "$W/$arm-target.npy" >"$ART/$arm-ctx2-alpha100.npy.gz"
  "$PY" - "$ART/$arm-conditional-targets.json" "$records" "$train" "$holdout" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); m=r['mapping']
if (r.get('schema')!='jass.l3_conditional_targets.v2'
    or r.get('context_schema')!='ctx2-phase-tactical-30'
    or r.get('target',{}).get('alpha')!=1.0): raise SystemExit('CTX2 alpha100 target drift')
if (r.get('records'),r.get('train_records'),r.get('holdout_records')) != tuple(map(int,sys.argv[2:5])):
 raise SystemExit('target sizing drift')
fits=[row['fit'] for row in m['folds']]+[m['final_train_fit']['fit']]
if (m.get('fold_group')!='opening_id' or not m.get('fold_local_rms')
    or not m.get('each_game_total_weight_equal') or not m.get('all_groups_fold_disjoint')
    or m.get('train_holdout_group_overlap')!=0 or not all(row.get('converged') for row in fits)):
 raise SystemExit('strict CTX2 cross-fit contract failed')
PY
done

fit_stage(){
  local arm="$1" prior="$2" records train holdout
  read -r records train holdout < <(arm_counts "$arm")
  stage "fit-$arm-ctx2-alpha100"
  /usr/bin/time -f '%e' -o "$W/fit-$arm.seconds" timeout "$FIT_TIMEOUT" \
    env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" PYTHONUNBUFFERED=1 \
    "$PY" pattern_jass/tools/train_stream.py \
      --data "$W/$arm.jnnw" --feat "$W/$arm.feat" --out "$W/$arm.pjtw" \
      --target external --target-values "$W/$arm-target.npy" \
      --targets-report "$ART/$arm-target-consumption.json" \
      --loss logistic --exact-fold --tempo-stage \
      --prior-mean "$prior" --prior-decay 0 \
      --holdout-count "$holdout" --l2 1e-5 --max-iter "$MAXIT" \
      --chunk "$CHUNK" --lbfgs-maxcor 20 --lbfgs-gtol 1e-4 --prune \
      --optimizer-report "$ART/$arm-optimizer.json" >"$W/fit-$arm.log" 2>&1
  [ -s "$W/$arm.pjtw" ] || die "$arm produced no model"
  "$PY" jobs/tools/verify_optimizer_convergence.py \
    --report "$ART/$arm-optimizer.json" --label "$arm" \
    --expected-max-iterations "$MAXIT" --expected-maxcor 20 --expected-gtol 1e-4 \
    --receipt "$ART/$arm-convergence.json"
  gzip -n -c "$W/$arm.pjtw" >"$ART/$arm.pjtw.gz"
}

fit_stage mega_full_4m "$W/l2low.pjtw"
fit_stage current_2m "$W/mega_full_4m.pjtw"

stage publish-candidate-certificate
"$PY" - "$W" "$ART" "$EXPECTED_CODE_SHA" "$CURRICULUM_SHA" <<'PY'
import hashlib,json,struct,sys
from pathlib import Path
w,art=Path(sys.argv[1]),Path(sys.argv[2]); code=sys.argv[3]; champion_sha=sys.argv[4]
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1<<20),b''): h.update(block)
 return h.hexdigest()
def structure(path):
 path=Path(path); magic,version,scale,n_pat,n_ext=struct.unpack('<5I',path.read_bytes()[:20])
 expected=20+8*(n_pat+n_ext)
 if (magic!=0x57544A50 or (version&0xff)!=3 or scale<=0 or n_pat!=4251528
     or n_ext!=120 or path.stat().st_size!=expected): raise SystemExit(f'{path}: PJTW drift')
 return {'version':version,'scale':scale,'n_patterns':n_pat,'n_extras':n_ext,'size_bytes':path.stat().st_size}
stages={}
for arm in ('mega_full_4m','current_2m'):
 targets=json.load(open(art/f'{arm}-conditional-targets.json'))
 consumed=json.load(open(art/f'{arm}-target-consumption.json'))
 if consumed['source']['sha256']!=targets['outputs']['aligned_sha256']:
  raise SystemExit(f'{arm}: target consumption drift')
 model=w/f'{arm}.pjtw'
 stages[arm]={'model_raw_sha256':sha(model),'model_gz_sha256':sha(art/f'{arm}.pjtw.gz'),
  'structure':structure(model),'optimizer':json.load(open(art/f'{arm}-optimizer.json')),
  'convergence':json.load(open(art/f'{arm}-convergence.json')),
  'target_sha256':targets['outputs']['aligned_sha256'],
  'target_oof_gain_vs_state_blind':targets['mapping']['oof_mse_gain_vs_state_blind'],
  'target_seconds':float((w/f'targets-{arm}.seconds').read_text()),
  'fit_seconds':float((w/f'fit-{arm}.seconds').read_text())}
if stages['current_2m']['model_raw_sha256']==champion_sha:
 raise SystemExit('candidate unexpectedly equals Curriculum')
payload={'schema':'jass.l3_context2_curriculum_full_relabel_fit.v1',
 'verdict':'JASS_CONTEXT2_CURRICULUM_FULL_RELABEL_MODEL_READY','code_sha':code,
 'baseline':{'label':'CURRICULUM','model_raw_sha256':champion_sha,
  'source_job':'cpx62-1341-jass-megacorpus-arm-d-fit-v1','baseline_reused_without_refit':True},
 'candidate':{'label':'CURRICULUM_CTX2_ALPHA100','model_raw_sha256':stages['current_2m']['model_raw_sha256'],
  'artifact':'current_2m.pjtw.gz'},
 'recipe':{'sequence':['MEGA_FULL_4M','CURRENT_2M'],'target':'CTX2_PHASE_TACTICAL_ALIGNED',
  'alpha':1.0,'architecture':'8cf_exact_fold_tempo_120_extras','first_prior_mean':'L2LOW',
  'second_prior_mean':'refitted_MEGA_FULL_4M_CTX2_ALPHA100','prior_decay':0,'l2':1e-5,
  'gtol':1e-4,'max_iterations':2000,'lbfgs_maxcor':20},
 'stages':stages,'primary_contrast':'candidate_vs_CURRICULUM_native_0.1s_fresh_pool',
 'diagnostic_view':'Q00_d9','strength_games_played':0,'frozen_cohorts_read':0,
 'new_training_games_generated':False,'promotion_authorized':False,'automatic_next_job':None}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/'VERDICT__JASS_CONTEXT2_CURRICULUM_FULL_RELABEL_MODEL_READY').touch()
(art/'PROMOTION_AUTHORIZED__FALSE').touch(); (art/'AUTOMATIC_NEXT_JOB__NULL').touch()
print(json.dumps(payload,sort_keys=True))
PY
say "JASS_CONTEXT2_CURRICULUM_FULL_RELABEL_MODEL_READY alpha=1.00 stages=mega4m,current2m games=0 promotion=false"
