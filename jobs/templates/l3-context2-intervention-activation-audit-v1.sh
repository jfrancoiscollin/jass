#!/usr/bin/env bash
# Realized CTX2 activation/covariance screen on the certified intervention 2M.
# Read-only: no self-play, mapper/PatternEval fit, force game, frozen or promotion.
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
BASELINE_ROOT="r2:jass-data/runs/home-1395-l3-context2-knob-attribution-v1/20260817T211534Z-f4e9fe1e"
CURRENT_ROOT="r2:jass-data/runs/home-1397-l3-context2-fixed-contribution-audit-v1/20260817T222724Z-f60336ca"
PLAN_ROOT="r2:jass-data/runs/cpx62-1408-l3-context2-intervention-plan-v1/20260818T182226Z-20fd6621"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        [ -f "$ART/context2-intervention-activation.json" ] && printf 'census_ready=1\n'
        [ -f "$ART/context2-intervention-activation-audit.json" ] && printf 'audit_ready=1\n'
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
[[ "$JASS_JOB_ID" =~ ^cpx62-([0-9]+)-l3-context2-intervention-activation-audit-v1$ ]] || die "invalid job nomenclature"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "explicit execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "persistent numeric runtime absent; do not reinstall"
PY="$VENV/bin/python"; "$PY" -c 'import numpy; assert numpy.__version__' || die "numeric runtime invalid"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 5120 ] || die "less than 5 GiB free ($DFA MiB)"
say "host=$(hostname) nproc=$(nproc) mode=ctx2_intervention_activation_audit eta_minutes=15-35"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_context2_activation_census.py jobs/tools/l3_context2_intervention_activation_audit.py
"$PY" -m unittest jobs.tests.test_l3_context2_activation_census \
  jobs.tests.test_l3_context2_intervention_activation_audit \
  jobs.tests.test_l3_context2_intervention_activation_template >"$W/tests.log" 2>&1

stage fetch-authenticated-inputs
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CORPUS_ROOT" \
  --file artefacts/context2-intervention-2m.jnnw.gz=intervention.jnnw.gz \
  --file artefacts/context2-intervention-2m.jsm.gz=intervention.jsm.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=corpus-summary.json \
  --out-dir "$IN" --report "$ART/verified-corpus.json" --expected-state completed >"$W/fetch-corpus.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$BASELINE_ROOT" \
  --file artefacts/cells/BASE-activation.json=baseline-activation.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=baseline-summary.json \
  --out-dir "$IN" --report "$ART/verified-baseline.json" --expected-state completed >"$W/fetch-baseline.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRENT_ROOT" \
  --file artefacts/fixed-current2m-contribution-audit.json=current-contribution.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=current-summary.json \
  --out-dir "$IN" --report "$ART/verified-current.json" --expected-state completed >"$W/fetch-current.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$PLAN_ROOT" \
  --file artefacts/context2-intervention-plan.json=plan.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=plan-summary.json \
  --out-dir "$IN" --report "$ART/verified-plan.json" --expected-state completed >"$W/fetch-plan.log" 2>&1

"$PY" - "$ART" "$IN" <<'PY'
import json,sys
from pathlib import Path
art,src=map(Path,sys.argv[1:3])
expected={
 'verified-corpus.json':('cpx62-1409-l3-context2-intervention-corpus-v1','20260818T184956Z-3465ec72','3465ec720eb37c5c9368f2df048831f7381c5839'),
 'verified-baseline.json':('home-1395-l3-context2-knob-attribution-v1','20260817T211534Z-f4e9fe1e','f4e9fe1ef103fb52e7e3a2c10e967bc736e934f7'),
 'verified-current.json':('home-1397-l3-context2-fixed-contribution-audit-v1','20260817T222724Z-f60336ca','f60336ca7b29e976e14c47eba92223fedd30eebf'),
 'verified-plan.json':('cpx62-1408-l3-context2-intervention-plan-v1','20260818T182226Z-20fd6621','20fd66216dc28c14a8d3e4b258e9fe65bad52351')}
for name,identity in expected.items():
 row=json.load(open(art/name)); got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha'))
 if got!=identity or row.get('result_state')!='completed' or row.get('exit_code')!=0:
  raise SystemExit(f'{name}: identity/state drift {got}')
