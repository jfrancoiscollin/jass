#!/usr/bin/env bash
# Full-Jass CTX2 phase+tactical causal models on immutable TURNOVER 2M.
#
# A = certified historical CTX1_A30 model, reused without refit.
# B = CTX2_PHASE_TACTICAL_A30 aligned.
# C = the same CTX2 prediction marginal shuffled within
#     cohort x opening-fold x terminal-WDL x tempo-phase-bin.
#
# This job builds labels and fits B/C only. It generates no games, reads no
# frozen cohort, performs no force gate and cannot promote a model.
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
CTX1_ROOT="r2:jass-data/runs/cpx62-1340-jass-megacorpus-comparative-fit-v1/20260814T123246Z-2ce07222"
TURNOVER_SHA="9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
META_SHA="acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
L2LOW_SHA="ec47e4b37fc7e95dcb390c0a5eddf207e98c0818c1708636d2df9e85b1d149b4"
EXPECTED_RECORDS=2000000; EXPECTED_HOLDOUT=199204; EXPECTED_EXTRAS=120
EXPECTED_CONTEXT=30; SPLIT_SEED=577215; HOLDOUT_MOD=10
MAXIT=2000; CHUNK=20000; TARGET_TIMEOUT=21600; FIT_TIMEOUT=28800
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
        for arm in aligned shuffled; do
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
[[ "$JASS_JOB_ID" =~ ^(home|cpx62)-([0-9]+)-l3-context2-phase-tactical-fit-v1$ ]] ||
  die "invalid job nomenclature"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "explicit execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(nproc)" -eq 16 ] || die "16-CPU box contract mismatch"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 20480 ] || die "less than 20 GiB free ($DFA MiB)"
say "host=$(hostname) nproc=$(nproc) free_mb=$DFA mode=ctx2_phase_tactical_fit"
monitor

stage fetch-authenticated-immutable-sources
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_ROOT" \
  --file artefacts/turnover1to1.jnnw.gz=turnover.jnnw.gz \
  --file artefacts/turnover1to1.jsm.gz=turnover.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-turnover.json" >"$W/fetch-turnover.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$L2LOW_ROOT" \
  --file artefacts/control.pjtw.gz=l2low.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-l2low.json" >"$W/fetch-l2low.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CTX1_ROOT" \
  --file artefacts/current_2m.pjtw.gz=ctx1.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=ctx1-summary.json \
  --out-dir "$IN" --report "$ART/verified-ctx1.json" >"$W/fetch-ctx1.log" 2>&1

python3 - "$ART" <<'PY'
import json,sys
from pathlib import Path
art=Path(sys.argv[1])
expected={
 'verified-turnover.json':('home-0977-l3-pure-turnover1to1-train-v1',None,None),
 'verified-l2low.json':('cpx62-1164-l3-prior-dose-l2-refit-v1',None,None),
 'verified-ctx1.json':('cpx62-1340-jass-megacorpus-comparative-fit-v1',
   '20260814T123246Z-2ce07222','2ce07222f86c1468a1081fbdc53e9e17a0c5326e')}
for name,(job,attempt,code) in expected.items():
 row=json.load(open(art/name))
 if row.get('job_id')!=job or row.get('result_state')!='completed' or row.get('exit_code')!=0:
  raise SystemExit(f'{name}: source identity/state drift')
 if attempt and row.get('attempt_id')!=attempt: raise SystemExit(f'{name}: attempt drift')
 if code and row.get('code_sha')!=code: raise SystemExit(f'{name}: code drift')
PY

gunzip -c "$IN/turnover.jnnw.gz" >"$W/turnover.raw.jnnw"
gunzip -c "$IN/turnover.jsm.gz" >"$W/turnover.raw.jsm"
gunzip -c "$IN/l2low.pjtw.gz" >"$W/l2low.pjtw"
gunzip -c "$IN/ctx1.pjtw.gz" >"$W/ctx1.pjtw"
[ "$(sha256sum "$W/turnover.raw.jnnw" | awk '{print $1}')" = "$TURNOVER_SHA" ] || die "TURNOVER data drift"
[ "$(sha256sum "$W/turnover.raw.jsm" | awk '{print $1}')" = "$META_SHA" ] || die "TURNOVER meta drift"
[ "$(sha256sum "$W/l2low.pjtw" | awk '{print $1}')" = "$L2LOW_SHA" ] || die "L2LOW drift"

stage persistent-numeric-runtime
if [ ! -f "$VENV_READY" ]; then
  mkdir -p "$(dirname "$VENV")"
  python3 -m venv --clear "$VENV"
  "$VENV/bin/python" -m pip install --disable-pip-version-check --only-binary=:all: \
    numpy scipy >"$W/pip-bootstrap-once.log" 2>&1
  "$VENV/bin/python" - "$VENV_READY" "$JASS_JOB_ID" <<'PY'
import json,numpy,scipy,sys
open(sys.argv[1],'w').write(json.dumps({'schema':'jass.numeric_cache.v1',
 'created_by':sys.argv[2],'numpy':numpy.__version__,'scipy':scipy.__version__},
 indent=2,sort_keys=True)+'\n')
