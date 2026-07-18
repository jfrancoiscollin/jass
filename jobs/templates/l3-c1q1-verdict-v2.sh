#!/usr/bin/env bash
# template: L3-PURE C1-Q1 contract-complete verdict v2
# description: rerun evaluation only from the four immutable G2 artifacts;
#              common-search + native equal-time + paired P1-P4 conversion
# expected_duration: recalibrate on the target box before GitOps queueing
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"; : "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"

: "${EXPECTED_CODE_SHA:?GitOps wrapper must pin the reviewed merge SHA}"
# 4 C1-Q1 cells (v2, fixed runner). Q00 = baseline (capture only).
declare -A PREFIX=(
  [Q00]="r2:jass-data/runs/ccx33-0802-c1q1-q00-v2/20260718T164932Z-e6787b8a"
  [Q10]="r2:jass-data/runs/cpx62-0804-c1q1-q10-v2/20260718T165133Z-e6787b8a"
  [Q01]="r2:jass-data/runs/cpx62-0805-c1q1-q01-v2/20260718T165700Z-e6787b8a"
  [Q11]="r2:jass-data/runs/ccx33-0803-c1q1-q11-v2/20260718T165432Z-e6787b8a"
)
declare -A SRCJOB=(
  [Q00]="ccx33-0802-c1q1-q00-v2" [Q10]="cpx62-0804-c1q1-q10-v2"
  [Q01]="cpx62-0805-c1q1-q01-v2" [Q11]="ccx33-0803-c1q1-q11-v2"
)
CELLS=(Q00 Q10 Q01 Q11)
NOPEN="${NOPEN:-300}"; NSH_GATE="${NSH_GATE:-16}"; PAR_GATE="${PAR_GATE:-5}"
NSH_CONV="${NSH_CONV:-8}"; PAR_CONV="${PAR_CONV:-4}"
DEPTH="${DEPTH:-9}"; CONV_DEPTH="${CONV_DEPTH:-10}"; ARB_DEPTH="${ARB_DEPTH:-14}"
NATIVE_MOVETIME="${NATIVE_MOVETIME:-0.1}"; BOOTSTRAP_REPLICATES="${BOOTSTRAP_REPLICATES:-10000}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-7200}"
CACHE_MB="${CACHE_MB:-128}"; JASS_BUILD_JOBS="${JASS_BUILD_JOBS:-8}"; FULL_RUN_APPROVED="${FULL_RUN_APPROVED:-0}"
SCREEN_DELTA="${SCREEN_DELTA:-0.02}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; INPUTS="$JASS_RESULT_DIR/inputs"; CRUN="$JASS_RESULT_DIR/cells"
mkdir -p "$W" "$ART" "$INPUTS" "$CRUN"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/STAGE.txt"; : > "$RES"; echo preflight > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
set_stage(){ echo "$1" > "$STAGE"; say "stage=$1 time_fr=$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"; }
run_pids(){ local label="$1"; shift; local fail=0 pid; for pid in "$@"; do wait "$pid" || fail=$((fail+1)); done; [ "$fail" -eq 0 ] || die "$label: $fail failed"; }
jnnw_count(){ python3 - "$1" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(8)
if len(b)!=8 or b[:4]!=b'JNNW': raise SystemExit(2)
print(struct.unpack('<I',b[4:8])[0])
PY
}
MONITOR_PID=""
monitor(){ ( while true; do { TZ=Europe/Paris date '+time_fr=%Y-%m-%dT%H:%M:%S%z'; printf 'stage=%s\n' "$(cat "$STAGE" 2>/dev/null||echo ?)";
  df -Pm "$JASS_RESULT_DIR"|awk 'NR==2{printf "free_mb=%s\n",$4}';
  printf 'gate_results=%s conv_shards=%s\n' "$(find "$W" -name 'gate.*.log' -exec grep -h '^RESULT ' {} + 2>/dev/null|wc -l)" "$(find "$W" -maxdepth 1 -name '*.conv.*.json' 2>/dev/null|wc -l)"; } > "$PROG.tmp"; mv "$PROG.tmp" "$PROG"; sleep 300; done ) & MONITOR_PID="$!"; }
