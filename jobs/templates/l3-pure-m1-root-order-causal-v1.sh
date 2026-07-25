#!/usr/bin/env bash
# 0961: causal replay of native Scan root ordering inside exact Jass.
# Diagnostic only: no training, promotion or automatic continuation.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${GAUGE_PREFIX:?}"; : "${CAUSAL_PREFIX:?}"; : "${SEMANTICS_PREFIX:?}"
: "${ROOT_TRACE_PREFIX:?}"; : "${SCAN_BIN:?}"; : "${SCAN_SOURCE_BUNDLE:?}"
: "${EXPECTED_SCAN_SHA256:?}"; : "${EXPECTED_SCAN_RUNTIME_SHA256:?}"
: "${EXPECTED_SCAN_EVAL_SHA256:?}"; : "${EXPECTED_SCAN_BUNDLE_SHA256:?}"
: "${EXPECTED_SCAN_SOURCE_COMMIT:?}"; : "${EXPECTED_EXACT_PJTW_SHA256:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; IN="$JASS_RESULT_DIR/inputs"
mkdir -p "$W" "$ART" "$IN" "$ART/replay" "$ART/conversion" "$W/source-traces" "$W/native-traces"
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
  rm -rf "$W/build8-exact" "$W/build32" "$W/baseline-code" "$W/scan-source" "$IN"
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM

STRATA=(p3_mince p4_egal)
NSHARDS=4
REPLAY_SHARDS=8
TARGET_PER_STRATUM=300
DEPTH=10
DEFENDER_DEPTH=10
MAX_PLIES=260
BOOTSTRAP_SAMPLES=200000
READOUT_SEED=961101
CACHE_MB=128
BASELINE_CODE_SHA="5f151c248cf1611c1d6695a1275d01a91fb9b424"
PATCH="jobs/patches/scan-0960-root-trace.patch"
P3_GAUGE_SHA="cd92710fec7934d113ccade22180d4cddf029b084dd20c8fa9e30ca686767c91"
P4_GAUGE_SHA="0d925c4fbd7e7928bf6d86bd2cd40f796ee6805e0010e51d5d6483986da2a1ac"

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${ROOT_ORDER_CAUSAL_GO:-0}" = 1 ] || die "root-order authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"
[ -f "$PATCH" ] || die "Scan trace patch missing"
monitor

stage local-contract-tests
python3 -m py_compile \
  jobs/tools/l3_root_order_oracle.py \
  jobs/tools/l3_root_order_replay.py \
  jobs/tools/l3_root_order_causal_report.py \
  jobs/tools/conv_fixed_wdl.py \
  jobs/tools/aggregate_conv_shards.py
python3 -m unittest \
  jobs.tests.test_l3_root_order_causal \
  jobs.tests.test_l3_internal_root_trace \
  jobs.tests.test_l3_scan_semantics_audit \
  > "$W/test-root-order.log" 2>&1

