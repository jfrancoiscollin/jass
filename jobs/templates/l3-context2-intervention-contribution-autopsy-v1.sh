#!/usr/bin/env bash
# Attribute the failed 1411 mapper concentration to the six source cells.
# Read-only replay: no mapper/PatternEval fit, self-play, force, frozen or promotion.
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
CURRENT_ROOT="r2:jass-data/runs/home-1397-l3-context2-fixed-contribution-audit-v1/20260817T222724Z-f60336ca"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
SPLIT_SEED=577215; HOLDOUT_MOD=10; EXPECTED_RECORDS=2000000
MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        [ -f "$ART/context2-intervention-contribution-autopsy.json" ] && printf 'autopsy_ready=1\n'
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
  rm -rf "$IN" "$W" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-([0-9]+)-l3-context2-intervention-contribution-autopsy-v1$ ]] || die "invalid job nomenclature"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "explicit execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "persistent numeric runtime absent; do not reinstall"
PY="$VENV/bin/python"; "$PY" -c 'import numpy; assert numpy.__version__' || die "numeric runtime invalid"
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 10240 ] || die "less than 10 GiB free ($DFA MiB)"
say "host=cpx62 nproc=16 mode=ctx2_contribution_autopsy comparable_1411_seconds=323 eta_minutes=5-12"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_context2_intervention_contribution_autopsy.py
"$PY" -m unittest jobs.tests.test_l3_context2_intervention_contribution_autopsy \
  jobs.tests.test_l3_context2_intervention_contribution_autopsy_template >"$W/tests.log" 2>&1

stage fetch-authenticated-sources
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CORPUS_ROOT" \
  --file artefacts/context2-intervention-2m.jnnw.gz=original.jnnw.gz \
  --file artefacts/context2-intervention-2m.jsm.gz=original.jsm.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=corpus-summary.json \
  --out-dir "$IN" --report "$ART/verified-corpus.json" --expected-state completed >"$W/fetch-corpus.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$MAPPER_ROOT" \
  --file artefacts/conditional-targets.json=conditional-targets.json \
  --file artefacts/intervention-contribution-audit.json=intervention-contribution-audit.json \
  --file artefacts/intervention-mapper-screen.json=intervention-mapper-screen.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=mapper-summary.json \
  --out-dir "$IN" --report "$ART/verified-mapper.json" --expected-state completed >"$W/fetch-mapper.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRENT_ROOT" \
  --file artefacts/fixed-current2m-contribution-audit.json=current-contribution-audit.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=current-summary.json \
  --out-dir "$IN" --report "$ART/verified-current.json" --expected-state completed >"$W/fetch-current.log" 2>&1

"$PY" - "$ART" "$IN" <<'PY'
import json,sys
from pathlib import Path
art,src=map(Path,sys.argv[1:3])
expected={
 'verified-corpus.json':('cpx62-1409-l3-context2-intervention-corpus-v1','20260818T184956Z-3465ec72','3465ec720eb37c5c9368f2df048831f7381c5839'),
 'verified-mapper.json':('cpx62-1411-l3-context2-intervention-mapper-screen-v1','20260818T200558Z-9ec9195a','9ec9195aeb517798d69609e404b59346405fdd54'),
 'verified-current.json':('home-1397-l3-context2-fixed-contribution-audit-v1','20260817T222724Z-f60336ca','f60336ca7b29e976e14c47eba92223fedd30eebf')}
for name,identity in expected.items():
 row=json.load(open(art/name)); got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha'))
 if got!=identity or row.get('result_state')!='completed' or row.get('exit_code')!=0:
  raise SystemExit(f'{name}: identity/state drift {got}')
if json.load(open(src/'corpus-summary.json')).get('verdict')!='JASS_CONTEXT2_INTERVENTION_CORPUS_READY': raise SystemExit('corpus verdict drift')
if json.load(open(src/'mapper-summary.json')).get('verdict')!='JASS_CONTEXT2_INTERVENTION_MAPPER_SCREEN_FAILED': raise SystemExit('1411 verdict drift')
if json.load(open(src/'current-summary.json')).get('verdict')!='JASS_CONTEXT2_FIXED_CONTRIBUTION_AUDITED': raise SystemExit('CURRENT verdict drift')
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
 raise SystemExit('split hash drift against certified mapper input')
