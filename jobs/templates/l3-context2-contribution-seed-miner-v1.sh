#!/usr/bin/env bash
# Mine six deterministic CTX2 seed pools. Read-only: no fit or game generation.
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
AUTOPSY_ROOT="r2:jass-data/runs/cpx62-1413-l3-context2-contribution-autopsy-readout-v1/20260818T204712Z-2d6e9599"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
SPLIT_SEED=577215; HOLDOUT_MOD=10; MINER_SEED=2026081806; PER_POOL=4096
MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        [ -f "$ART/context2-contribution-seeds.json" ] && printf 'seed_manifest_ready=1\n'
      } >"$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120
    done ) & MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  if [ "$rc" -ne 0 ] && [ -s "$W/miner.log" ]; then
    python3 - "$W/miner.log" "$ART" <<'PY'
import json,pathlib,re,sys
log,art=pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2])
tail='\n'.join(log.read_text(errors='replace').splitlines()[-220:])
lines=[line.strip() for line in tail.splitlines() if line.strip()]
exceptions=[line for line in lines if re.match(r'^(?:[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception)|SystemExit):',line)]
root=exceptions[-1] if exceptions else (lines[-1] if lines else 'EMPTY_MINER_LOG')
payload={'schema':1,'verdict':'JASS_CONTEXT2_CONTRIBUTION_SEED_MINER_ROOT_CAUSE_READY',
 'root_cause':root,'miner_log_tail':tail}
(art/'root-cause.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
safe=re.sub(r'[^A-Za-z0-9]+','_',root).strip('_')[:200]
(art/f'ROOT_CAUSE__{safe}').touch()
PY
  fi
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
[[ "$JASS_JOB_ID" =~ ^cpx62-([0-9]+[a-z]?)-l3-context2-contribution-seed-miner-v[0-9]+$ ]] || die "invalid job nomenclature"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "explicit execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "persistent numeric runtime absent; do not reinstall"
PY="$VENV/bin/python"; "$PY" -c 'import numpy,scipy; from scipy.optimize import milp; assert numpy.__version__ and scipy.__version__' || die "numeric runtime invalid"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 10240 ] || die "less than 10 GiB free ($DFA MiB)"
say "host=cpx62 nproc=16 mode=ctx2_contribution_seed_miner eta_minutes=5-12"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_context2_contribution_seed_miner.py
"$PY" -m unittest jobs.tests.test_l3_context2_contribution_seed_miner \
  jobs.tests.test_l3_context2_contribution_seed_miner_template >"$W/tests.log" 2>&1

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
timeout 600s python3 jobs/tools/fetch_result_files.py --prefix "$AUTOPSY_ROOT" \
  --file artefacts/context2-intervention-contribution-autopsy.json=autopsy.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=autopsy-summary.json \
  --out-dir "$IN" --report "$ART/verified-autopsy.json" --expected-state completed >"$W/fetch-autopsy.log" 2>&1

"$PY" - "$ART" "$IN" <<'PY'
import json,sys
from pathlib import Path
art,src=map(Path,sys.argv[1:3])
expected={
 'verified-corpus.json':('cpx62-1409-l3-context2-intervention-corpus-v1','20260818T184956Z-3465ec72','3465ec720eb37c5c9368f2df048831f7381c5839'),
 'verified-mapper.json':('cpx62-1411-l3-context2-intervention-mapper-screen-v1','20260818T200558Z-9ec9195a','9ec9195aeb517798d69609e404b59346405fdd54'),
 'verified-autopsy.json':('cpx62-1413-l3-context2-contribution-autopsy-readout-v1','20260818T204712Z-2d6e9599','2d6e95994ca055bfd942d59c2c6c696323944c9a')}
for name,identity in expected.items():
 row=json.load(open(art/name)); got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha'))
 if got!=identity or row.get('result_state')!='completed' or row.get('exit_code')!=0:
  raise SystemExit(f'{name}: identity/state drift {got}')
if json.load(open(src/'corpus-summary.json')).get('verdict')!='JASS_CONTEXT2_INTERVENTION_CORPUS_READY': raise SystemExit('corpus verdict drift')
if json.load(open(src/'mapper-summary.json')).get('verdict')!='JASS_CONTEXT2_INTERVENTION_MAPPER_SCREEN_FAILED': raise SystemExit('mapper verdict drift')
if json.load(open(src/'autopsy-summary.json')).get('verdict')!='JASS_CONTEXT2_INTERVENTION_CONTRIBUTION_AUTOPSY_AUDITED': raise SystemExit('autopsy verdict drift')
PY

stage reproduce-exact-split
gunzip -c "$IN/original.jnnw.gz" >"$W/original.jnnw"
gunzip -c "$IN/original.jsm.gz" >"$W/original.jsm"
python3 tools/selfplay_frontier.py split --data "$W/original.jnnw" --meta "$W/original.jsm" \
  --out-data "$W/intervention.jnnw" --out-meta "$W/intervention.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" --manifest "$ART/split.json" >"$W/split.log" 2>&1
"$PY" - "$ART/split.json" "$IN/conditional-targets.json" "$W/intervention.jnnw" "$W/intervention.jsm" <<'PY'
import hashlib,json,sys
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1<<20),b''): h.update(block)
 return h.hexdigest()
