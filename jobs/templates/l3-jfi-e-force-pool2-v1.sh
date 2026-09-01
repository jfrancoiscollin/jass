#!/usr/bin/env bash
# JFI-E Pool2: one unchanged replication, only after positive Pool1, followed by
# the terminal two-pool readout. No third pool and no promotion are authorized.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${BOUNDARY_C_ROOT:?}"; : "${EXPECTED_BOUNDARY_C_JOB:?}"; : "${EXPECTED_BOUNDARY_C_ATTEMPT:?}"; : "${EXPECTED_BOUNDARY_C_CODE_SHA:?}"
: "${JFI_D_ROOT:?}"; : "${EXPECTED_JFI_D_JOB:?}"; : "${EXPECTED_JFI_D_ATTEMPT:?}"; : "${EXPECTED_JFI_D_CODE_SHA:?}"
: "${JFI_E_POOL1_ROOT:?}"; : "${EXPECTED_JFI_E_POOL1_JOB:?}"; : "${EXPECTED_JFI_E_POOL1_ATTEMPT:?}"; : "${EXPECTED_JFI_E_POOL1_CODE_SHA:?}"
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
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-jfi-e-force-pool2-v1$ ]]||die "nomenclature mismatch"
[ "${JFI_POOL2_AUTHORIZED:-0}" = 1 ]&&[ "${POST_POSITIVE_POOL1_AUTHORIZED:-0}" = 1 ]||die "Pool2 authorization missing"
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

stage authenticate-positive-pool1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$JFI_E_POOL1_ROOT" \
  --file artefacts/JFI_E_POOL1_READOUT.json=pool1-readout.json \
  --file artefacts/JFI_E_POOL1_PROTOCOL.json=pool1-protocol.json \
  --file artefacts/JFI_FORCE_POOL1_NATIVE.json=pool1-native.json \
  --file artefacts/JFI_FORCE_POOL1_Q00.json=pool1-q00.json \
  --file artefacts/jfi-force-pool1-openings.fen=pool1-openings.fen \
  --file artefacts/jfi-force-pool1-openings-selector.json=pool1-selector.json \
  --file artefacts/jfi-force-pool1-openings-provenance.json=pool1-provenance.json \
  --file artefacts/POOL2_AUTHORIZED__TRUE=POOL2_AUTHORIZED \
  --out-dir "$IN" --report "$ART/verified-jfi-e-pool1.json" >"$W/fetch-pool1.log" 2>&1
"$PY" - "$IN" "$ART/verified-jfi-e-pool1.json" "$EXPECTED_JFI_E_POOL1_JOB" "$EXPECTED_JFI_E_POOL1_ATTEMPT" "$EXPECTED_JFI_E_POOL1_CODE_SHA" <<'PY'
import hashlib,json,sys
root,receipt=sys.argv[1:3]; job,attempt,code=sys.argv[3:]; load=lambda n:json.load(open(f'{root}/{n}'))
v=json.load(open(receipt)); r=load('pool1-readout.json'); p=load('pool1-protocol.json')
sha=lambda n:hashlib.sha256(open(f'{root}/{n}','rb').read()).hexdigest()
if (v.get('job_id'),v.get('attempt_id'),v.get('code_sha'),v.get('result_state'))!=(job,attempt,code,'completed'):
 raise SystemExit('JFI-E Pool1 identity drift')
if r.get('verdict')!='JFI_POOL1_NATIVE_POSITIVE' or r.get('pool2_authorized') is not True:
 raise SystemExit('Pool2 was not scientifically authorized')
if p.get('code_sha')!=code or p.get('pool',{}).get('fen_sha256')!=sha('pool1-openings.fen'):
 raise SystemExit('Pool1 reproducibility receipt drift')
for view in ('native','q00'):
 if r[{'native':'primary_native','q00':'secondary_q00'}[view]]['openings_sha256']!=sha('pool1-openings.fen'):
  raise SystemExit(f'Pool1 {view} opening link drift')
PY