if json.load(open(src/'corpus-summary.json')).get('verdict')!='JASS_CONTEXT2_INTERVENTION_CORPUS_READY':
 raise SystemExit('corpus verdict drift')
if json.load(open(src/'baseline-summary.json')).get('verdict')!='JASS_CONTEXT2_KNOB_ATTRIBUTION_READY':
 raise SystemExit('baseline verdict drift')
if json.load(open(src/'current-summary.json')).get('verdict')!='JASS_CONTEXT2_FIXED_CONTRIBUTION_AUDITED':
 raise SystemExit('CURRENT contribution verdict drift')
if json.load(open(src/'plan-summary.json')).get('verdict')!='JASS_CONTEXT2_INTERVENTION_PLAN_READY':
 raise SystemExit('plan verdict drift')
PY

stage decompress-and-roundtrip
gunzip -c "$IN/intervention.jnnw.gz" >"$W/intervention.jnnw"
gunzip -c "$IN/intervention.jsm.gz" >"$W/intervention.jsm"
"$PY" jobs/tools/assert_corpus_wdl.py --data "$W/intervention.jnnw" >"$W/wdl.log" 2>&1

stage build-production-ctx2-dumper
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass jass_tests >"$W/build.log" 2>&1
"$W/build/jass_tests" >"$W/cpp-tests.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "missing jass binary"

stage dump-production-ctx2-on-intervention-2m
timeout 3600s "$J" --dump-conditional-context-v2 "$W/intervention.jnnw" "$W/intervention.ctx2.feat" >"$W/dump.log" 2>&1

stage analyze-realized-activation-and-covariance
timeout 3600s "$PY" jobs/tools/l3_context2_activation_census.py analyze \
  --data "$W/intervention.jnnw" --meta "$W/intervention.jsm" --feat "$W/intervention.ctx2.feat" \
  --material-threshold 1e-6 --rare-threshold 1e-3 --rank-rows 250000 \
  --report "$ART/context2-intervention-activation.json" \
  --csv "$ART/context2-intervention-activation.csv" \
  --markdown "$ART/context2-intervention-activation.md" >"$W/analyse.log" 2>&1
timeout 600s "$PY" jobs/tools/l3_context2_intervention_activation_audit.py \
  --intervention "$ART/context2-intervention-activation.json" \
  --baseline "$IN/baseline-activation.json" --corpus-summary "$IN/corpus-summary.json" \
  --plan "$IN/plan.json" --current-contribution "$IN/current-contribution.json" \
  --out "$ART/context2-intervention-activation-audit.json" >"$W/audit.log" 2>&1

stage publish-screen-certificate
"$PY" - "$ART" "$EXPECTED_CODE_SHA" <<'PY' | tee -a "$RES"
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); audit=json.load(open(art/'context2-intervention-activation-audit.json'))
verdict=audit['verdict']
payload={'schema':'jass.l3_context2_intervention_activation_job.v1','verdict':verdict,
 'code_sha':sys.argv[2],'screen_passed':audit['screen_passed'],'audit':audit,
 'selfplay_generated':False,'fits_run':0,'force_games_played':0,'frozen_read':False,
 'promotion_authorized':False,'automatic_next_job':None}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/f'VERDICT__{verdict}').touch()
for name,value in audit['guards'].items(): (art/f'GUARD__{name}__{str(bool(value)).upper()}').touch()
r=audit['realized']
(art/f'LOGDET_GAIN_VS_BASE__MICRO_{int(round(r["logdet_gain_vs_base"]*1e6))}').touch()
(art/f'EFFECTIVE_COVARIANCE_DIMENSION__MILLI_{int(round(r["effective_covariance_dimension"]*1000))}').touch()
(art/f'MAX_ABS_PAIR_CORRELATION__PPM_{int(round(r["maximum_absolute_pair_correlation"]*1e6))}').touch()
for name in ('SELFPLAY_GENERATED__FALSE','FITS_RUN__0','FORCE_GAMES_PLAYED__0','FROZEN_READ__FALSE','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_NEXT_JOB__NULL'):
 (art/name).touch()
print(json.dumps(payload,sort_keys=True))
PY
say "$("$PY" -c 'import json,sys; a=json.load(open(sys.argv[1])); print(a["verdict"])' "$ART/context2-intervention-activation-audit.json") fits=0 force=0 frozen=false promotion=false"