jnnw_count(){ python3 - "$1" <<'PY'
import struct,sys
raw=open(sys.argv[1],"rb").read(8)
if len(raw)!=8 or raw[:4]!=b"JNNW": raise SystemExit("invalid JNNW")
print(struct.unpack("<I",raw[4:])[0])
PY
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

stage fetch-and-verify-immutable-inputs
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$IN" \
  --report "$ART/verified-fixed-inputs.json" > "$W/fetch-fixed.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$GAUGE_PREFIX" \
  --file artefacts/p3_mince-stable.jnnw.gz=p3.jnnw.gz \
  --file artefacts/p4_egal-stable.jnnw.gz=p4.jnnw.gz \
  --file artefacts/holdout-provenance.json=gauge-provenance.json \
  --out-dir "$IN" --report "$ART/verified-gauge.json" > "$W/fetch-gauge.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$CAUSAL_PREFIX" \
  --file artefacts/scan-exact-8cf.pjtw.gz=scan-exact.pjtw.gz \
  --file artefacts/scan-exact-port-manifest.json=scan-port-manifest.json \
  --out-dir "$IN" --report "$ART/verified-0957.json" > "$W/fetch-0957.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$SEMANTICS_PREFIX" \
  --file artefacts/scan-semantics-variant-manifest.json=variant-manifest.json \
  --file artefacts/conversion/SCAN_VERIFY_THREAT-D10-p3_mince.json=BASE-p3_mince.json \
  --file artefacts/conversion/SCAN_VERIFY_THREAT-D10-p4_egal.json=BASE-p4_egal.json \
  --out-dir "$IN" --report "$ART/verified-0959.json" > "$W/fetch-0959.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$ROOT_TRACE_PREFIX" \
  --file artefacts/search-tree-sentinels.json=search-tree-sentinels.json \
  --file artefacts/root-internal-traces.tar.gz=root-internal-traces.tar.gz \
  --file artefacts/root-internal-trace-audit.json=source-0960bis.json \
  --out-dir "$IN" --report "$ART/verified-0960bis.json" > "$W/fetch-0960bis.log" 2>&1

gunzip -c "$IN/gen2.pjtw.gz" > "$W/GEN2.pjtw"
gunzip -c "$IN/p3.jnnw.gz" > "$W/p3_mince.jnnw"
gunzip -c "$IN/p4.jnnw.gz" > "$W/p4_egal.jnnw"
gunzip -c "$IN/scan-exact.pjtw.gz" > "$W/SCAN_EXACT.pjtw"
tar -C "$W/source-traces" -xzf "$IN/root-internal-traces.tar.gz"
[ "$(sha256sum "$W/SCAN_EXACT.pjtw"|awk '{print $1}')" = "$EXPECTED_EXACT_PJTW_SHA256" ] ||
  die "exact Scan PJTW hash mismatch"
for spec in "p3_mince:$P3_GAUGE_SHA" "p4_egal:$P4_GAUGE_SHA"; do
  name="${spec%%:*}"; want="${spec#*:}"
  [ "$(sha256sum "$W/$name.jnnw"|awk '{print $1}')" = "$want" ] ||
    die "$name gauge hash mismatch"
  [ "$(jnnw_count "$W/$name.jnnw")" -eq "$TARGET_PER_STRATUM" ] ||
    die "$name gauge count mismatch"
done
python3 - "$IN" "$W/SCAN_VERIFY_THREAT.txt" "$W/Q00.txt" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1])
source=json.loads((root/"source-0960bis.json").read_text())
if source.get("localization",{}).get("verdict")!="ROOT_ORDERING_SELECTIVITY_DIVERGENCE":
    raise SystemExit("0960bis verdict mismatch")
if len(json.loads((root/"search-tree-sentinels.json").read_text()).get("sentinels",[]))!=48:
    raise SystemExit("0960bis sentinel count mismatch")
variants=json.loads((root/"variant-manifest.json").read_text())
spec=variants["arms"]["SCAN_VERIFY_THREAT"]["search_params"]
base=json.loads((root/"BASE-p3_mince.json").read_text())
q00=base["defender_search_params"]
if len(spec.split(","))!=65 or len(q00.split(","))!=63:
    raise SystemExit("search fingerprint mismatch")
Path(sys.argv[2]).write_text(spec+"\n")
Path(sys.argv[3]).write_text(q00+"\n")
PY
cp "$IN/search-tree-sentinels.json" "$ART/search-tree-sentinels.json"
cp "$IN/source-0960bis.json" "$ART/source-0960bis.json"
cp "$IN/scan-port-manifest.json" "$ART/scan-exact-port-manifest.json"
cp "$IN/gauge-provenance.json" "$ART/corrected-gauge-provenance.json"
for stratum in "${STRATA[@]}"; do
  cp "$IN/BASE-$stratum.json" "$ART/conversion/BASE-$stratum.json"
done

stage build-instrumented-native-scan
git clone -q "$SCAN_SOURCE_BUNDLE" "$W/scan-source"
[ "$(git -C "$W/scan-source" rev-parse HEAD)" = "$EXPECTED_SCAN_SOURCE_COMMIT" ] ||
  die "Scan source commit mismatch"