stage authenticate-frozen-inputs
jfi_authenticate_force_inputs
"$PY" jobs/tools/jfi_force_readout.py --mode pool1 \
  --pool1-native "$IN/pool1-native.json" --pool1-q00 "$IN/pool1-q00.json" \
  --candidate-sha "$CANDIDATE_SHA" --curriculum-sha "$JFI_CURRICULUM_SHA" \
  --executable-sha "$BOUNDARY_EXE_SHA" --search-params "$JFI_Q00" \
  --out "$W/recomputed-pool1.json" >"$W/recompute-pool1.log" 2>&1
[ "$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$W/recomputed-pool1.json")" = JFI_POOL1_NATIVE_POSITIVE ] \
  || die "Pool1 positive verdict does not reproduce"
jfi_fetch_force_exclusions
stage build-identical-engine
jfi_build_force_engine

stage generate-certify-fresh-pool2
jfi_generate_pool jfi-force-pool2-openings 2026120120 --exclude "$IN/pool1-openings.fen"

stage force-pool2-native-primary
jfi_run_gate "$ART/jfi-force-pool2-openings.fen" native 2026120121 JFI_FORCE_POOL2_NATIVE
stage force-pool2-q00-diagnostic
jfi_run_gate "$ART/jfi-force-pool2-openings.fen" q00 2026120121 JFI_FORCE_POOL2_Q00

stage chained-terminal-readout
"$PY" jobs/tools/jfi_force_readout.py --mode final \
  --pool1-native "$IN/pool1-native.json" --pool1-q00 "$IN/pool1-q00.json" \
  --pool2-native "$ART/JFI_FORCE_POOL2_NATIVE.json" --pool2-q00 "$ART/JFI_FORCE_POOL2_Q00.json" \
  --candidate-sha "$CANDIDATE_SHA" --curriculum-sha "$JFI_CURRICULUM_SHA" \
  --executable-sha "$BOUNDARY_EXE_SHA" --search-params "$JFI_Q00" \
  --out "$ART/JFI_E_FINAL_READOUT.json" >"$W/readout.log" 2>&1
VERDICT=$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JFI_E_FINAL_READOUT.json")
for name in pool1-readout.json pool1-protocol.json pool1-native.json pool1-q00.json pool1-openings.fen pool1-selector.json pool1-provenance.json; do cp "$IN/$name" "$ART/$name"; done
"$PY" - "$ART/JFI_E_POOL2_PROTOCOL.json" "$EXPECTED_CODE_SHA" "$CANDIDATE_SHA" "$JFI_CURRICULUM_SHA" "$BOUNDARY_EXE_SHA" "$ART" <<'PY'
import hashlib,json,sys
out,code,candidate,curriculum,exe,root=sys.argv[1:]
sha=lambda p:hashlib.sha256(open(p,'rb').read()).hexdigest()
payload={'schema':'jass.jfi.e_pool2_protocol.v1','code_sha':code,
 'models':{'candidate_sha256':candidate,'curriculum_sha256':curriculum},'executable_sha256':exe,
 'pool':{'generator_seed':2026120120,'openings':3000,'candidates':30000,
         'fen_sha256':sha(f'{root}/jfi-force-pool2-openings.fen'),
         'selector_sha256':sha(f'{root}/jfi-force-pool2-openings-selector.json'),
         'provenance_sha256':sha(f'{root}/jfi-force-pool2-openings-provenance.json'),
         'historical_exclusions':26,'pool1_excluded':True},
 'gates':{'native':{'games':6000,'movetime':0.1,'bootstrap_seed':2026120121},
          'q00':{'games':6000,'depth':9,'bootstrap_seed':2026120121}},
 'chained_native':{'bootstrap_samples':200000,'bootstrap_seed':2026120199,'games':12000},
 'guards':{'SCAN_READS':0,'PROMOTION_AUTHORIZED':False,'THIRD_POOL_AUTHORIZED':False}}
open(out,'w').write(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY
printf '%s\n' "$VERDICT" >"$ART/VERDICT__$VERDICT"; printf '6000\n' >"$ART/FRESH_OPENINGS__6000"
printf '24000\n' >"$ART/GAMES_TOTAL__24000"; printf '0\n' >"$ART/SCAN_READS__0"
printf 'FALSE\n' >"$ART/THIRD_POOL_AUTHORIZED__FALSE"; printf 'FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"
say "$VERDICT cumulative_native_games=12000 cumulative_q00_games=12000 third_pool=false promotion=false"