finalize(){ rc=$?; trap - EXIT; set +e; [ -n "$MONITOR_PID" ] && { kill "$MONITOR_PID" 2>/dev/null; wait "$MONITOR_PID" 2>/dev/null; }
  [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"; [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt";
  [ -d "$W" ] && (cd "$W" && find . -type f -name '*.log' -print0|tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null||true;
  rm -rf "$W/build8" "$W/build32" "$W"/gate-* "$W/strata" "$INPUTS" "$CRUN" 2>/dev/null||true; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR

say "=== $JASS_JOB_ID — L3-PURE C1-Q1 contract-complete verdict v2 ==="
[ "$FULL_RUN_APPROVED" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
ACTUAL_SHA="$(git rev-parse HEAD)"; [ "$ACTUAL_SHA" = "$EXPECTED_CODE_SHA" ] || die "code SHA $ACTUAL_SHA != $EXPECTED_CODE_SHA"
[ "$NOPEN" -eq 300 ] || die "Q1 verdict requires NOPEN=300"
[ "$DEPTH" -eq 9 ] || die "Q1 common-search requires depth 9"
[ "$CONV_DEPTH" -eq 10 ] || die "Q1 conversion requires depth 10"
[ "$NATIVE_MOVETIME" = 0.1 ] || die "Q1 native-search requires 0.1 s/move"
[ "$SCREEN_DELTA" = 0.02 ] || die "Q1 conversion threshold is pre-registered at 0.02"
[ "$BOOTSTRAP_REPLICATES" -ge 10000 ] || die "paired bootstrap requires >=10000 replicates"
NPROC="$(nproc)"; [ "$NPROC" -ge 16 ] || die "need >=16 CPUs, got $NPROC"
FREE_MB="$(df -Pm "$JASS_RESULT_DIR"|awk 'NR==2{print $4}')"; [ "${FREE_MB:-0}" -ge 5000 ] || die "<5GiB free"
say "preflight: nproc=$NPROC free_mb=$FREE_MB common_gates=3x$((NOPEN*2)) native_gates=3x$((NOPEN*2)) conv=4cells-P1-P4 timeout=${SHARD_TIMEOUT}s"
monitor
python3 -m py_compile jobs/tools/fetch_result_files.py jobs/tools/fetch_t1bis_inputs.py \
  jobs/tools/run_jass_gate_bounded.py jobs/tools/conv_fixed_wdl.py \
  jobs/tools/aggregate_conv_shards.py jobs/tools/l3_q1_verdict.py \
  jobs/tools/split_stratified_fen.py
python3 jobs/tests/test_run_jass_gate.py > "$W/t-gate.log" 2>&1 || die "gate tests red"
python3 jobs/tests/test_conv_fixed_wdl.py > "$W/t-conv.log" 2>&1 || die "conv tests red"
python3 jobs/tests/test_aggregate_conv_shards.py > "$W/t-agg.log" 2>&1 || die "aggregate tests red"
python3 jobs/tests/test_l3_q1_verdict.py > "$W/t-verdict.log" 2>&1 || die "verdict tests red"

set_stage fetch-inputs
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$INPUTS" --report "$ART/verified-fixed-inputs.json" > "$W/fetch-inputs.log" 2>&1 || die "fixed inputs unavailable"
gunzip -c "$INPUTS/gen2.pjtw.gz" > "$W/gen2.pjtw"; cp "$INPUTS/gauge.fen" "$W/gauge.fen"
[ -s "$W/gen2.pjtw" ] && [ -s "$W/gauge.fen" ] || die "missing gen2/gauge"
declare -A SEARCH
for c in "${CELLS[@]}"; do
  d="$CRUN/$c"; mkdir -p "$d"
  python3 jobs/tools/fetch_result_files.py --prefix "${PREFIX[$c]}" \
    --file artefacts/g2.pjtw.gz=g2.pjtw.gz \
    --file artefacts/l3-pure-manifest.json=manifest.json \
    --out-dir "$d" --report "$ART/verified-$c.json" > "$W/fetch-$c.log" 2>&1 || die "$c result unavailable"
  python3 - "$d/manifest.json" "$ART/verified-$c.json" "$c" "${SRCJOB[$c]}" "$d/g2.pjtw.gz" <<'PY'
import hashlib,json,sys
man=json.loads(open(sys.argv[1]).read()); ver=json.loads(open(sys.argv[2]).read())
cell,job,g2=sys.argv[3],sys.argv[4],sys.argv[5]
if man.get('experiment')!='C1-Q1' or man.get('variant','').split('_')[0]!={'Q00':'Q00','Q10':'Q10','Q01':'Q01','Q11':'Q11'}[cell]:
    raise SystemExit(f'{cell}: manifest variant mismatch {man.get("variant")}')
if man.get('generations')!=2 or man.get('scientific_status')!='complete_generation_chain':
    raise SystemExit(f'{cell}: manifest not a complete 2-gen chain')
if ver.get('job_id')!=job: raise SystemExit(f'{cell}: source job mismatch {ver.get("job_id")}')
got=hashlib.sha256(open(g2,'rb').read()).hexdigest()
if man.get('champion_sha256',{}).get('g2.pjtw.gz')!=got:
    raise SystemExit(f'{cell}: g2 checksum differs from manifest')
print(f'{cell} verified')
PY
  SEARCH[$c]="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["search_params"])' "$d/manifest.json")"
  [ -n "${SEARCH[$c]}" ] || die "$c has no resolved search fingerprint"
  gunzip -c "$d/g2.pjtw.gz" > "$W/$c.pjtw"; [ -s "$W/$c.pjtw" ] || die "$c g2 empty"
done
COMMON_SEARCH="${SEARCH[Q00]}"
say "provenance OK: 4 C1-Q1 cells + 4 full fingerprints + gen2 defender + gauge"

set_stage build-8cf-and-32cf
for s in src/scan_eval.cpp src/search.cpp src/movegen.cpp; do
  git show "HEAD:$s" > "$W/exp-$(basename "$s")"; cmp -s "$s" "$W/exp-$(basename "$s")" || die "$s differs from pinned HEAD"; done
grep -q g_emasks src/scan_eval.cpp || die "scan_eval guard"; grep -q has_any_capture src/search.cpp || die "search guard"; grep -q has_any_capture src/movegen.cpp || die "movegen guard"
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl > "$W/clone.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || die "EGDB unavailable"; export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen-8cf.log" 2>&1
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake-8cf.log" 2>&1; grep -q 'EXTERNAL EGDB ENABLED' "$W/cmake-8cf.log" || die "8cf no EGDB"
cmake --build "$W/build8" -j"$JASS_BUILD_JOBS" --target jass > "$W/build-8cf.log" 2>&1 || die "8cf build"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 > "$W/gen-32cf.log" 2>&1
cmake -S . -B "$W/build32" $FLAGS > "$W/cmake-32cf.log" 2>&1; grep -q 'EXTERNAL EGDB ENABLED' "$W/cmake-32cf.log" || die "32cf no EGDB"
cmake --build "$W/build32" -j"$JASS_BUILD_JOBS" --target jass > "$W/build-32cf.log" 2>&1 || die "32cf build"
J8="$W/build8/jass"; J32="$W/build32/jass"
python3 jobs/tools/cache_guard.py --cache-mb "$CACHE_MB" --procs 45 > "$ART/cache-gates.json" || die "gate cache guard"
python3 jobs/tools/cache_guard.py --cache-mb "$CACHE_MB" --procs 24 > "$ART/cache-conv.json" || die "conv cache guard"
awk -v limit="$NOPEN" '/^[[:space:]]*#/ {next} {sub(/#.*/,""); if(NF){print; n++; if(n>=limit) exit}}' data/dilf_combinations.fen > "$W/open.fen"
[ "$(wc -l < "$W/open.fen")" -eq "$NOPEN" ] || die "not enough fixed openings ($NOPEN)"

# --- common-search gates: each non-baseline cell vs Q00 (8cf both sides, same search) ---
set_stage common-search-gates
declare -A GPID
for c in Q10 Q01 Q11; do
  timeout 14400 python3 jobs/tools/run_jass_gate_bounded.py --jass "$J8" \
    --pattern-a "$W/$c.pjtw" --pattern-b "$W/Q00.pjtw" --openings-file "$W/open.fen" \
    --search-params-a "$COMMON_SEARCH" --search-params-b "$COMMON_SEARCH" \
    --depth "$DEPTH" --pairs 1 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout "$SHARD_TIMEOUT" --work-dir "$W/gate-common-$c" \
    --out "$ART/gate-common-$c-vs-Q00.json" > "$W/gate-common-$c.log" 2>&1 & GPID[$c]=$!
done
run_pids "common-search gates" "${GPID[@]}"

# --- native-search gates: each cell keeps its own 63-key fingerprint, equal time ---
set_stage native-equal-time-gates
unset GPID
declare -A GPID
for c in Q10 Q01 Q11; do
  timeout 21600 python3 jobs/tools/run_jass_gate_bounded.py --jass "$J8" \
    --pattern-a "$W/$c.pjtw" --pattern-b "$W/Q00.pjtw" --openings-file "$W/open.fen" \
    --search-params-a "${SEARCH[$c]}" --search-params-b "${SEARCH[Q00]}" \
    --movetime "$NATIVE_MOVETIME" --pairs 1 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout "$SHARD_TIMEOUT" --work-dir "$W/gate-native-$c" \
    --out "$ART/gate-native-$c-vs-Q00.json" > "$W/gate-native-$c.log" 2>&1 & GPID[$c]=$!
done
run_pids "native equal-time gates" "${GPID[@]}"

# --- conversion P1-P4 for all 4 cells (fixed gen2 defender) ---
set_stage conversion-p1-p4
python3 jobs/tools/split_stratified_fen.py --input "$W/gauge.fen" --out-dir "$W/strata" --manifest "$ART/gauge-strata.json" > "$W/split-gauge.log" 2>&1
mkdir -p "$ART/conversion"
run_conv(){ local model="$1" pattern="$2" stratum="$3" pool="$4" expected="$5"; local -a pids=() inputs=(); local shard out
  for shard in $(seq 0 $((NSH_CONV-1))); do out="$W/${model}.${stratum}.conv.${shard}.json"; inputs+=("$out")
    timeout "$SHARD_TIMEOUT" python3 jobs/tools/conv_fixed_wdl.py --jass "$J8" --defender-jass "$J32" \
      --pattern "$pattern" --defender-pattern "$W/gen2.pjtw" --pool-jnnw "$pool" \
      --search-params "$COMMON_SEARCH" --defender-search-params "$COMMON_SEARCH" \
      --depth "$CONV_DEPTH" --max-plies 260 --shard "$shard" --nshards "$NSH_CONV" --out "$out" \
      > "$W/${model}.${stratum}.conv.${shard}.log" 2>&1 & pids+=("$!")
    if [ "${#pids[@]}" -ge "$PAR_CONV" ]; then run_pids "$model $stratum batch" "${pids[@]}"; pids=(); fi
  done
  run_pids "$model $stratum" "${pids[@]}"
  python3 jobs/tools/aggregate_conv_shards.py --inputs "${inputs[@]}" --expected-shards "$NSH_CONV" \
    --expected-records "$expected" --max-error-rate 0.08 --stratum "$stratum" \
    --require-position-results \
    --out "$ART/conversion/${model}-${stratum}.json" > "$W/${model}.${stratum}.agg.log" 2>&1; }
for stratum in p1_net p2_moyen p3_mince p4_egal; do
  python3 jobs/tools/jnnw_doe.py fen-to-jnnw --input "$W/strata/$stratum.fen" --output "$W/$stratum.raw.jnnw" >/dev/null
  "$J32" --deep-relabel "$W/$stratum.raw.jnnw" "$W/$stratum.rel.jnnw" "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb "$CACHE_MB" > "$W/$stratum.relabel.log" 2>&1
  python3 jobs/tools/jnnw_doe.py keep-decisive --input "$W/$stratum.rel.jnnw" --output "$W/$stratum.dec.jnnw" >/dev/null
  EXP="$(jnnw_count "$W/$stratum.dec.jnnw")"; [ "$EXP" -gt 0 ] || die "$stratum no decisive positions"
  cpids=(); for c in "${CELLS[@]}"; do run_conv "$c" "$W/$c.pjtw" "$stratum" "$W/$stratum.dec.jnnw" "$EXP" & cpids+=("$!"); done
  run_pids "conversion $stratum" "${cpids[@]}"
done

set_stage aggregate-verdict
python3 - "$ART/q1-verdict-spec.json" "$CRUN" "$BOOTSTRAP_REPLICATES" "$SCREEN_DELTA" <<'PY'
import json,sys
from pathlib import Path
out, cells_root = Path(sys.argv[1]), Path(sys.argv[2])
replicates, threshold = int(sys.argv[3]), float(sys.argv[4])
cells = ('Q00','Q10','Q01','Q11')
strata = ('p1_net','p2_moyen','p3_mince','p4_egal')
search = {
    cell: json.loads((cells_root/cell/'manifest.json').read_text())['search_params']
    for cell in cells
}
cell_specs = {}
for cell in cells:
    item = {
        'search_params': search[cell],
        'conversion': {
            stratum: f'conversion/{cell}-{stratum}.json' for stratum in strata
        },
    }
    if cell != 'Q00':
        item['common_gate'] = f'gate-common-{cell}-vs-Q00.json'
        item['native_gate'] = f'gate-native-{cell}-vs-Q00.json'
    cell_specs[cell] = item
payload = {
    'schema': 2,
    'experiment': 'L3-PURE-C1-Q1',
    'baseline': 'Q00',
    'common_search_params': search['Q00'],
    'conversion_delta_threshold': threshold,
    'bootstrap': {'method': 'paired_position', 'replicates': replicates, 'seed': 271828},
    'cells': cell_specs,
    'automatic_next_job': None,
}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8')
PY
python3 jobs/tools/l3_q1_verdict.py --spec "$ART/q1-verdict-spec.json" \
  --out "$ART/c1q1-verdict.json" > "$W/verdict.log" 2>&1 \
  || die "contract-complete Q1 verdict invalid"
cat "$ART/c1q1-verdict.json" | tee -a "$RES"
set_stage complete
say "=== C1-Q1 verdict complete; no Q2 job was launched ==="
