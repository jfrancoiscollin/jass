#!/usr/bin/env bash
# JFI-E Pool1: frozen JASS_NATIVE_ACTIVE_V1 vs CURRICULUM on one fresh,
# historically disjoint 3000-opening pool. Native 0.1 s is primary; Q00 is diagnostic.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${BOUNDARY_C_ROOT:?}"; : "${EXPECTED_BOUNDARY_C_JOB:?}"; : "${EXPECTED_BOUNDARY_C_ATTEMPT:?}"; : "${EXPECTED_BOUNDARY_C_CODE_SHA:?}"
: "${JFI_D_ROOT:?}"; : "${EXPECTED_JFI_D_JOB:?}"; : "${EXPECTED_JFI_D_ATTEMPT:?}"; : "${EXPECTED_JFI_D_CODE_SHA:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"; GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$IN" "$ART" "$GEOM"; RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; echo start >"$STAGE"
say(){ echo "$*"|tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }; stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"; PY="$VENV/bin/python"
# shellcheck source=jfi-force-common-v1.sh
source jobs/templates/jfi-force-common-v1.sh
MON=""
monitor(){ (t0=$(date +%s); while true; do
  { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"; printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null||echo unknown)"; printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"; } >"$PROG.tmp"
  mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120; done) & MON="$!"; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ]||{ kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null||true; [ -f "$PROG" ]&&cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W"&&find . -type f -name '*.log' -print0|tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null||true
  rm -rf "$W/build" "$W"/gate-* "$IN" "$GEOM" 2>/dev/null||true; exit "$rc"; }
trap finalize EXIT; trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ]||die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-jfi-e-force-pool1-v1$ ]]||die "nomenclature mismatch"
[ "${GO_JFI_FORCE:-0}" = 1 ]&&[ "${POST_BOUNDARY_C_AUTHORIZED:-0}" = 1 ]||die "JFI-E authorization missing"
[ "${NO_SCAN_READS:-0}" = 1 ]&&[ "${NO_PROMOTION:-0}" = 1 ]&&[ "${NO_THIRD_POOL:-0}" = 1 ]||die "decision guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ]&&[ -z "$(git branch --show-current)" ]&&[ -z "$(git status --porcelain)" ]||die "source drift"
[ "$(hostname)" = cpx62 ]&&[ "$(nproc)" -eq 16 ]||die "CPX62 contract mismatch"
[ -f "$VENV/.jass-runtime-ready-v1" ]&&[ "$(tr ',' '\n' <<<"$JFI_Q00"|wc -l)" -eq 63 ]||die "runtime/Q00 drift"
"$PY" -c 'import numpy; assert numpy.__version__' || die "numeric runtime invalid"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/jfi_force_readout.py jobs/tools/run_jass_gate_bounded.py \
  jobs/tools/select_independent_opening_pool.py jobs/tools/validate_opening_pool.py
"$PY" -m unittest jobs.tests.test_jfi_force_readout >"$W/python-tests.log" 2>&1

stage authenticate-frozen-inputs
jfi_authenticate_force_inputs
jfi_fetch_force_exclusions

stage build-identical-engine
jfi_build_force_engine

stage generate-certify-fresh-pool1
jfi_generate_pool jfi-force-pool1-openings 2026120110

stage force-pool1-native-primary
jfi_run_gate "$ART/jfi-force-pool1-openings.fen" native 2026120111 JFI_FORCE_POOL1_NATIVE
stage force-pool1-q00-diagnostic
jfi_run_gate "$ART/jfi-force-pool1-openings.fen" q00 2026120111 JFI_FORCE_POOL1_Q00

stage pool1-readout-and-decision
"$PY" jobs/tools/jfi_force_readout.py --mode pool1 \
  --pool1-native "$ART/JFI_FORCE_POOL1_NATIVE.json" --pool1-q00 "$ART/JFI_FORCE_POOL1_Q00.json" \
  --candidate-sha "$CANDIDATE_SHA" --curriculum-sha "$JFI_CURRICULUM_SHA" \
  --executable-sha "$BOUNDARY_EXE_SHA" --search-params "$JFI_Q00" \
  --out "$ART/JFI_E_POOL1_READOUT.json" >"$W/readout.log" 2>&1
read -r VERDICT AUTHORIZED < <("$PY" - "$ART/JFI_E_POOL1_READOUT.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); print(d['verdict'],str(d['pool2_authorized']).upper())
PY
)
"$PY" - "$ART/JFI_E_POOL1_PROTOCOL.json" "$EXPECTED_CODE_SHA" "$CANDIDATE_SHA" "$JFI_CURRICULUM_SHA" "$BOUNDARY_EXE_SHA" "$ART" <<'PY'
import hashlib,json,sys
out,code,candidate,curriculum,exe,root=sys.argv[1:]
sha=lambda p:hashlib.sha256(open(p,'rb').read()).hexdigest()
payload={'schema':'jass.jfi.e_pool1_protocol.v1','code_sha':code,
 'models':{'candidate_sha256':candidate,'curriculum_sha256':curriculum},'executable_sha256':exe,
 'pool':{'generator_seed':2026120110,'openings':3000,'candidates':30000,
         'fen_sha256':sha(f'{root}/jfi-force-pool1-openings.fen'),
         'selector_sha256':sha(f'{root}/jfi-force-pool1-openings-selector.json'),
         'provenance_sha256':sha(f'{root}/jfi-force-pool1-openings-provenance.json'),
         'historical_exclusions':26},
 'gates':{'native':{'games':6000,'movetime':0.1,'bootstrap_seed':2026120111},
          'q00':{'games':6000,'depth':9,'bootstrap_seed':2026120111}},
 'guards':{'SCAN_READS':0,'PROMOTION_AUTHORIZED':False,'THIRD_POOL_AUTHORIZED':False}}
open(out,'w').write(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY
printf '%s\n' "$VERDICT" >"$ART/VERDICT__$VERDICT"; printf '%s\n' "$AUTHORIZED" >"$ART/POOL2_AUTHORIZED__$AUTHORIZED"
printf '3000\n' >"$ART/FRESH_OPENINGS__3000"; printf '12000\n' >"$ART/GAMES_TOTAL__12000"
printf '0\n' >"$ART/SCAN_READS__0"; printf 'FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"
say "$VERDICT native_games=6000 q00_games=6000 pool2_authorized=$AUTHORIZED promotion=false"
