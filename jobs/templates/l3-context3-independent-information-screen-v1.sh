#!/usr/bin/env bash
# Read-only CTX3 nonlinear independent-information screen on immutable 1409.
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
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; cp "$STAGE" "$ART/STAGE.txt"; }

CORPUS_ROOT="r2:jass-data/runs/cpx62-1409-l3-context2-intervention-corpus-v1/20260818T184956Z-3465ec72"
MAPPER_ROOT="r2:jass-data/runs/cpx62-1411-l3-context2-intervention-mapper-screen-v1/20260818T200558Z-9ec9195a"
FAILURE_ROOT="r2:jass-data/runs/cpx62-1415a-l3-context2-shared-information-readout-v1/20260819T051956Z-136bafca"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
SPLIT_SEED=577215; HOLDOUT_MOD=10; EXPECTED_RECORDS=2000000
FOLD_SEED=20260811; SHUFFLE_SEED=2026081903; BOOTSTRAP_SEED=2026081904
BOOTSTRAP_REPLICATES=5000; RIDGE=0.0001; CHUNK_SIZE=50000
MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        [ -f "$ART/context3-independent-information-screen.json" ] && printf 'screen_ready=1\n'
      } >"$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120
    done ) & MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -maxdepth 1 -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  case "$W" in "$JASS_RESULT_DIR"/*) ;; *) exit 98 ;; esac
  case "$IN" in "$JASS_RESULT_DIR"/*) ;; *) exit 99 ;; esac
  rm -rf -- "$IN" "$W" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-([0-9]+[a-z]?)-l3-context3-independent-information-screen-v1$ ]] ||
  die "invalid job nomenclature"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "explicit execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "persistent numeric runtime absent; do not reinstall"
PY="$VENV/bin/python"
"$PY" -c 'import numpy,scipy; assert numpy.__version__ and scipy.__version__' ||
  die "persistent numeric runtime invalid"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 10240 ] || die "less than 10 GiB free ($DFA MiB)"
say "host=cpx62 nproc=16 mode=ctx3_independent_information eta_minutes=15-35"
say "source_records=2000000 candidates=3 bootstrap=5000 selfplay=0 patterneval_fits=0 force=0"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_context3_independent_information_screen.py
"$PY" -m unittest jobs.tests.test_l3_context3_independent_information_screen \
  jobs.tests.test_l3_context3_independent_information_template >"$W/tests.log" 2>&1

stage fetch-authenticated-sources
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CORPUS_ROOT" \
  --file artefacts/context2-intervention-2m.jnnw.gz=original.jnnw.gz \
  --file artefacts/context2-intervention-2m.jsm.gz=original.jsm.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=corpus-summary.json \
  --out-dir "$IN" --report "$ART/verified-corpus.json" --expected-state completed >"$W/fetch-corpus.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$MAPPER_ROOT" \
  --file artefacts/conditional-targets.json=conditional-targets.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=mapper-summary.json \
  --out-dir "$IN" --report "$ART/verified-mapper.json" --expected-state completed >"$W/fetch-mapper.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$FAILURE_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=failure-summary.json \
  --out-dir "$IN" --report "$ART/verified-failure.json" --expected-state completed >"$W/fetch-failure.log" 2>&1

"$PY" - "$ART" "$IN" <<'PY'
import json,sys
from pathlib import Path
art,src=map(Path,sys.argv[1:3])
expected={
 'verified-corpus.json':('cpx62-1409-l3-context2-intervention-corpus-v1','20260818T184956Z-3465ec72','3465ec720eb37c5c9368f2df048831f7381c5839'),
 'verified-mapper.json':('cpx62-1411-l3-context2-intervention-mapper-screen-v1','20260818T200558Z-9ec9195a','9ec9195aeb517798d69609e404b59346405fdd54'),
 'verified-failure.json':('cpx62-1415a-l3-context2-shared-information-readout-v1','20260819T051956Z-136bafca','136bafcabedcac6c5bf40c01f5339bb67f4acac0')}
for name,identity in expected.items():
 row=json.load(open(art/name)); got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha'))
 if got!=identity or row.get('result_state')!='completed' or row.get('exit_code')!=0:
  raise SystemExit(f'{name}: identity/state drift {got}')
if json.load(open(src/'corpus-summary.json')).get('verdict')!='JASS_CONTEXT2_INTERVENTION_CORPUS_READY':
 raise SystemExit('corpus verdict drift')
if json.load(open(src/'mapper-summary.json')).get('verdict')!='JASS_CONTEXT2_INTERVENTION_MAPPER_SCREEN_FAILED':
 raise SystemExit('mapper verdict drift')
if json.load(open(src/'failure-summary.json')).get('verdict')!='JASS_CONTEXT2_SHARED_INFORMATION_POOL_FAILURE_AUDITED':
 raise SystemExit('1415a terminal verdict drift')
PY

stage reproduce-exact-split
gunzip -c "$IN/original.jnnw.gz" >"$W/original.jnnw"
gunzip -c "$IN/original.jsm.gz" >"$W/original.jsm"
python3 tools/selfplay_frontier.py split --data "$W/original.jnnw" --meta "$W/original.jsm" \
  --out-data "$W/intervention.jnnw" --out-meta "$W/intervention.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" --manifest "$ART/split.json" >"$W/split.log" 2>&1
read -r RECORDS TRAIN HOLDOUT < <("$PY" - "$ART/split.json" <<'PY'
import json,sys
s=json.load(open(sys.argv[1])); print(s['records'],s['train_records'],s['holdout_records'])
PY
)
[ "$RECORDS" -eq "$EXPECTED_RECORDS" ] && [ "$TRAIN" -gt 0 ] && [ "$HOLDOUT" -gt 0 ] ||
  die "split sizing drift"
"$PY" - "$IN/conditional-targets.json" "$W/intervention.jnnw" "$W/intervention.jsm" "$TRAIN" <<'PY'
import hashlib,json,sys
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1<<20),b''): h.update(block)
 return h.hexdigest()
r=json.load(open(sys.argv[1])); src=r['source']
if r.get('train_records')!=int(sys.argv[4]): raise SystemExit('train-count drift')
if sha(sys.argv[2])!=src.get('data_sha256') or sha(sys.argv[3])!=src.get('meta_sha256'):
 raise SystemExit('split hashes drift against certified mapper')
PY

stage build-production-ctx2-dumper
for file in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/movegen.cpp src/movegen.hpp; do
  git show "$EXPECTED_CODE_SHA:$file" | cmp - "$file" || die "architecture source drift: $file"
done
grep -q 'g_emasks' src/scan_eval.cpp || die "scan_eval lacks NPS masks"
grep -q 'has_any_capture' src/search.cpp || die "search lacks capture fast path"
grep -q 'has_any_capture' src/movegen.cpp || die "movegen lacks capture fast path"
timeout 1800s cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
timeout 3600s cmake --build "$W/build" -j16 --target jass jass_tests >"$W/build.log" 2>&1
"$W/build/jass_tests" >"$W/cpp-tests.log" 2>&1
timeout 3600s "$W/build/jass" --dump-conditional-context-v2 \
  "$W/intervention.jnnw" "$W/intervention.ctx2.feat" >"$W/dump.log" 2>&1
"$PY" - "$IN/conditional-targets.json" "$W/intervention.ctx2.feat" <<'PY'
import hashlib,json,sys
h=hashlib.sha256()
with open(sys.argv[2],'rb') as f:
 for block in iter(lambda:f.read(1<<20),b''): h.update(block)
if h.hexdigest()!=json.load(open(sys.argv[1]))['source']['feat_sha256']:
 raise SystemExit('production CTX2 feature dump hash drift')
PY

stage screen-independent-information
timeout 4500s "$PY" jobs/tools/l3_context3_independent_information_screen.py \
  --data "$W/intervention.jnnw" --meta "$W/intervention.jsm" \
  --features "$W/intervention.ctx2.feat" --train-count "$TRAIN" \
  --fold-seed "$FOLD_SEED" --shuffle-seed "$SHUFFLE_SEED" \
  --bootstrap-seed "$BOOTSTRAP_SEED" --bootstrap-replicates "$BOOTSTRAP_REPLICATES" \
  --ridge "$RIDGE" --chunk-size "$CHUNK_SIZE" \
  --report "$ART/context3-independent-information-screen.json" >"$W/screen.log" 2>&1

stage reporting-roundtrip
"$PY" - "$ART/context3-independent-information-screen.json" "$RECORDS" "$TRAIN" "$HOLDOUT" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); records,train,holdout=map(int,sys.argv[2:])
if r.get('schema')!='jass.l3_context3_independent_information_screen.v1': raise SystemExit('report schema drift')
if r['source']['records']!=records or r['source']['train_records']!=train or r['source']['holdout_records']!=holdout:
 raise SystemExit('report sizing drift')
if r['selected_candidate'] not in ('odd_curvature','tactical_magnitude_gates','combined'):
 raise SystemExit('candidate drift')
if r['protocol']['bootstrap_replicates']!=5000 or len(r['guards'])!=8:
 raise SystemExit('protocol/report roundtrip drift')
PY

stage publish-screen-certificate
"$PY" - "$ART" "$EXPECTED_CODE_SHA" <<'PY' | tee -a "$RES"
import json,re,sys
from pathlib import Path
art=Path(sys.argv[1]); screen=json.load(open(art/'context3-independent-information-screen.json'))
verdict=screen['verdict']; passed=bool(screen['screen_passed']); selected=screen['selected_candidate']
payload={'schema':'jass.l3_context3_independent_information_job.v1','verdict':verdict,
 'code_sha':sys.argv[2],'screen_passed':passed,'selected_candidate':selected,
 'discovery':screen['discovery'][selected],
 'holdout_improvement_vs_ctx2':screen['holdout_improvement_vs_ctx2'],
 'aligned_vs_shuffled_oof':screen['aligned_vs_shuffled_oof'],
 'aligned_vs_shuffled_holdout':screen['aligned_vs_shuffled_holdout'],
 'guards':screen['guards'],'linear_screen_fits_run':28,'conditional_tanh_mapper_fits_run':0,
 'selfplay_generated':False,'patterneval_fits_run':0,'force_games_played':0,
 'frozen_read':False,'promotion_authorized':False,
 'next_recommended_job':('cpx62-1417-l3-context3-exact-mapper-causal-screen-v1' if passed else None),
 'automatic_next_job':None}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/f'VERDICT__{verdict}').touch()
for key,value in screen['guards'].items():
 safe=re.sub('[^A-Za-z0-9]+','_',key).strip('_').upper()
 (art/f'GUARD__{safe}__{str(bool(value)).upper()}').touch()
for name in ('SELFPLAY_GENERATED__FALSE','CONDITIONAL_TANH_MAPPER_FITS_RUN__0',
 'PATTERNEVAL_FITS_RUN__0','FORCE_GAMES_PLAYED__0','FROZEN_READ__FALSE',
 'PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_NEXT_JOB__NULL'):
 (art/name).touch()
print(json.dumps(payload,sort_keys=True))
PY
say "$("$PY" -c 'import json,sys; r=json.load(open(sys.argv[1])); print(r["verdict"],r["selected_candidate"])' "$ART/context3-independent-information-screen.json") selfplay=false patterneval_fits=0 force=0"
