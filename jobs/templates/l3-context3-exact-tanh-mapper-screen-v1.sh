#!/usr/bin/env bash
# Exact CTX3 tanh mapper causal screen on the immutable 1409 corpus.
# Fits CTX2, aligned CTX3 and augmentation-shuffled CTX3 only. No PatternEval.
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
SCREEN_ROOT="r2:jass-data/runs/cpx62-1416b-l3-context3-independent-information-screen-v1/20260819T070756Z-95059c8e"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
SPLIT_SEED=577215; HOLDOUT_MOD=10; EXPECTED_RECORDS=2000000
TARGET_TIMEOUT=10800
MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        [ -f "$ART/context3-exact-tanh-mapper-screen.json" ] && printf 'screen_ready=1\n'
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
[[ "$JASS_JOB_ID" =~ ^cpx62-([0-9]+)-l3-context3-exact-tanh-mapper-screen-v1$ ]] || die "invalid job nomenclature"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "explicit execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "persistent numeric runtime absent; do not reinstall"
PY="$VENV/bin/python"; "$PY" -c 'import numpy,scipy; assert numpy.__version__ and scipy.__version__' || die "numeric runtime invalid"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 15360 ] || die "less than 15 GiB free ($DFA MiB)"
say "host=$(hostname) nproc=$(nproc) mode=ctx3_exact_tanh_mapper_screen eta_minutes=35-120"
say "records=2000000 mapper_fits=18 bootstrap=5000 selfplay=0 patterneval=0 force=0 frozen=0"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_conditional_targets.py \
  jobs/tools/l3_context3_independent_information_screen.py \
  jobs/tools/l3_context3_exact_tanh_mapper_screen.py
"$PY" -m unittest \
  jobs.tests.test_l3_context3_independent_information_screen \
  jobs.tests.test_l3_context3_exact_tanh_mapper_screen \
  jobs.tests.test_l3_context3_exact_tanh_mapper_template >"$W/tests.log" 2>&1

stage fetch-authenticated-inputs
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CORPUS_ROOT" \
  --file artefacts/context2-intervention-2m.jnnw.gz=intervention.jnnw.gz \
  --file artefacts/context2-intervention-2m.jsm.gz=intervention.jsm.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=corpus-summary.json \
  --out-dir "$IN" --report "$ART/verified-corpus.json" --expected-state completed >"$W/fetch-corpus.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$SCREEN_ROOT" \
  --file artefacts/context3-independent-information-screen.json=screen.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=screen-summary.json \
  --file artefacts/split.json=screen-split.json \
  --out-dir "$IN" --report "$ART/verified-screen.json" --expected-state completed >"$W/fetch-screen.log" 2>&1

"$PY" - "$ART" "$IN" <<'PY'
import json,sys
from pathlib import Path
art,src=map(Path,sys.argv[1:3])
expected={
 'verified-corpus.json':('cpx62-1409-l3-context2-intervention-corpus-v1','20260818T184956Z-3465ec72','3465ec720eb37c5c9368f2df048831f7381c5839'),
 'verified-screen.json':('cpx62-1416b-l3-context3-independent-information-screen-v1','20260819T070756Z-95059c8e','95059c8e8a2750d91e499281d28b5adce81b1867')}
for name,identity in expected.items():
 row=json.load(open(art/name)); got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha'))
 if got!=identity or row.get('result_state')!='completed' or row.get('exit_code')!=0:
  raise SystemExit(f'{name}: identity/state drift {got}')
if json.load(open(src/'corpus-summary.json')).get('verdict')!='JASS_CONTEXT2_INTERVENTION_CORPUS_READY': raise SystemExit('corpus verdict drift')
summary=json.load(open(src/'screen-summary.json')); screen=json.load(open(src/'screen.json'))
if summary.get('verdict')!='JASS_CONTEXT3_INDEPENDENT_INFORMATION_SCREEN_PASSED': raise SystemExit('screen summary verdict drift')
if screen.get('verdict')!='JASS_CONTEXT3_INDEPENDENT_INFORMATION_SCREEN_PASSED' or not screen.get('screen_passed'): raise SystemExit('screen report verdict drift')
if summary.get('selected_candidate')!=screen.get('selected_candidate'): raise SystemExit('selected candidate identity drift')
PY

stage reconstruct-opening-group-split
gunzip -c "$IN/intervention.jnnw.gz" >"$W/source.jnnw"
gunzip -c "$IN/intervention.jsm.gz" >"$W/source.jsm"
python3 tools/selfplay_frontier.py split --data "$W/source.jnnw" --meta "$W/source.jsm" \
  --out-data "$W/intervention.jnnw" --out-meta "$W/intervention.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" --manifest "$ART/split.json" >"$W/split.log" 2>&1