s=json.load(open(sys.argv[1])); c=json.load(open(sys.argv[2])); src=c['source']
if s.get('records')!=2000000 or s.get('train_records')!=c.get('train_records') or s.get('holdout_records')!=c.get('holdout_records'):
 raise SystemExit('split sizing drift')
if sha(sys.argv[3])!=src.get('data_sha256') or sha(sys.argv[4])!=src.get('meta_sha256'):
 raise SystemExit('split hash drift against mapper input')
PY

stage build-production-ctx2-dumper
timeout 1800s cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
timeout 3600s cmake --build "$W/build" -j16 --target jass jass_tests >"$W/build.log" 2>&1
"$W/build/jass_tests" >"$W/cpp-tests.log" 2>&1
timeout 3600s "$W/build/jass" --dump-conditional-context-v2 \
  "$W/intervention.jnnw" "$W/intervention.ctx2.feat" >"$W/dump.log" 2>&1

stage mine-six-disjoint-seed-pools
timeout 1800s "$PY" jobs/tools/l3_context2_contribution_seed_miner.py \
  --data "$W/intervention.jnnw" --meta "$W/intervention.jsm" \
  --features "$W/intervention.ctx2.feat" --conditional-report "$IN/conditional-targets.json" \
  --autopsy "$IN/autopsy.json" --out-dir "$W/seeds" \
  --manifest "$ART/context2-contribution-seeds.json" --seed "$MINER_SEED" \
  --per-pool "$PER_POOL" >"$W/miner.log" 2>&1

stage production-parser-roundtrip
for pool in blocked_man center_presence king_centrality king_safe_mobility legal_capture_option neutral; do
  timeout 300s "$W/build/jass" --dump-conditional-context-v2 \
    "$W/seeds/$pool.jnnw" "$W/$pool.feat" >"$W/roundtrip-$pool.log" 2>&1
  gzip -n -9 -c "$W/seeds/$pool.jnnw" >"$ART/$pool.jnnw.gz"
done
"$PY" - "$W" "$ART/context2-contribution-seeds.json" "$PER_POOL" <<'PY'
import json,struct,sys
from pathlib import Path
w=Path(sys.argv[1]); manifest=json.load(open(sys.argv[2])); expected=int(sys.argv[3])
if manifest.get('verdict')!='JASS_CONTEXT2_CONTRIBUTION_SEEDS_READY': raise SystemExit('seed verdict drift')
for name,row in manifest['pools'].items():
 raw=(w/f'{name}.feat').read_bytes()
 if len(raw)<12 or raw[:4]!=b'FEAT': raise SystemExit(f'{name}: FEAT roundtrip header drift')
 count,width=struct.unpack_from('<II',raw,4)
 if (count,width)!=(expected,30): raise SystemExit(f'{name}: FEAT roundtrip shape {(count,width)}')
 if row['records']!=expected: raise SystemExit(f'{name}: manifest count drift')
guards=manifest['guards']
expected_exact={'pool_count':6,'exact_records_total':6*expected,'all_pool_counts_exact':True,
 'all_stratum_histograms_identical':True,'all_target_signs_balanced_50_50':True,
 'opening_overlap_count':0,'canonical_duplicate_count':0}
if any(guards.get(key)!=value for key,value in expected_exact.items()):
 raise SystemExit(f'guard drift {guards}')
if not 0 < guards.get('maximum_realized_positions_per_source_game',99) <= 2:
 raise SystemExit(f'source-game cap drift {guards}')
PY

stage publish-seed-certificate
"$PY" - "$ART" "$EXPECTED_CODE_SHA" <<'PY' | tee -a "$RES"
import json,re,sys
from pathlib import Path
art=Path(sys.argv[1]); manifest=json.load(open(art/'context2-contribution-seeds.json'))
payload={'schema':'jass.l3_context2_contribution_seed_miner_job.v1',
 'verdict':manifest['verdict'],'code_sha':sys.argv[2],'seed':manifest['seed'],
 'target_components':manifest['target_components'],'pools':manifest['pools'],
 'guards':manifest['guards'],'mapper_fits_run':0,'patterneval_fits_run':0,
 'selfplay_generated':False,'force_games_played':0,'frozen_read':False,
 'promotion_authorized':False,'next_recommended_job':'cpx62-1415-l3-context2-contribution-balanced-pilot-v1',
 'automatic_next_job':None}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/f'VERDICT__{manifest["verdict"]}').touch()
for name,row in manifest['pools'].items():
 safe=re.sub('[^A-Za-z0-9_.-]+','_',name)
 (art/f'POOL__{safe}__N_{row["records"]}__SHA_{row["sha256"][:16]}').touch()
for name in ('MAPPER_FITS_RUN__0','PATTERNEVAL_FITS_RUN__0','SELFPLAY_GENERATED__FALSE',
 'FORCE_GAMES_PLAYED__0','FROZEN_READ__FALSE','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_NEXT_JOB__NULL'):
 (art/name).touch()
print(json.dumps(payload,sort_keys=True))
PY
say "JASS_CONTEXT2_CONTRIBUTION_SEEDS_READY pools=6 records=24576 selfplay=false fits=0"
