#!/usr/bin/env bash
# 0958: exact-Scan-eval search intervention and paired root-trace audit.
# Diagnostic only: no training, promotion or automatic continuation.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${GAUGE_PREFIX:?}"; : "${CAUSAL_PREFIX:?}"
: "${SCAN_BIN:?}"; : "${SCAN_SOURCE_BUNDLE:?}"
: "${EXPECTED_SCAN_SHA256:?}"; : "${EXPECTED_SCAN_RUNTIME_SHA256:?}"
: "${EXPECTED_SCAN_EVAL_SHA256:?}"; : "${EXPECTED_SCAN_BUNDLE_SHA256:?}"
: "${EXPECTED_SCAN_SOURCE_COMMIT:?}"; : "${EXPECTED_EXACT_PJTW_SHA256:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; IN="$JASS_RESULT_DIR/inputs"
mkdir -p "$W" "$ART" "$IN" "$ART/conversion" "$ART/traces" "$W/params"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/stage.txt"
: > "$RES"; echo preflight > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "stage=$1"; }
MON=""
monitor(){
  (while true; do
    { date -Is; printf 'stage=%s\n' "$(cat "$STAGE")"; } > "$PROG.tmp"
    mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 60
  done) & MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || kill "$MON" 2>/dev/null
  cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -name '*.log' -type f -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build8-exact" "$W/build32" "$W/scan-source" "$IN"
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM

STRATA=(p3_mince p4_egal)
ARMS=(NO_FORWARD SCAN_EXT_QS SCAN_LMR FULL_WIDTH)
CONV_NSHARDS=4; TRACE_NSHARDS=8; PAR_CELL_GROUPS=2
TARGET_PER_STRATUM=300; DEPTH=10; DEFENDER_DEPTH=10; MAX_PLIES=260
TRACE_DEPTHS="8,10,12"; BOOTSTRAP_SAMPLES=200000; READOUT_SEED=958101
CACHE_MB=128
P3_GAUGE_SHA="cd92710fec7934d113ccade22180d4cddf029b084dd20c8fa9e30ca686767c91"
P4_GAUGE_SHA="0d925c4fbd7e7928bf6d86bd2cd40f796ee6805e0010e51d5d6483986da2a1ac"

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${SEARCH_AUDIT_GO:-0}" = 1 ] || die "search-audit authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"
monitor

stage local-contract-tests
python3 -m py_compile \
  jobs/tools/l3_search_variants.py \
  jobs/tools/l3_search_tree_select.py \
  jobs/tools/l3_search_tree_replay.py \
  jobs/tools/l3_search_tree_report.py
python3 -m unittest \
  jobs.tests.test_l3_search_tree_audit \
  jobs.tests.test_l3_pure_m1_search_tree_audit \
  > "$W/test-search-tree-audit.log" 2>&1

jnnw_count(){ python3 - "$1" <<'PY'
import struct,sys
raw=open(sys.argv[1],"rb").read(8)
if len(raw)!=8 or raw[:4]!=b"JNNW":
    raise SystemExit("invalid JNNW")
print(struct.unpack("<I",raw[4:])[0])
PY
}
wait_all(){
  local label="$1"; shift; local fail=0 pid
  for pid in "$@"; do wait "$pid" || fail=$((fail+1)); done
  [ "$fail" -eq 0 ] || die "$label: $fail workers failed"
}

stage verify-pinned-scan-runtime-and-source
[ -x "$SCAN_BIN" ] || die "Scan binary missing"
[ -f "$SCAN_SOURCE_BUNDLE" ] || die "Scan source bundle missing"
[ "$(sha256sum "$SCAN_BIN"|awk '{print $1}')" = "$EXPECTED_SCAN_SHA256" ] ||
  die "Scan binary hash mismatch"
[ "$(sha256sum "$SCAN_SOURCE_BUNDLE"|awk '{print $1}')" = "$EXPECTED_SCAN_BUNDLE_SHA256" ] ||
  die "Scan source bundle hash mismatch"
SCAN_DIR="$(dirname "$(readlink -f "$SCAN_BIN")")"
[ "$(sha256sum "$SCAN_DIR/data/eval"|awk '{print $1}')" = "$EXPECTED_SCAN_EVAL_SHA256" ] ||
  die "Scan data/eval hash mismatch"
RUNTIME_SHA="$(python3 jobs/tools/scan_runtime_fingerprint.py \
  --scan-dir "$SCAN_DIR" --output "$ART/scan-runtime-manifest.json")"
[ "$RUNTIME_SHA" = "$EXPECTED_SCAN_RUNTIME_SHA256" ] ||
  die "Scan runtime fingerprint mismatch"

stage fetch-immutable-0957-gauge-and-models
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$IN" \
  --report "$ART/verified-fixed-inputs.json" > "$W/fetch-fixed.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$GAUGE_PREFIX" \
  --file artefacts/p3_mince-stable.jnnw.gz=p3.jnnw.gz \
  --file artefacts/p4_egal-stable.jnnw.gz=p4.jnnw.gz \
  --file artefacts/holdout-provenance.json=gauge-provenance.json \
  --out-dir "$IN" --report "$ART/verified-gauge.json" > "$W/fetch-gauge.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$CAUSAL_PREFIX" \
  --file artefacts/scan-gap-causal-readout.json=source-0957.json \
  --file artefacts/scan-exact-8cf.pjtw.gz=scan-exact.pjtw.gz \
  --file artefacts/scan-exact-port-manifest.json=scan-port-manifest.json \
  --file artefacts/scan-static-parity.json=source-static-parity.json \
  --file artefacts/conversion/SCAN_EXACT_D10-p3_mince.json=Q00-p3_mince.json \
  --file artefacts/conversion/SCAN_EXACT_D10-p4_egal.json=Q00-p4_egal.json \
  --file artefacts/conversion/SCAN_EXACT_D12-p3_mince.json=EXACT_D12-p3_mince.json \
  --file artefacts/conversion/SCAN_EXACT_D12-p4_egal.json=EXACT_D12-p4_egal.json \
  --file artefacts/conversion/SCAN_NATIVE_D10-p3_mince.json=NATIVE_D10-p3_mince.json \
  --file artefacts/conversion/SCAN_NATIVE_D10-p4_egal.json=NATIVE_D10-p4_egal.json \
  --file artefacts/conversion/SCAN_NATIVE_D12-p3_mince.json=NATIVE_D12-p3_mince.json \
  --file artefacts/conversion/SCAN_NATIVE_D12-p4_egal.json=NATIVE_D12-p4_egal.json \
  --out-dir "$IN" --report "$ART/verified-0957.json" > "$W/fetch-0957.log" 2>&1

gunzip -c "$IN/gen2.pjtw.gz" > "$W/GEN2.pjtw"
gunzip -c "$IN/p3.jnnw.gz" > "$W/p3_mince.jnnw"
gunzip -c "$IN/p4.jnnw.gz" > "$W/p4_egal.jnnw"
gunzip -c "$IN/scan-exact.pjtw.gz" > "$W/SCAN_EXACT.pjtw"
cp "$IN/source-0957.json" "$ART/source-0957.json"
cp "$IN/scan-port-manifest.json" "$ART/scan-exact-port-manifest.json"
cp "$IN/source-static-parity.json" "$ART/source-0957-static-parity.json"
cp "$IN/gauge-provenance.json" "$ART/corrected-gauge-provenance.json"
for stratum in "${STRATA[@]}"; do
  cp "$IN/Q00-$stratum.json" "$ART/conversion/Q00-$stratum.json"
  cp "$IN/NATIVE_D10-$stratum.json" "$ART/conversion/SCAN_NATIVE-$stratum.json"
done

[ "$(sha256sum "$W/SCAN_EXACT.pjtw"|awk '{print $1}')" = "$EXPECTED_EXACT_PJTW_SHA256" ] ||
  die "exact Scan PJTW hash mismatch"
for spec in "p3_mince:$P3_GAUGE_SHA" "p4_egal:$P4_GAUGE_SHA"; do
  name="${spec%%:*}"; want="${spec#*:}"
  [ "$(sha256sum "$W/$name.jnnw"|awk '{print $1}')" = "$want" ] ||
    die "$name gauge hash mismatch"
  [ "$(jnnw_count "$W/$name.jnnw")" -eq "$TARGET_PER_STRATUM" ] ||
    die "$name gauge count mismatch"
done
python3 - "$IN" "$W/Q00.txt" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1])
docs=[json.loads((root/f"Q00-{s}.json").read_text()) for s in ("p3_mince","p4_egal")]
src=json.loads((root/"source-0957.json").read_text())
parity=json.loads((root/"source-static-parity.json").read_text())
if src.get("verdict")!="SCAN_GAP_CAUSAL_READOUT_READY_HUMAN_REVIEW":
    raise SystemExit("0957 verdict mismatch")
