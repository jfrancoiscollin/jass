#!/usr/bin/env bash
# CTX2 activation census on exactly 100,000 complete paired self-play games.
# Read-only diagnostic: no fit, force game, frozen cohort or promotion.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

SOURCE_ROOT="r2:jass-data/runs/home-1044-l3-pure-hard-replay-large-source-v1/20260729T070032Z-477da64d"
SOURCE_JOB="home-1044-l3-pure-hard-replay-large-source-v1"
SOURCE_ATTEMPT="20260729T070032Z-477da64d"
SOURCE_CODE_SHA="477da64da2dea09c8ceb1f1e8e79e2c54d023a5a"
SOURCE_RECORDS=40000000
SAMPLE_GAMES=100000; SAMPLE_OPENINGS=50000; SAMPLE_SEED=2026081701
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
        [ -f "$ART/sample-manifest.json" ] && printf 'sample_ready=1\n'
        [ -f "$ART/context2-activation-census.json" ] && printf 'census_ready=1\n'
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
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^home-([0-9]+)-l3-context2-activation-census100k-v1$ ]] ||
  die "invalid job nomenclature"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "explicit execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" != cpx62 ] && [ "$(nproc)" -eq 16 ] || die "Home 16-CPU contract mismatch"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 10240 ] || die "less than 10 GiB free ($DFA MiB)"
[ -f "$VENV_READY" ] || die "persistent numeric runtime absent; do not reinstall"
PY="$VENV/bin/python"
"$PY" -c 'import numpy; assert numpy.__version__' || die "persistent NumPy runtime unusable"
say "host=$(hostname) nproc=$(nproc) free_mb=$DFA mode=ctx2_activation_census100k"
monitor

stage repository-contracts
python3 -m py_compile jobs/tools/l3_context2_activation_census.py
"$PY" -m unittest jobs.tests.test_l3_context2_activation_census >"$W/tests.log" 2>&1

stage fetch-authenticated-uniform40m-source
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_ROOT" \
  --file artefacts/uniform.jnnw.gz=uniform.jnnw.gz \
  --file artefacts/uniform.jsm.gz=uniform.jsm.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=source-summary.json \
  --out-dir "$IN" --report "$ART/verified-source.json" >"$W/fetch.log" 2>&1

"$PY" - "$ART/verified-source.json" "$IN/source-summary.json" \
  "$SOURCE_JOB" "$SOURCE_ATTEMPT" "$SOURCE_CODE_SHA" "$SOURCE_RECORDS" <<'PY'
import json,sys
verified=json.load(open(sys.argv[1])); summary=json.load(open(sys.argv[2])); expected=int(sys.argv[6])
if (verified.get('job_id'),verified.get('attempt_id'),verified.get('code_sha')) != tuple(sys.argv[3:6]):
 raise SystemExit('source identity drift')
if verified.get('result_state')!='completed' or verified.get('exit_code')!=0:
 raise SystemExit('source state drift')
arm=(summary.get('arms') or {}).get('uniform') or {}; policy=summary.get('policy') or {}
if summary.get('verdict')!='L3_PURE_HARD_REPLAY_LARGE_SOURCE_READY':
 raise SystemExit('source certificate verdict drift')
if arm.get('records')!=expected or summary.get('external_teacher_inputs')!=0:
 raise SystemExit('source record count/teacher contract drift')
required={'name':'uniform','depth':8,'label_depth':4,'random_open_plies':8,
 'explore_eps':8,'explore_decay_plies':60,'split_selfplay_rngs':True,
 'pair_openings':True,'drop_plycap':True,'post_drawn_root_fix':True}
if any(policy.get(k)!=v for k,v in required.items()):
 raise SystemExit(f'source self-play policy drift: {policy}')
for key in ('data_raw_sha256','meta_raw_sha256'):
 if not isinstance(arm.get(key),str) or len(arm[key])!=64: raise SystemExit(f'missing {key}')
PY

gunzip -c "$IN/uniform.jnnw.gz" >"$W/uniform.raw.jnnw"
gunzip -c "$IN/uniform.jsm.gz" >"$W/uniform.raw.jsm"
read -r DATA_SHA META_SHA < <("$PY" - "$IN/source-summary.json" <<'PY'
import json,sys
a=json.load(open(sys.argv[1]))['arms']['uniform']; print(a['data_raw_sha256'],a['meta_raw_sha256'])
PY
)
[ "$(sha256sum "$W/uniform.raw.jnnw" | awk '{print $1}')" = "$DATA_SHA" ] || die "source data hash drift"
[ "$(sha256sum "$W/uniform.raw.jsm" | awk '{print $1}')" = "$META_SHA" ] || die "source meta hash drift"