read -r RECORDS TRAIN HOLDOUT < <("$PY" - "$ART/split.json" "$IN/screen-split.json" <<'PY'
import json,sys
a,b=map(lambda p:json.load(open(p)),sys.argv[1:3])
for k in ('records','train_records','holdout_records','data_sha256','meta_sha256'):
 if a.get(k)!=b.get(k): raise SystemExit(f'split drift {k}: {a.get(k)} != {b.get(k)}')
print(a['records'],a['train_records'],a['holdout_records'])
PY
)
[ "$RECORDS" -eq "$EXPECTED_RECORDS" ] && [ "$TRAIN" -gt 0 ] && [ "$HOLDOUT" -gt 0 ] || die "split sizing drift"
rm -f "$W/source.jnnw" "$W/source.jsm"

stage build-production-ctx2-dumper
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass jass_tests >"$W/build.log" 2>&1
"$W/build/jass_tests" >"$W/cpp-tests.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "missing jass binary"
timeout 3600s "$J" --dump-conditional-context-v2 "$W/intervention.jnnw" "$W/intervention.ctx2.feat" >"$W/dump.log" 2>&1

stage fit-and-screen-exact-tanh-mappers
/usr/bin/time -f '%e' -o "$W/mapper.seconds" timeout "$TARGET_TIMEOUT" \
  "$PY" jobs/tools/l3_context3_exact_tanh_mapper_screen.py \
    --data "$W/intervention.jnnw" --meta "$W/intervention.jsm" \
    --features "$W/intervention.ctx2.feat" --screen "$IN/screen.json" \
    --train-count "$TRAIN" --scratch "$W/ctx3-scratch" \
    --aligned-out "$ART/ctx3-aligned-mapper-prediction.npy" \
    --feature-shuffled-out "$ART/ctx3-feature-shuffled-mapper-prediction.npy" \
    --report "$ART/context3-exact-tanh-mapper-screen.json" \
    --fold-seed 20260811 --shuffle-seed 2026081903 \
    --bootstrap-seed 2026081905 --bootstrap-replicates 5000 \
    --ridge 1e-4 --max-iterations 100 --tolerance 1e-8 \
    --line-search-steps 20 --chunk-size 50000 >"$W/mapper.log" 2>&1

stage validate-and-publish
"$PY" - "$ART/context3-exact-tanh-mapper-screen.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
if r.get('schema')!='jass.l3_context3_exact_tanh_mapper_screen.v1': raise SystemExit('report schema drift')
if len(r.get('guards',{}))!=11: raise SystemExit('guard count drift')
if r['protocol'].get('patterneval_fits_run')!=0 or r['protocol'].get('force_games_played')!=0: raise SystemExit('forbidden action drift')
if r['protocol'].get('frozen_read') or r['protocol'].get('promotion_authorized'): raise SystemExit('forbidden authorization drift')
if r['shuffle_control'].get('fixed_point_count')!=0: raise SystemExit('shuffle fixed-point drift')
for name in ('ctx2','aligned_ctx3','feature_shuffled_ctx3'):
 m=r['mappings'][name]; fits=[row['fit'] for row in m['folds']]+[m['final_train_fit']['fit']]
 if len(fits)!=6 or not all(row.get('converged') for row in fits): raise SystemExit(f'{name} convergence drift')
PY

"$PY" - "$ART" "$EXPECTED_CODE_SHA" <<'PY' | tee -a "$RES"
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); screen=json.load(open(art/'context3-exact-tanh-mapper-screen.json'))
verdict=screen['verdict']; passed=bool(screen['screen_passed']); selected=screen['protocol']['selected_candidate']
payload={'schema':'jass.l3_context3_exact_tanh_mapper_job.v1','verdict':verdict,
 'code_sha':sys.argv[2],'screen_passed':passed,'selected_candidate':selected,
 'records':screen['source']['records'],'train_records':screen['source']['train_records'],
 'holdout_records':screen['source']['holdout_records'],'contrasts':screen['contrasts'],
 'guards':screen['guards'],'tanh_mapper_fits_run':18,'patterneval_fits_run':0,
 'force_games_played':0,'frozen_read':False,'promotion_authorized':False,
 'automatic_next_job':None,
 'next_recommended_job':('cpx62-1418-l3-context3-paired-targets-and-patterneval-fit-v1' if passed else None)}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/f'VERDICT__{verdict}').touch()
for name,value in screen['guards'].items(): (art/f'GUARD__{name.upper()}__{str(bool(value)).upper()}').touch()
for name,row in screen['contrasts'].items():
 (art/f'CONTRAST__{name.upper()}__EST_PPB_{int(round(row["estimate"]*1e9))}__LO_PPB_{int(round(row["ci95"][0]*1e9))}__HI_PPB_{int(round(row["ci95"][1]*1e9))}').touch()
for name in ('SELFPLAY_GENERATED__FALSE','PATTERNEVAL_FITS_RUN__0','FORCE_GAMES_PLAYED__0','FROZEN_READ__FALSE','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_NEXT_JOB__NULL'):
 (art/name).touch()
print(json.dumps(payload,sort_keys=True))
PY
say "$("$PY" -c 'import json,sys; r=json.load(open(sys.argv[1])); print(r["verdict"],r["protocol"]["selected_candidate"])' "$ART/context3-exact-tanh-mapper-screen.json") patterneval=0 force=0"
