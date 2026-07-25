#!/usr/bin/env bash
# 0960: first-divergence root trace between native Scan and exact Jass.
# Diagnostic only: no training, promotion or automatic continuation.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${CAUSAL_PREFIX:?}"; : "${SEMANTICS_PREFIX:?}"
: "${SCAN_BIN:?}"; : "${SCAN_SOURCE_BUNDLE:?}"
: "${EXPECTED_SCAN_SHA256:?}"; : "${EXPECTED_SCAN_RUNTIME_SHA256:?}"
: "${EXPECTED_SCAN_EVAL_SHA256:?}"; : "${EXPECTED_SCAN_BUNDLE_SHA256:?}"
: "${EXPECTED_SCAN_SOURCE_COMMIT:?}"; : "${EXPECTED_EXACT_PJTW_SHA256:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; IN="$JASS_RESULT_DIR/inputs"
mkdir -p "$W" "$ART" "$IN" "$ART/traces"
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
  rm -rf "$W/build8-exact" "$W/scan-source" "$IN"
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM

NSHARDS=8
CACHE_MB=128
PATCH="jobs/patches/scan-0960-root-trace.patch"

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${ROOT_TRACE_GO:-0}" = 1 ] || die "root-trace authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"
[ -f "$PATCH" ] || die "Scan trace patch missing"
monitor

stage local-contract-tests
python3 -m py_compile \
  jobs/tools/l3_internal_root_trace.py \
  jobs/tools/l3_internal_root_trace_report.py
python3 -m unittest \
  jobs.tests.test_l3_internal_root_trace \
  jobs.tests.test_l3_scan_semantics_audit \
  jobs.tests.test_l3_search_tree_audit \
  > "$W/test-root-trace.log" 2>&1

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
python3 jobs/tools/fetch_result_files.py --prefix "$CAUSAL_PREFIX" \
  --file artefacts/scan-exact-8cf.pjtw.gz=scan-exact.pjtw.gz \
  --file artefacts/scan-exact-port-manifest.json=scan-port-manifest.json \
  --out-dir "$IN" --report "$ART/verified-0957.json" > "$W/fetch-0957.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$SEMANTICS_PREFIX" \
  --file artefacts/search-tree-sentinels.json=search-tree-sentinels.json \
  --file artefacts/scan-semantics-variant-manifest.json=variant-manifest.json \
  --file artefacts/scan-node-semantics-audit.json=source-0959.json \
  --out-dir "$IN" --report "$ART/verified-0959.json" > "$W/fetch-0959.log" 2>&1
gunzip -c "$IN/scan-exact.pjtw.gz" > "$W/SCAN_EXACT.pjtw"
[ "$(sha256sum "$W/SCAN_EXACT.pjtw"|awk '{print $1}')" = "$EXPECTED_EXACT_PJTW_SHA256" ] ||
  die "exact Scan PJTW hash mismatch"
python3 - "$IN" "$W/SCAN_VERIFY_THREAT.txt" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1])
source=json.loads((root/"source-0959.json").read_text())
if source.get("localization",{}).get("verdict")!="SCAN_INTERNAL_NODE_SEMANTICS_REQUIRED":
    raise SystemExit("0959 verdict mismatch")
sent=json.loads((root/"search-tree-sentinels.json").read_text())
if len(sent.get("sentinels",[]))!=48:
    raise SystemExit("0959 sentinel count mismatch")
variants=json.loads((root/"variant-manifest.json").read_text())
if variants.get("protocol")!="l3-pure-m1-scan-node-semantics-ladder-v1":
    raise SystemExit("0959 variant protocol mismatch")
spec=variants["arms"]["SCAN_VERIFY_THREAT"]["search_params"]
if len(spec.split(","))!=65:
    raise SystemExit("0959 exact-semantics fingerprint mismatch")
Path(sys.argv[2]).write_text(spec+"\n")
PY
cp "$IN/search-tree-sentinels.json" "$ART/search-tree-sentinels.json"
cp "$IN/source-0959.json" "$ART/source-0959.json"
cp "$IN/variant-manifest.json" "$ART/source-0959-variant-manifest.json"
cp "$IN/scan-port-manifest.json" "$ART/scan-exact-port-manifest.json"

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
make -C "$W/scan-source/src" -j4 > "$W/build-scan-trace.log" 2>&1
SCAN_TRACE="$W/scan-source/src/scan"
[ -x "$SCAN_TRACE" ] || die "instrumented Scan build missing"
python3 - "$PATCH" "$SCAN_TRACE" "$EXPECTED_SCAN_SOURCE_COMMIT" \
  "$ART/scan-trace-build-manifest.json" <<'PY'
import hashlib,json,sys
from pathlib import Path
patch,binary,commit,out=sys.argv[1:]
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
Path(out).write_text(json.dumps({
  "schema":1,
  "source_commit":commit,
  "patch_sha256":sha(patch),
  "binary_sha256":sha(binary),
  "trace_env":"SCAN_TRACE_ROOT",
},indent=2,sort_keys=True)+"\n")
PY

stage build-exact-jass-trace
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON -DJASS_DRAWISH_SCALING=ON -DJASS_SCAN_EXACT_EVAL=ON"
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cmake -S . -B "$W/build8-exact" $FLAGS > "$W/cmake8-exact.log" 2>&1
cmake --build "$W/build8-exact" -j4 --target jass > "$W/build8-exact.log" 2>&1
J8X="$W/build8-exact/jass"

stage paired-root-internal-traces
pids=()
for shard in $(seq 0 $((NSHARDS-1))); do
  timeout 14400 python3 jobs/tools/l3_internal_root_trace.py \
    --sentinels "$ART/search-tree-sentinels.json" \
    --jass "$J8X" --pattern "$W/SCAN_EXACT.pjtw" \
    --search-params-file "$W/SCAN_VERIFY_THREAT.txt" \
    --scan "$SCAN_TRACE" --shard "$shard" --nshards "$NSHARDS" \
    --out "$ART/traces/root-trace-s${shard}.json" \
    > "$W/root-trace-s${shard}.log" 2>&1 & pids+=("$!")
done
fail=0
for pid in "${pids[@]}"; do wait "$pid" || fail=$((fail+1)); done
[ "$fail" -eq 0 ] || die "$fail root-trace workers failed"
mapfile -t trace_inputs < <(find "$ART/traces" -name 'root-trace-s*.json' -print | sort)
[ "${#trace_inputs[@]}" -eq "$NSHARDS" ] || die "missing trace shards"
tar -C "$ART/traces" -czf "$ART/root-internal-traces.tar.gz" .

stage first-divergence-readout
python3 jobs/tools/l3_internal_root_trace_report.py \
  --sentinels "$ART/search-tree-sentinels.json" \
  --inputs "${trace_inputs[@]}" \
  --out "$ART/root-internal-trace-audit.json" \
  --summary-out "$ART/JASS_CONTROL_SUMMARY.json" | tee -a "$RES"
VERDICT="$(python3 - "$ART/JASS_CONTROL_SUMMARY.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["verdict"])
PY
)"
printf '%s\n' "$VERDICT" > "$ART/VERDICT__$VERDICT"
printf '%s\n' TRAINING_AUTHORIZED__FALSE > "$ART/TRAINING_AUTHORIZED__FALSE"
printf '%s\n' PROMOTION_AUTHORIZED__FALSE > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf '%s\n' AUTOMATIC_NEXT_JOB__NULL > "$ART/AUTOMATIC_NEXT_JOB__NULL"
stage complete
say "ROOT_INTERNAL_TRACE_READY verdict=$VERDICT training=false promotion=false"