stage deterministic-complete-paired-game-sample
timeout 7200s "$PY" jobs/tools/l3_context2_activation_census.py sample \
  --data "$W/uniform.raw.jnnw" --meta "$W/uniform.raw.jsm" \
  --out-data "$W/sample100k.jnnw" --out-meta "$W/sample100k.jsm" \
  --games "$SAMPLE_GAMES" --games-per-opening 2 --seed "$SAMPLE_SEED" \
  --manifest "$ART/sample-manifest.json" >"$W/sample.log" 2>&1
"$PY" - "$ART/sample-manifest.json" "$SOURCE_RECORDS" "$SAMPLE_GAMES" "$SAMPLE_OPENINGS" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); source=int(sys.argv[2]); games=int(sys.argv[3]); openings=int(sys.argv[4])
if r['source']['records']!=source or r['sample']['games']!=games or r['sample']['openings']!=openings:
 raise SystemExit('sample cardinality drift')
if not r['sample']['complete_games'] or not r['sample']['complete_opening_groups']:
 raise SystemExit('sample broke complete trajectories')
PY
rm -f "$W/uniform.raw.jnnw" "$W/uniform.raw.jsm"

stage build-production-ctx2-dumper
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
  -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass jass_tests >"$W/build.log" 2>&1
"$W/build/jass_tests" >"$W/cpp-tests.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "missing jass binary"

stage dump-ctx2-on-training-positions
timeout 7200s "$J" --dump-conditional-context-v2 \
  "$W/sample100k.jnnw" "$W/sample100k.ctx2.feat" >"$W/dump.log" 2>&1

stage analyse-activation-by-position-game-phase
timeout 7200s "$PY" jobs/tools/l3_context2_activation_census.py analyze \
  --data "$W/sample100k.jnnw" --meta "$W/sample100k.jsm" \
  --feat "$W/sample100k.ctx2.feat" \
  --expected-games "$SAMPLE_GAMES" --expected-openings "$SAMPLE_OPENINGS" \
  --material-threshold 1e-6 --rare-threshold 1e-3 --rank-rows 250000 \
  --report "$ART/context2-activation-census.json" \
  --csv "$ART/context2-activation-census.csv" \
  --markdown "$ART/context2-activation-census.md" >"$W/analyse.log" 2>&1

stage publish-audited-census
gzip -n -c "$W/sample100k.jnnw" >"$ART/sample100k.jnnw.gz"
gzip -n -c "$W/sample100k.jsm" >"$ART/sample100k.jsm.gz"
gzip -n -c "$W/sample100k.ctx2.feat" >"$ART/sample100k.ctx2.feat.gz"
"$PY" - "$ART" "$EXPECTED_CODE_SHA" "$SOURCE_JOB" "$SOURCE_ATTEMPT" <<'PY'
import hashlib,json,sys
from pathlib import Path
art=Path(sys.argv[1]); census=json.load(open(art/'context2-activation-census.json'))
sample=json.load(open(art/'sample-manifest.json'))
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1<<20),b''): h.update(block)
 return h.hexdigest()
population=census['population']
if (population.get('positions'),population.get('games'),population.get('openings'),
 population.get('complete_game_sampling')) != (sample['sample']['records'],100000,50000,True):
 raise SystemExit('population/sample mismatch')
if census['phase']['recomposition_max_absolute_error']>1e-5:
 raise SystemExit('CTX2 phase/base recomposition mismatch')
payload={'schema':'jass.l3_context2_activation_census_job.v1',
 'verdict':'JASS_CONTEXT2_ACTIVATION_CENSUS100K_READY','code_sha':sys.argv[2],
 'source':{'job_id':sys.argv[3],'attempt_id':sys.argv[4]},
 'sample':sample['sample'],'census_verdict':census['verdict'],
 'all_30_channels_materially_active':census['diagnostics']['all_30_channels_materially_active'],
 'all_15_base_signals_materially_active':census['diagnostics']['all_15_base_signals_materially_active'],
 'rare_raw_channels':census['diagnostics']['rare_raw_channels'],
 'rare_base_signals':census['diagnostics']['rare_base_signals'],
 'artifacts':{name:sha(art/name) for name in ('sample100k.jnnw.gz','sample100k.jsm.gz',
  'sample100k.ctx2.feat.gz','context2-activation-census.json','context2-activation-census.csv')},
 'selfplay_generated':False,'fits_run':0,'force_games_played':0,'frozen_read':False,
 'promotion_authorized':False,'automatic_next_job':None}
open(art/'JASS_CONTROL_SUMMARY.json','w').write(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/'VERDICT__JASS_CONTEXT2_ACTIVATION_CENSUS100K_READY').touch()
(art/'PROMOTION_AUTHORIZED__FALSE').write_text('false\n')
(art/'AUTOMATIC_NEXT_JOB__NULL').write_text('null\n')
PY
say "JASS_CONTEXT2_ACTIVATION_CENSUS100K_READY games=$SAMPLE_GAMES openings=$SAMPLE_OPENINGS generated=false promotion=false"