PY

stage build-production-ctx2-dumper
for file in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/movegen.cpp src/movegen.hpp; do
  git show "$EXPECTED_CODE_SHA:$file" >"$W/$(basename "$file").expected"
  cmp -s "$file" "$W/$(basename "$file").expected" || die "architecture source drift: $file"
done
grep -q "g_emasks" src/scan_eval.cpp || die "archi: scan_eval without g_emasks"
grep -q "has_any_capture" src/search.cpp || die "archi: search without has_any_capture"
grep -q "has_any_capture" src/movegen.cpp || die "archi: movegen without has_any_capture"
timeout 1800s cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
timeout 3600s cmake --build "$W/build" -j16 --target jass jass_tests >"$W/build.log" 2>&1
"$W/build/jass_tests" >"$W/cpp-tests.log" 2>&1
timeout 3600s "$W/build/jass" --dump-conditional-context-v2 \
  "$W/intervention.jnnw" "$W/intervention.ctx2.feat" >"$W/dump.log" 2>&1

stage replay-and-localize-contributions
timeout 1800s "$PY" jobs/tools/l3_context2_intervention_contribution_autopsy.py \
  --original-meta "$W/original.jsm" --split-meta "$W/intervention.jsm" \
  --features "$W/intervention.ctx2.feat" --conditional-report "$IN/conditional-targets.json" \
  --intervention-audit "$IN/intervention-contribution-audit.json" \
  --current-audit "$IN/current-contribution-audit.json" --corpus-summary "$IN/corpus-summary.json" \
  --split-seed "$SPLIT_SEED" --holdout-mod "$HOLDOUT_MOD" \
  --out "$ART/context2-intervention-contribution-autopsy.json" >"$W/autopsy.log" 2>&1

stage publish-autopsy
"$PY" - "$ART" "$EXPECTED_CODE_SHA" <<'PY' | tee -a "$RES"
import json,re,sys
from pathlib import Path
art=Path(sys.argv[1]); report=json.load(open(art/'context2-intervention-contribution-autopsy.json'))
if report.get('verdict')!='JASS_CONTEXT2_INTERVENTION_CONTRIBUTION_AUTOPSY_READY': raise SystemExit('autopsy verdict drift')
lattice=report['fixed_mapper_quota_lattice']; dominant=report['dominant_component']['component']
payload={'schema':'jass.l3_context2_intervention_contribution_autopsy_job.v1',
 'verdict':report['verdict'],'code_sha':sys.argv[2],
 'dominant_component':dominant,'dominant_share':report['dominant_component']['absolute_logit_share'],
 'quota_only_rescue_predicted':lattice['quota_only_rescue_predicted'],
 'full_gate_candidates':lattice['full_gate_candidates'],'best_candidate':lattice['best_candidate'],
 'mechanism':report['mechanism'],'mapper_fits_run':0,'patterneval_fits_run':0,
 'selfplay_generated':False,'force_games_played':0,'frozen_read':False,
 'promotion_authorized':False,'automatic_next_job':None}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/f'VERDICT__{report["verdict"]}').touch()
safe=re.sub('[^A-Za-z0-9_.-]+','_',dominant)
(art/f'DOMINANT_COMPONENT__{safe}').touch()
(art/f'QUOTA_ONLY_RESCUE__{str(bool(lattice["quota_only_rescue_predicted"])).upper()}').touch()
(art/f'FULL_GATE_CANDIDATES__{int(lattice["full_gate_candidates"])}').touch()
for name in ('MAPPER_FITS_RUN__0','PATTERNEVAL_FITS_RUN__0','SELFPLAY_GENERATED__FALSE',
 'FORCE_GAMES_PLAYED__0','FROZEN_READ__FALSE','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_NEXT_JOB__NULL'):
 (art/name).touch()
print(json.dumps(payload,sort_keys=True))
PY
say "JASS_CONTEXT2_INTERVENTION_CONTRIBUTION_AUTOPSY_READY mapper_fits=0 patterneval_fits=0 selfplay=false force=0"