git -C "$W/scan-source" apply --check "$JASS_CODE_DIR/$PATCH"
git -C "$W/scan-source" apply "$JASS_CODE_DIR/$PATCH"
git -C "$W/scan-source" diff --check
cp "$SCAN_DIR/scan.ini" "$W/scan-source/src/scan.ini"
mkdir -p "$W/scan-source/src/data"
cp "$SCAN_DIR/data/eval" "$W/scan-source/src/data/eval"
make -C "$W/scan-source/src" -j4 > "$W/build-scan-order.log" 2>&1
SCAN_TRACE="$W/scan-source/src/scan"
[ -x "$SCAN_TRACE" ] || die "instrumented Scan build missing"

stage build-exact-candidate-and-fixed-defender
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EXACT_FLAGS="$FLAGS -DJASS_DRAWISH_SCALING=ON -DJASS_SCAN_EXACT_EVAL=ON"
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
mkdir -p "$W/baseline-code"
git cat-file -e "$BASELINE_CODE_SHA^{commit}"
git archive "$BASELINE_CODE_SHA" | tar -x -C "$W/baseline-code"
python3 "$W/baseline-code/pattern_jass/tools/gen_patterns.py" \
  --emit --variant v4 > "$W/gen32.log" 2>&1
cmake -S "$W/baseline-code" -B "$W/build32" $FLAGS > "$W/cmake32.log" 2>&1
cmake --build "$W/build32" -j4 --target jass > "$W/build32.log" 2>&1
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cmake -S . -B "$W/build8-exact" $EXACT_FLAGS > "$W/cmake8.log" 2>&1
cmake --build "$W/build8-exact" -j4 --target jass > "$W/build8.log" 2>&1
cmake --build "$W/build8-exact" -j4 --target jass_tests > "$W/build8-tests.log" 2>&1
ctest --test-dir "$W/build8-exact" --output-on-failure > "$W/ctest8.log" 2>&1
J8X="$W/build8-exact/jass"; J32="$W/build32/jass"
[ "$("$J8X" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "equivalent king-capture paths were not deduplicated"
[ "$("$J8X" --perft 1 'B:W13,23,25:B6,14,24,K45' | awk '{print $3}')" = 2 ] ||
  die "tablebase-draw witness legal moves mismatch"

export SCAN_TRACE_ROOT=1
stage native-repaired-sentinel-trace
pids=()
for shard in $(seq 0 $((REPLAY_SHARDS-1))); do
  timeout 7200 python3 jobs/tools/l3_internal_root_trace.py \
    --sentinels "$ART/search-tree-sentinels.json" \
    --jass "$J8X" --pattern "$W/SCAN_EXACT.pjtw" \
    --search-params-file "$W/SCAN_VERIFY_THREAT.txt" \
    --scan "$SCAN_TRACE" \
    --shard "$shard" --nshards "$REPLAY_SHARDS" \
    --out "$W/native-traces/root-trace-s${shard}.json" \
    > "$W/native-trace-s${shard}.log" 2>&1 & pids+=("$!")
done
fail=0
for pid in "${pids[@]}"; do wait "$pid" || fail=$((fail+1)); done
[ "$fail" -eq 0 ] || die "$fail native repaired trace workers failed"

stage sentinel-root-order-replay
pids=()
for shard in $(seq 0 $((REPLAY_SHARDS-1))); do
  timeout 7200 python3 jobs/tools/l3_root_order_replay.py \
    --sentinels "$ART/search-tree-sentinels.json" \
    --jass "$J8X" --pattern "$W/SCAN_EXACT.pjtw" \
    --search-params-file "$W/SCAN_VERIFY_THREAT.txt" \
    --scan "$SCAN_TRACE" --depth 12 \
    --shard "$shard" --nshards "$REPLAY_SHARDS" \
    --out "$ART/replay/root-order-s${shard}.json" \
    > "$W/replay-s${shard}.log" 2>&1 & pids+=("$!")
done
fail=0
for pid in "${pids[@]}"; do wait "$pid" || fail=$((fail+1)); done
[ "$fail" -eq 0 ] || die "$fail sentinel replay workers failed"

stage full-gauge-root-order-conversion
for arm in NATIVE_REPAIRED ROOT_ORDER; do
  for stratum in "${STRATA[@]}"; do
    pids=(); inputs=(); root_args=()
    [ "$arm" != ROOT_ORDER ] || root_args=(--root-order-scan "$SCAN_TRACE")
    for shard in $(seq 0 $((NSHARDS-1))); do
      out="$W/$arm-$stratum-s${shard}.json"; inputs+=("$out")
      timeout 18000 python3 jobs/tools/conv_fixed_wdl.py \
        --jass "$J8X" --defender-jass "$J32" \
        --pattern "$W/SCAN_EXACT.pjtw" --defender-pattern "$W/GEN2.pjtw" \
        --search-params "$(cat "$W/SCAN_VERIFY_THREAT.txt")" \
        --defender-search-params "$(cat "$W/Q00.txt")" \
        "${root_args[@]}" \
        --pool-jnnw "$W/$stratum.jnnw" \
        --depth "$DEPTH" --defender-depth "$DEFENDER_DEPTH" \
        --max-plies "$MAX_PLIES" --shard "$shard" --nshards "$NSHARDS" \
        --out "$out" > "$W/$arm-$stratum-s${shard}.log" 2>&1 &
      pids+=("$!")
    done
    fail=0
    for pid in "${pids[@]}"; do wait "$pid" || fail=$((fail+1)); done
    [ "$fail" -eq 0 ] || die "$arm/$stratum: $fail conversion workers failed"
    python3 jobs/tools/aggregate_conv_shards.py \
      --inputs "${inputs[@]}" --expected-shards "$NSHARDS" \
      --expected-records "$TARGET_PER_STRATUM" --max-error-rate 0.02 \
      --stratum "$stratum" --require-position-results \
      --out "$ART/conversion/$arm-$stratum.json" \
      > "$W/aggregate-$arm-$stratum.log" 2>&1
  done
done

stage causal-root-order-readout
mapfile -t source_traces < <(find "$W/native-traces" -name 'root-trace-s*.json' -print | sort)
mapfile -t replay_inputs < <(find "$ART/replay" -name 'root-order-s*.json' -print | sort)
[ "${#source_traces[@]}" -eq 8 ] || die "missing 0960bis source traces"
[ "${#replay_inputs[@]}" -eq "$REPLAY_SHARDS" ] || die "missing 0961 replay traces"
python3 jobs/tools/l3_root_order_causal_report.py \
  --sentinels "$ART/search-tree-sentinels.json" \
  --source-traces "${source_traces[@]}" \
  --replay-inputs "${replay_inputs[@]}" \
  --conversion-dir "$ART/conversion" --strata "${STRATA[@]}" \
  --bootstrap-samples "$BOOTSTRAP_SAMPLES" --seed "$READOUT_SEED" \
  --out "$ART/root-order-causal-audit.json" \
  --summary-out "$ART/JASS_CONTROL_SUMMARY.json" | tee -a "$RES"
VERDICT="$(python3 - "$ART/JASS_CONTROL_SUMMARY.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["verdict"])
PY
)"
tar -C "$ART/replay" -czf "$ART/root-order-replay-traces.tar.gz" .
printf '%s\n' "$VERDICT" > "$ART/VERDICT__$VERDICT"
printf '%s\n' TRAINING_AUTHORIZED__FALSE > "$ART/TRAINING_AUTHORIZED__FALSE"
printf '%s\n' PROMOTION_AUTHORIZED__FALSE > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf '%s\n' AUTOMATIC_NEXT_JOB__NULL > "$ART/AUTOMATIC_NEXT_JOB__NULL"
stage complete
say "ROOT_ORDER_CAUSAL_READY verdict=$VERDICT training=false promotion=false"