PY
fi
PY="$VENV/bin/python"
"$PY" - "$ART/python-runtime.json" "$VENV" <<'PY'
import json,numpy,scipy,sys
json.dump({'schema':'jass.python_runtime.v1','venv':sys.argv[2],
 'numpy':numpy.__version__,'scipy':scipy.__version__,
 'pytorch_installed_or_required':False,'persistent_cache':True},
 open(sys.argv[1],'w'),indent=2,sort_keys=True)
open(sys.argv[1],'a').write('\n')
PY

stage repository-contracts-and-opening-split
python3 -m py_compile jobs/tools/l3_conditional_targets.py jobs/tools/verify_optimizer_convergence.py
python3 -m unittest jobs.tests.test_l3_context2_phase_tactical_protocol >"$W/protocol-tests.log" 2>&1
python3 tools/selfplay_frontier.py split \
  --data "$W/turnover.raw.jnnw" --meta "$W/turnover.raw.jsm" \
  --out-data "$W/current.jnnw" --out-meta "$W/current.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$ART/split.json" >"$W/split.log" 2>&1
read -r RECORDS TRAIN HOLDOUT < <("$PY" - "$ART/split.json" <<'PY'
import json,sys
s=json.load(open(sys.argv[1])); print(s['records'],s['train_records'],s['holdout_records'])
PY
)
[ "$RECORDS" -eq "$EXPECTED_RECORDS" ] && [ "$HOLDOUT" -eq "$EXPECTED_HOLDOUT" ] ||
  die "split sizing drift"

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
"$J" --dump-eval-features "$W/current.jnnw" "$W/current.feat" >"$W/eval-features.log" 2>&1
"$J" --dump-conditional-context-v2 "$W/current.jnnw" "$W/current.ctx2.feat" >"$W/context-features.log" 2>&1
read -r K C < <(python3 - "$W/current.feat" "$W/current.ctx2.feat" <<'PY'
import struct,sys
def width(p):
 with open(p,'rb') as f:
  assert f.read(4)==b'FEAT'; return struct.unpack('<II',f.read(8))[1]
print(width(sys.argv[1]),width(sys.argv[2]))
PY
)
[ "$K" -eq "$EXPECTED_EXTRAS" ] && [ "$C" -eq "$EXPECTED_CONTEXT" ] ||
  die "feature widths drift: production=$K context=$C"

stage build-ctx2-aligned-and-causal-shuffled-targets
/usr/bin/time -f '%e' -o "$W/targets.seconds" timeout "$TARGET_TIMEOUT" \
  "$PY" jobs/tools/l3_conditional_targets.py \
    --data "$W/current.jnnw" --meta "$W/current.jsm" --feat "$W/current.ctx2.feat" \
    --context-schema ctx2-phase-tactical-30 --group-by opening_id \
    --row-weighting game_equal --require-convergence \
    --train-count "$TRAIN" --aligned-out "$W/aligned.npy" --shuffled-out "$W/shuffled.npy" \
    --report "$ART/conditional-targets.json" --alpha 0.30 \
    --shuffle-within-wdl --shuffle-phase-bins 4 \
    --fold-count 5 --fold-seed 20260811 --shuffle-seed 20260812 \
    --ridge 1e-4 --max-iterations 100 --tolerance 1e-8 --line-search-steps 20 \
    >"$W/targets.log" 2>&1

"$PY" - "$ART/conditional-targets.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); m=r['mapping']; s=r['shuffle_control']
if r.get('schema')!='jass.l3_conditional_targets.v2' or r.get('context_schema')!='ctx2-phase-tactical-30':
 raise SystemExit('CTX2 target schema drift')
if (m.get('fold_group')!='opening_id' or not m.get('fold_local_rms')
    or not m.get('each_game_total_weight_equal') or not m.get('all_groups_fold_disjoint')
    or m.get('train_holdout_group_overlap')!=0):
 raise SystemExit('strict cross-fit contract failed')
fits=[row['fit'] for row in m['folds']]+[m['final_train_fit']['fit']]
if not all(row.get('converged') for row in fits): raise SystemExit('mapper convergence failed')
if (s.get('fixed_point_count')!=0
    or s.get('stratification')!='terminal_wdl_black_x_tempo_phase_4_bins'
    or not s.get('all_final_target_marginals_preserved')):
 raise SystemExit('causal shuffle contract failed')
if m['matrix_diagnostics']['effective_rank']<=0: raise SystemExit('empty CTX2 matrix rank')
PY
gzip -n -c "$W/aligned.npy" >"$ART/ctx2-aligned-target.npy.gz"
gzip -n -c "$W/shuffled.npy" >"$ART/ctx2-shuffled-target.npy.gz"
gzip -n -c "$W/current.ctx2.feat" >"$ART/ctx2-context.feat.gz"