if src.get("localization",{}).get("verdict")!="SEARCH_IMPLEMENTATION_DOMINANT":
    raise SystemExit("0957 localization mismatch")
if parity.get("verdict")!="SCAN_STATIC_PORT_EXACT" or parity.get("comparison",{}).get("max_abs_delta")!=0:
    raise SystemExit("0957 exact static parity proof missing")
params={d.get("search_params") for d in docs}
defender={d.get("defender_search_params") for d in docs}
if len(params)!=1 or params!=defender:
    raise SystemExit("Q00 candidate/defender fingerprint mismatch")
q00=params.pop()
if not isinstance(q00,str) or len(q00.split(","))!=63:
    raise SystemExit("Q00 is not fully resolved")
Path(sys.argv[2]).write_text(q00+"\n")
PY
python3 jobs/tools/l3_search_variants.py --base-file "$W/Q00.txt" \
  --out-dir "$W/params" --manifest "$ART/search-variant-manifest.json" \
  > "$W/search-variants.log" 2>&1
Q00="$(cat "$W/Q00.txt")"

stage build-exact-candidate-and-fixed-defender
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EXACT_FLAGS="$FLAGS -DJASS_DRAWISH_SCALING=ON -DJASS_SCAN_EXACT_EVAL=ON"
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cmake -S . -B "$W/build8-exact" $EXACT_FLAGS > "$W/cmake8-exact.log" 2>&1
cmake --build "$W/build8-exact" -j4 --target jass > "$W/build8-exact.log" 2>&1
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 > "$W/gen32.log" 2>&1
cmake -S . -B "$W/build32" $FLAGS > "$W/cmake32.log" 2>&1
cmake --build "$W/build32" -j4 --target jass > "$W/build32.log" 2>&1
J8X="$W/build8-exact/jass"; J32="$W/build32/jass"