fit_arm(){
  local arm="$1" target="$2"
  stage "fit-ctx2-$arm"
  /usr/bin/time -f '%e' -o "$W/fit-$arm.seconds" timeout "$FIT_TIMEOUT" \
    env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" PYTHONUNBUFFERED=1 \
    "$PY" pattern_jass/tools/train_stream.py \
      --data "$W/current.jnnw" --feat "$W/current.feat" --out "$W/$arm.pjtw" \
      --target external --target-values "$target" \
      --targets-report "$ART/$arm-target-consumption.json" \
      --loss logistic --exact-fold --tempo-stage \
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

fit_arm aligned "$W/aligned.npy"
fit_arm shuffled "$W/shuffled.npy"

stage publish-abc-model-certificate
"$PY" - "$W" "$ART" "$IN/ctx1-summary.json" "$EXPECTED_CODE_SHA" <<'PY'
import hashlib,json,struct,sys
from pathlib import Path
w,art=Path(sys.argv[1]),Path(sys.argv[2]); source=json.load(open(sys.argv[3])); code=sys.argv[4]
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for block in iter(lambda:f.read(1<<20),b''): h.update(block)
 return h.hexdigest()
def structure(p):
 magic,version,scale,n_pat,n_ext=struct.unpack('<5I',Path(p).read_bytes()[:20])
 expected=20+8*(n_pat+n_ext)
 if (magic!=0x57544A50 or (version&0xff)!=3 or scale<=0 or n_pat!=4251528
     or n_ext!=120 or Path(p).stat().st_size!=expected):
  raise SystemExit(f'{p}: PJTW structure drift')
 return {'version':version,'scale':scale,'n_patterns':n_pat,'n_extras':n_ext,
  'size_bytes':Path(p).stat().st_size}
source_arm=source.get('arms',{}).get('CURRENT_2M',{})
if source.get('verdict')!='JASS_MEGACORPUS_ABC_FITS_READY': raise SystemExit('CTX1 certificate drift')
models={}
for key,name in (('A','ctx1'),('B','aligned'),('C','shuffled')):
 p=w/f'{name}.pjtw'; raw=sha(p)
 models[key]={'model_raw_sha256':raw,'structure':structure(p)}
 if key!='A':
  models[key]['model_gz_sha256']=sha(art/f'{name}.pjtw.gz')
  models[key]['optimizer']=json.load(open(art/f'{name}-optimizer.json'))
  models[key]['convergence']=json.load(open(art/f'{name}-convergence.json'))
  models[key]['fit_seconds']=float((w/f'fit-{name}.seconds').read_text())
if models['A']['model_raw_sha256']!=source_arm.get('model_raw_sha256'):
 raise SystemExit('reused CTX1 model hash drift')
if len({row['model_raw_sha256'] for row in models.values()})!=3:
 raise SystemExit('A/B/C models are not distinct')
targets=json.load(open(art/'conditional-targets.json'))
payload={'schema':'jass.l3_context2_phase_tactical_models.v1',
 'verdict':'JASS_CONTEXT2_PHASE_TACTICAL_MODELS_READY','code_sha':code,
 'corpus':'TURNOVER_CURRENT_2M','parent':'L2LOW','records':2_000_000,
 'split':{'seed':577215,'holdout_mod':10,'holdout_records':199_204},
 'architecture':'8cf_exact_fold_tempo_120_extras',
 'recipe':{'alpha':0.30,'prior_mean':'L2LOW','prior_decay':0,'l2':1e-5,
  'gtol':1e-4,'max_iterations':2000},
 'arms':{
  'A':{**models['A'],'target':'CTX1_LEGACY_A30','reused_from':'cpx62-1340'},
  'B':{**models['B'],'target':'CTX2_PHASE_TACTICAL_A30_ALIGNED'},
  'C':{**models['C'],'target':'CTX2_PHASE_TACTICAL_A30_SHUFFLED_WDL_PHASE_MATCHED'}},
 'target_certificate':{'context_schema':targets['context_schema'],
  'aligned_sha256':targets['outputs']['aligned_sha256'],
  'shuffled_sha256':targets['outputs']['shuffled_sha256'],
  'fold_group':targets['mapping']['fold_group'],
  'row_weighting':targets['mapping']['row_weighting'],
  'fold_local_rms':targets['mapping']['fold_local_rms'],
  'shuffle_stratification':targets['shuffle_control']['stratification'],
  'fixed_points':targets['shuffle_control']['fixed_point_count'],
  'matrix_diagnostics':targets['mapping']['matrix_diagnostics']},
 'primary_contrast':'B_vs_C_on_native_two_fresh_disjoint_opening_pools',
 'secondary_contrast':'B_vs_A_only_if_B_vs_C_is_established_positive',
 'diagnostic_view':'Q00_d9','new_selfplay_generated':False,'frozen_cohorts_read':0,
 'strength_games_played':0,'promotion_authorized':False,'automatic_next_job':None}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/'VERDICT__JASS_CONTEXT2_PHASE_TACTICAL_MODELS_READY').touch()
(art/'PROMOTION_AUTHORIZED__FALSE').touch(); (art/'AUTOMATIC_NEXT_JOB__NULL').touch()
print(json.dumps(payload,sort_keys=True))
PY
say "JASS_CONTEXT2_PHASE_TACTICAL_MODELS_READY selfplay=0 frozen=0 strength_games=0 promotion=false"