stage repeat-static-parity-gate
git clone -q "$SCAN_SOURCE_BUNDLE" "$W/scan-source"
[ "$(git -C "$W/scan-source" rev-parse HEAD)" = "$EXPECTED_SCAN_SOURCE_COMMIT" ] ||
  die "Scan source commit mismatch"
cp "$SCAN_DIR/scan.ini" "$W/scan-source/scan.ini"
cp "$SCAN_DIR/data/eval" "$W/scan-source/data/eval"
SCAN_CPP=()
for src in "$W/scan-source"/src/*.cpp; do
  [ "$(basename "$src")" = main.cpp ] || SCAN_CPP+=("$src")
done
g++ -std=c++14 -O2 -mpopcnt -pthread -I"$W/scan-source/src" \
  jobs/tools/scan_static_probe.cpp "${SCAN_CPP[@]}" \
  -o "$W/scan-static-probe" > "$W/scan-probe-build.log" 2>&1
python3 jobs/tools/scan_static_parity.py \
  --pool-jnnw "$W/p3_mince.jnnw" --pool-jnnw "$W/p4_egal.jnnw" \
  --limit-per-pool 0 --scan-probe "$W/scan-static-probe" \
  --scan-cwd "$W/scan-source" --jass "$J8X" --pjtw "$W/SCAN_EXACT.pjtw" \
  --workers 4 --max-abs-diff 0 --out "$ART/scan-static-parity.json" \
  > "$W/static-parity.log" 2>&1

stage select-balanced-discordant-sentinels
python3 jobs/tools/l3_search_tree_select.py --strata "${STRATA[@]}" \
  --pool-jnnw "$W/p3_mince.jnnw" --pool-jnnw "$W/p4_egal.jnnw" \
  --jass-exact-d12 "$IN/EXACT_D12-p3_mince.json" \
  --jass-exact-d12 "$IN/EXACT_D12-p4_egal.json" \
  --scan-native-d12 "$IN/NATIVE_D12-p3_mince.json" \
  --scan-native-d12 "$IN/NATIVE_D12-p4_egal.json" \
  --failures-per-side 8 --controls-per-side 4 --seed 958001 \
  --out "$ART/search-tree-sentinels.json" > "$W/select.log" 2>&1

run_cell(){
  local arm="$1" params="$2" stratum="$3" pool="$4"
  local pids=() inputs=() shard out
  for shard in $(seq 0 $((CONV_NSHARDS-1))); do
    out="$W/$arm-$stratum-$shard.json"; inputs+=("$out")
    timeout 21600 python3 jobs/tools/conv_fixed_wdl.py \
      --jass "$J8X" --defender-jass "$J32" \
      --pattern "$W/SCAN_EXACT.pjtw" --defender-pattern "$W/GEN2.pjtw" \
      --search-params "$params" --defender-search-params "$Q00" \
      --pool-jnnw "$pool" --depth "$DEPTH" --defender-depth "$DEFENDER_DEPTH" \
      --max-plies "$MAX_PLIES" --shard "$shard" --nshards "$CONV_NSHARDS" \
      --out "$out" > "$W/$arm-$stratum-$shard.log" 2>&1 & pids+=("$!")
  done
  wait_all "$arm/$stratum" "${pids[@]}"
  python3 jobs/tools/aggregate_conv_shards.py --inputs "${inputs[@]}" \
    --expected-shards "$CONV_NSHARDS" --expected-records "$TARGET_PER_STRATUM" \
    --max-error-rate 0.02 --stratum "$stratum" --require-position-results \
    --out "$ART/conversion/$arm-$stratum.json" \
    > "$W/$arm-$stratum-aggregate.log" 2>&1
}

stage full-gauge-search-interventions
for stratum in "${STRATA[@]}"; do
  pids=()
  for arm in "${ARMS[@]}"; do
    params="$(cat "$W/params/$arm.txt")"
    run_cell "$arm" "$params" "$stratum" "$W/$stratum.jnnw" & pids+=("$!")
    if [ "${#pids[@]}" -ge "$PAR_CELL_GROUPS" ]; then
      wait_all "$stratum arm batch" "${pids[@]}"; pids=()
    fi
  done
  [ "${#pids[@]}" -eq 0 ] || wait_all "$stratum arm batch" "${pids[@]}"
done

stage paired-multidepth-root-traces
pids=()
for shard in $(seq 0 $((TRACE_NSHARDS-1))); do
  timeout 21600 python3 jobs/tools/l3_search_tree_replay.py \
    --sentinels "$ART/search-tree-sentinels.json" \
    --variants "$ART/search-variant-manifest.json" \
    --jass "$J8X" --pattern "$W/SCAN_EXACT.pjtw" --scan "$SCAN_BIN" \
    --depths "$TRACE_DEPTHS" --shard "$shard" --nshards "$TRACE_NSHARDS" \
    --out "$ART/traces/replay-s${shard}.json" \
    > "$W/replay-s${shard}.log" 2>&1 & pids+=("$!")
done
wait_all "root traces" "${pids[@]}"
mapfile -t replay_inputs < <(find "$ART/traces" -name 'replay-s*.json' -print | sort)
[ "${#replay_inputs[@]}" -eq "$TRACE_NSHARDS" ] || die "missing replay shards"
tar -C "$ART/traces" -czf "$ART/search-tree-traces.tar.gz" .

stage aggregate-search-tree-readout
python3 jobs/tools/l3_search_tree_report.py \
  --sentinels "$ART/search-tree-sentinels.json" \
  --replay-inputs "${replay_inputs[@]}" --conversion-dir "$ART/conversion" \
  --strata "${STRATA[@]}" --bootstrap-samples "$BOOTSTRAP_SAMPLES" \
  --seed "$READOUT_SEED" --out "$ART/search-tree-audit.json" \
  --summary-out "$ART/JASS_CONTROL_SUMMARY.json" | tee -a "$RES"
printf '%s\n' SEARCH_TREE_AUDIT_READY_HUMAN_REVIEW \
  > "$ART/VERDICT__SEARCH_TREE_AUDIT_READY_HUMAN_REVIEW"
printf '%s\n' TRAINING_AUTHORIZED__FALSE > "$ART/TRAINING_AUTHORIZED__FALSE"
printf '%s\n' PROMOTION_AUTHORIZED__FALSE > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf '%s\n' AUTOMATIC_NEXT_JOB__NULL > "$ART/AUTOMATIC_NEXT_JOB__NULL"
stage complete
say "SEARCH_TREE_AUDIT_READY_HUMAN_REVIEW training=false promotion=false"
