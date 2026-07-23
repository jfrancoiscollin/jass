#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Causal TOP3 conversion matrix on a self-play-reachable, design-balanced pool.
# Evaluation only: this job cannot train, promote, or queue a successor.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"
: "${JASS_RESULT_DIR:?}"
: "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"
: "${EXPECTED_JOB_ID:?pin the prepared 0908 job id}"
: "${EXPECTED_CODE_SHA:?pin the reviewed develop merge SHA}"
: "${SOURCE_0842_PREFIX:?pin the immutable 0842 result prefix}"
: "${SCAN_BIN:?pin the reviewed Scan executable path}"
: "${EXPECTED_SCAN_SHA256:?pin sha256 of the reviewed Scan executable}"
: "${EXPECTED_SCAN_RUNTIME_SHA256:?pin canonical Scan binary/ini/eval/runtime fingerprint}"
EVAL_SOURCE_MODE="${EVAL_SOURCE_MODE:-imbalance2-0890bis}"
case "$EVAL_SOURCE_MODE" in
  imbalance2-0890bis)
    : "${EVAL_0890BIS_PREFIX:?pin the immutable 0890bis result prefix}"
    ;;
  pure-0842) ;;
  *) echo "ABORT: unsupported EVAL_SOURCE_MODE=$EVAL_SOURCE_MODE" >&2; exit 2 ;;
esac

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
INPUTS="$W/inputs"
OUT="$W/out"
MATRIX="$W/matrix"
SCAN_RUNTIME_DIR="$W/scan-runtime"
mkdir -p "$W" "$ART" "$INPUTS" "$OUT" "$MATRIX"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }

DEPTH="${DEPTH:-10}"
MAXPLIES="${MAXPLIES:-400}"
POOL_POSITIONS="${POOL_POSITIONS:-384}"
NSHARDS="${NSHARDS:-16}"
PAR="${PAR:-16}"
GAME_TIMEOUT="${GAME_TIMEOUT:-120}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-1200}"
GLOBAL_TIMEOUT="${GLOBAL_TIMEOUT:-2100}"
JASS_BUILD_JOBS="${JASS_BUILD_JOBS:-4}"
POOL_SEED="${POOL_SEED:-271828}"
BOOTSTRAP="${BOOTSTRAP:-10000}"
BOOTSTRAP_SEED="${BOOTSTRAP_SEED:-271828}"
EXPECTED_SEARCH_SHA256="${EXPECTED_SEARCH_SHA256:-61cdaf50cc1948537990331d78f5b296dc6aee71cc7c2b98bcbd0969977619e1}"
ARMS=(scan_scan scan_g4 g4_scan g0_g0 g4_g0 g0_g4 g4_g4)
TOTAL_GAMES=2688

RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
PHASE_FILE="$W/phase.txt"
: > "$RES"
: > "$PROG"
printf '%s\n' "initializing" > "$PHASE_FILE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
set_phase(){
  printf '%s\n' "$1" > "$PHASE_FILE.tmp"
  mv "$PHASE_FILE.tmp" "$PHASE_FILE"
}

MONITOR_PID=""
ACTIVE_PIDS=()
stop_monitor(){
  [ -n "$MONITOR_PID" ] || return 0
  kill "$MONITOR_PID" 2>/dev/null || true
  wait "$MONITOR_PID" 2>/dev/null || true
  MONITOR_PID=""
}
start_monitor(){
  local started="$1"
  (
    while true; do
      python3 - "$MATRIX" "$started" "$PROG.tmp" "$TOTAL_GAMES" "$PHASE_FILE" <<'PY'
import datetime as dt, glob, json, os, sys, time
root, started, target, total, phase_path = (
    sys.argv[1], float(sys.argv[2]), sys.argv[3], int(sys.argv[4]), sys.argv[5]
)
try:
    phase = open(phase_path, encoding="utf-8").read().strip()
except OSError:
    phase = "unknown"
completed = 0
arms = {}
for path in glob.glob(os.path.join(root, "*", "*.progress.json")):
    try:
        row = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        continue
    arm = str(row.get("arm", "unknown"))
    count = int(row.get("completed", 0))
    completed += count
    arms[arm] = arms.get(arm, 0) + count
elapsed = max(time.time() - started, 0.001)
rate = completed / elapsed
remaining = max(total - completed, 0)
eta = remaining / rate if rate else None
now = dt.datetime.now(dt.timezone(dt.timedelta(hours=2)))
with open(target, "w", encoding="utf-8") as handle:
    handle.write(f"time_fr={now.isoformat()}\n")
    handle.write(f"phase={phase}\n")
    handle.write(f"completed_games={completed}/{total} rate_games_s={rate:.4f} ")
    handle.write(f"eta_seconds={eta:.0f}\n" if eta is not None else "eta_seconds=unknown\n")
    handle.write("arms=" + json.dumps(arms, sort_keys=True) + "\n")
PY
      mv "$PROG.tmp" "$PROG"
      cp "$PROG" "$ART/.PROGRESS.txt.tmp"
      mv "$ART/.PROGRESS.txt.tmp" "$ART/PROGRESS.txt"
      sleep 60
    done
  ) &
  MONITOR_PID="$!"
}

run_pids(){
  local label="$1"; shift
  local failed=0 pid
  for pid in "$@"; do
    wait "$pid" || failed=$((failed+1))
  done
  [ "$failed" -eq 0 ] || die "$label: $failed failed/timed-out shard(s)"
}

finalize(){
  rc=$?
  trap - EXIT ERR INT TERM
  set +e
  stop_monitor
  if [ "${#ACTIVE_PIDS[@]}" -gt 0 ]; then
    kill "${ACTIVE_PIDS[@]}" 2>/dev/null || true
    for pid in "${ACTIVE_PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done
  fi
  [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  [ -d "$OUT" ] && cp -a "$OUT/." "$ART/"
  if [ -d "$MATRIX" ] && [ ! -f "$OUT/stable-top3-causal-matrix-raw.tar.gz" ]; then
    tar -C "$W" -czf "$ART/stable-top3-causal-matrix-partial.tar.gz" matrix \
      2>/dev/null || true
  fi
  if [ -d "$W" ]; then
    (cd "$W" && find . -type f -name '*.log' -print0 |
      tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  fi
  rm -rf "$W/build" "$INPUTS" "$SCAN_RUNTIME_DIR" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 130' INT
trap 'exit 143' TERM

say "=== $JASS_JOB_ID -- stable TOP3 causal conversion matrix ==="
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ -z "$(git branch --show-current)" ] || die "runner code worktree must be detached"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ "${SCIENTIFIC_GO:-0}" = 1 ] || die "SCIENTIFIC_GO=1 missing"
[ "${CAUSAL_MATRIX_GO:-0}" = 1 ] || die "CAUSAL_MATRIX_GO=1 missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "NO_AUTOMATIC_CONTINUATION=1 missing"
[ "$DEPTH" -eq 10 ] || die "all seven arms require common depth 10"
[ "$MAXPLIES" -eq 400 ] || die "matrix requires maxplies=400"
[ "$POOL_POSITIONS" -eq 384 ] || die "matrix requires exactly 384 positions"
[ "$NSHARDS" -eq 16 ] && [ "$PAR" -eq 16 ] || die "CPX62 matrix requires 16 shards / 16 parallel"
[ "$GAME_TIMEOUT" -eq 120 ] || die "per-game timeout must remain 120s"
if [ "$EVAL_SOURCE_MODE" = pure-0842 ]; then
  [ "$SHARD_TIMEOUT" -eq 900 ] || die "0921 per-shard timeout must remain 900s"
  [ "$GLOBAL_TIMEOUT" -eq 1200 ] || die "0921 global cap must remain 1200s"
else
  [ "$SHARD_TIMEOUT" -eq 1200 ] || die "per-shard timeout must remain 1200s"
  [ "$GLOBAL_TIMEOUT" -eq 2100 ] || die "global cap must remain 2100s"
fi
[ "$JASS_BUILD_JOBS" -eq 4 ] || die "build must remain -j4"
[ "$EXPECTED_SEARCH_SHA256" = 61cdaf50cc1948537990331d78f5b296dc6aee71cc7c2b98bcbd0969977619e1 ] \
  || die "unexpected 0890bis search fingerprint"

JOB_STARTED_EPOCH="$(date +%s)"
set_phase preflight
start_monitor "$JOB_STARTED_EPOCH"

# Runner-v3 disk hygiene. The target excludes this fresh work directory by age.
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
NPROC="$(nproc)"
[ "$NPROC" -eq 16 ] || die "CPX62 nproc drift: expected 16, got $NPROC"
MEM_MB="$(awk '/MemTotal:/ {printf "%d", $2/1024}' /proc/meminfo)"
[ "${MEM_MB:-0}" -ge 30000 ] || die "0908 is approved only for the 32 GiB CPX62 runner"
FREE_MB="$(df -Pm /root | awk 'NR==2 {print $4}')"
[ "${FREE_MB:-0}" -gt 5000 ] || die "free disk below 5 GiB"
[ -x "$SCAN_BIN" ] || die "Scan binary missing or not executable: $SCAN_BIN"
SCAN_SOURCE_BIN="$(readlink -f "$SCAN_BIN")"
SCAN_SOURCE_DIR="$(dirname "$SCAN_SOURCE_BIN")"
SCAN_SHA256="$(sha256sum "$SCAN_SOURCE_BIN" | awk '{print $1}')"
[ "$SCAN_SHA256" = "$EXPECTED_SCAN_SHA256" ] || die "Scan binary SHA256 mismatch"
for relative in scan.ini data/eval; do
  [ -f "$SCAN_SOURCE_DIR/$relative" ] \
    || die "active Scan runtime file missing: $SCAN_SOURCE_DIR/$relative"
done
mkdir -p "$SCAN_RUNTIME_DIR/data"
cp "$SCAN_SOURCE_BIN" "$SCAN_RUNTIME_DIR/scan_linux"
cp "$SCAN_SOURCE_DIR/scan.ini" "$SCAN_RUNTIME_DIR/scan.ini"
cp "$SCAN_SOURCE_DIR/data/eval" "$SCAN_RUNTIME_DIR/data/eval"
chmod 0555 "$SCAN_RUNTIME_DIR/scan_linux"
chmod 0444 "$SCAN_RUNTIME_DIR/scan.ini" "$SCAN_RUNTIME_DIR/data/eval"
SCAN_RUNTIME_SHA256="$(
  python3 jobs/tools/scan_runtime_fingerprint.py \
    --scan-dir "$SCAN_RUNTIME_DIR" --output "$OUT/scan-runtime-manifest.json"
)"
[ "$SCAN_RUNTIME_SHA256" = "$EXPECTED_SCAN_RUNTIME_SHA256" ] \
  || die "Scan runtime fingerprint mismatch"
SCAN_RUNTIME_BIN="$SCAN_RUNTIME_DIR/scan_linux"
say "preflight: nproc=$NPROC mem_mb=$MEM_MB free_mb=$FREE_MB build=-j$JASS_BUILD_JOBS scan_sha256=$SCAN_SHA256 scan_runtime_sha256=$SCAN_RUNTIME_SHA256"
if [ "$EVAL_SOURCE_MODE" = pure-0842 ]; then
  say "sizing: observed_0908=2688_games/320s_total; same matrix volume=2688; ETA_total=7-12min; hard_cap=1200s"
else
  say "sizing: anchor_0862=2048_games/328s=6.24_games_s; volume=7x384=2688; projected_play=431s; ETA_total=12-22min; hard_cap=2100s"
fi

set_phase smoke_tests
bash -n "$0"
python3 -m py_compile \
  jobs/tools/fetch_result_files.py \
  jobs/tools/calibrate_vs_scan.py \
  jobs/tools/scan_runtime_fingerprint.py \
  jobs/tools/stable_conversion_matrix.py \
  tools/stable_conversion_pool.py
python3 jobs/tests/test_stable_conversion_pool.py > "$W/test-stable-pool.log" 2>&1 \
  || die "stable pool tests failed"
python3 jobs/tests/test_stable_conversion_matrix.py > "$W/test-stable-matrix.log" 2>&1 \
  || die "matrix runner/aggregator round-trip tests failed"
python3 jobs/tests/test_stable_conversion_job.py > "$W/test-stable-job-contract.log" 2>&1 \
  || die "0908 template/CLI wiring contract failed"
python3 jobs/tests/test_scan_runtime_fingerprint.py > "$W/test-scan-runtime.log" 2>&1 \
  || die "Scan runtime fingerprint tests failed"
python3 tools/test_calibrate_vs_scan.py > "$W/test-draw-rules.log" 2>&1 \
  || die "draw-rule tests failed"
say "smoke: bash/python syntax + pool + runner write/read + draw rules OK"

# Fetch all pool sources plus their provenance profiles from immutable 0842.
set_phase fetch_inputs
python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_0842_PREFIX" \
  --file artefacts/l3-pure-p1-manifest.json=0842-manifest.json \
  --file artefacts/g1-profile.json=0842-g1-profile.json \
  --file artefacts/g1-selfplay.jnnw.gz=0842-g1.jnnw.gz \
  --file artefacts/g1-selfplay.jsm.gz=0842-g1.jsm.gz \
  --file artefacts/g2-profile.json=0842-g2-profile.json \
  --file artefacts/g2-selfplay.jnnw.gz=0842-g2.jnnw.gz \
  --file artefacts/g2-selfplay.jsm.gz=0842-g2.jsm.gz \
  --file artefacts/g3-profile.json=0842-g3-profile.json \
  --file artefacts/g3-selfplay.jnnw.gz=0842-g3.jnnw.gz \
  --file artefacts/g3-selfplay.jsm.gz=0842-g3.jsm.gz \
  --file artefacts/g4-profile.json=0842-g4-profile.json \
  --file artefacts/g4-selfplay.jnnw.gz=0842-g4.jnnw.gz \
  --file artefacts/g4-selfplay.jsm.gz=0842-g4.jsm.gz \
  --out-dir "$INPUTS" --report "$OUT/verified-0842-source.json" \
  > "$W/fetch-0842.log" 2>&1

# Select the evaluated model lineage. 0908 defaults to the specialist 0890bis
# source; 0921 uses the G0/G4 pair from the immutable pure 0842 lineage.
if [ "$EVAL_SOURCE_MODE" = pure-0842 ]; then
python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_0842_PREFIX" \
  --file artefacts/l3-pure-p1-manifest.json=pure-eval-manifest.json \
  --file artefacts/g0-material.pjtw.gz=pure-g0.pjtw.gz \
  --file artefacts/g4.pjtw.gz=pure-g4.pjtw.gz \
  --out-dir "$INPUTS" --report "$OUT/verified-pure-eval-source.json" \
  > "$W/fetch-pure-eval.log" 2>&1

python3 - "$OUT/verified-0842-source.json" "$OUT/verified-pure-eval-source.json" \
  "$INPUTS" "$OUT/source-contract.json" "$W/search-params.txt" \
  "$W/g0.pjtw" "$W/g4.pjtw" <<'PY'
import gzip, hashlib, json, sys
from pathlib import Path

sreport_path, ereport_path, root_name, out_name, search_name, g0_name, g4_name = sys.argv[1:]
root = Path(root_name)
sreport = json.load(open(sreport_path, encoding="utf-8"))
ereport = json.load(open(ereport_path, encoding="utf-8"))
source_job = "cpx62-0842-l3-p1-frozen-v1"
source_code = "337ccbdc4889732af43d3a4a713b8dac06f2a864"
for report in (sreport, ereport):
    if (report.get("job_id"), report.get("code_sha")) != (source_job, source_code):
        raise SystemExit("0842 identity/code mismatch")

source_expected = {
    "0842-manifest.json": "672d28f14eb41cbf3a074adf407c6cd000726aadf0b9c6b756cf050c7719d9c5",
    "0842-g1-profile.json": "c97d6fecff10443075d131ea528225114faa793d34c924bc40a56b20cfa47585",
    "0842-g1.jnnw.gz": "a1f181ef61d06967a4f4a2e737faaf6f6bee3a80698a864bc1b1fd98f15ab604",
    "0842-g1.jsm.gz": "2e30b630d748c54a2c889cd76c07ce90a9453a27b86542b8bcdd920daaa1a5f0",
    "0842-g2-profile.json": "67ca0194070f7a23f5f46ed049938c5630bd08102f57e22f4b7db7e8c42677f7",
    "0842-g2.jnnw.gz": "2ac958bc29af102cf32ef3c19ba3b04f74be683b203cc8e8685d201abf971ba0",
    "0842-g2.jsm.gz": "05d300165196ef548f80cef83d6444f184bafb4aeff15435bc17ce4761b5062c",
    "0842-g3-profile.json": "8321e219f327015bd569cc2866e006c151f24aa9968df8dafbc63601a74a9c43",
    "0842-g3.jnnw.gz": "4ce6472bcf67cd8aaa9d830314bc2386edd763f8449b84511aa8c4ca64f1cc2e",
    "0842-g3.jsm.gz": "fa88eb09a38bc3f17e3b8b99f773925d58d6e4fe7c70feab84db62ff20c450a3",
    "0842-g4-profile.json": "4eaa0f1ad0207638678c4b65566aa8758766974e559f910ed38811daed1fb278",
    "0842-g4.jnnw.gz": "f98e2c59cfca1304e414823271170bdc4955fc70b2937094adc14c5e11551f60",
    "0842-g4.jsm.gz": "52e271f1482c93cfdb472c475680f922fd53bb56a5ce649f1e42c9bd4ed4d330",
}
eval_expected = {
    "pure-eval-manifest.json": "672d28f14eb41cbf3a074adf407c6cd000726aadf0b9c6b756cf050c7719d9c5",
    "pure-g0.pjtw.gz": "4e63338e95f703a080cb4f29f60f09c93d8109395c616736f0ef9d9ca0e56e8f",
    "pure-g4.pjtw.gz": "e7eb9cd359d3418720e5e39484187d9d224ac9febd2b26e6302190454dd4e8e6",
}
def report_map(report):
    return {row["local_name"]: row["sha256"] for row in report.get("files", [])}
if report_map(sreport) != source_expected:
    raise SystemExit("0842 pool source inventory differs from pinned SHA256 set")
if report_map(ereport) != eval_expected:
    raise SystemExit("0842 evaluated model inventory differs from pinned SHA256 set")

manifest = json.loads((root / "pure-eval-manifest.json").read_text(encoding="utf-8"))
recipe = manifest.get("recipe") or {}
if (
    manifest.get("code_sha") != source_code
    or manifest.get("experiment") != "L3-PURE-P1"
    or manifest.get("phase_complete") != "P1"
    or recipe.get("lineage") != "L3-PURE"
    or recipe.get("generations") != 4
    or recipe.get("geometry") != "8cf"
    or manifest.get("search_params_count") != 63
):
    raise SystemExit("0842 pure scientific manifest mismatch")
if (
    manifest.get("external_teacher_inputs") != 0
    or manifest.get("training_sources") != ["selfplay_terminal_wdl"]
    or not (recipe.get("truth") or {}).get("terminal_wdl_only")
):
    raise SystemExit("0842 is not the no-oracle terminal-WDL pure lineage")
if manifest.get("student_sha256", {}).get("g4.pjtw.gz") != eval_expected["pure-g4.pjtw.gz"]:
    raise SystemExit("0842 pure G4 digest differs inside scientific manifest")

profile_proofs = {}
for gen in range(1, 5):
    profile = json.loads((root / f"0842-g{gen}-profile.json").read_text(encoding="utf-8"))
    if profile.get("operation") != "profile_selfplay" or profile.get("records") != 500000:
        raise SystemExit(f"0842 G{gen}: invalid profile shape/count")
    sources = profile.get("source_records", {})
    if sources.get("standard") != 500000 or sources.get("frontier", 0) != 0:
        raise SystemExit(f"0842 G{gen}: corpus is not 100% standard self-play")
    raw_data = gzip.decompress((root / f"0842-g{gen}.jnnw.gz").read_bytes())
    raw_meta = gzip.decompress((root / f"0842-g{gen}.jsm.gz").read_bytes())
    data_sha = hashlib.sha256(raw_data).hexdigest()
    meta_sha = hashlib.sha256(raw_meta).hexdigest()
    if profile.get("input", {}).get("data_sha256") != data_sha:
        raise SystemExit(f"0842 G{gen}: decompressed JNNW/profile mismatch")
    if profile.get("input", {}).get("meta_sha256") != meta_sha:
        raise SystemExit(f"0842 G{gen}: decompressed JSM/profile mismatch")
    profile_proofs[f"G{gen}"] = {
        "records": 500000, "standard": 500000, "frontier": 0,
        "raw_data_sha256": data_sha, "raw_meta_sha256": meta_sha,
    }

search = str(recipe.get("search_params", ""))
search_sha = hashlib.sha256(search.encode()).hexdigest()
expected_search = "61cdaf50cc1948537990331d78f5b296dc6aee71cc7c2b98bcbd0969977619e1"
if search_sha != expected_search or manifest.get("search_params_sha256") != expected_search:
    raise SystemExit("0842 pure search fingerprint SHA256 mismatch")
g0_raw = gzip.decompress((root / "pure-g0.pjtw.gz").read_bytes())
g4_raw = gzip.decompress((root / "pure-g4.pjtw.gz").read_bytes())
if hashlib.sha256(g0_raw).hexdigest() != "4dd50bd836375d825234fa263a964a2b684e865c6513cd7813d5ff93dbe97864":
    raise SystemExit("0842 pure G0 raw digest mismatch")
if hashlib.sha256(g4_raw).hexdigest() != "93c76031be3a039aa08eec4a1d3166321d93d602ca78a139509f8c6e90de5e86":
    raise SystemExit("0842 pure G4 raw digest mismatch")
Path(g0_name).write_bytes(g0_raw)
Path(g4_name).write_bytes(g4_raw)
Path(search_name).write_text(search + "\n", encoding="utf-8")

contract = {
    "schema": 1,
    "protocol": "stable-top3-causal-conversion-matrix",
    "selection_source": {
        "job_id": source_job, "code_sha": source_code,
        "prefix": sreport["prefix"], "selected_sha256": source_expected,
        "profiles": profile_proofs, "generation_recipe": recipe,
        "outcome_used_for_selection": False,
    },
    "evaluated_models": {
        "job_id": source_job, "code_sha": source_code,
        "prefix": ereport["prefix"], "selected_sha256": eval_expected,
        "lineage": "L3-PURE", "generation": "G4",
        "geometry": "8cf", "search_params_count": 63,
        "search_params_sha256": search_sha,
        "g0_raw_sha256": hashlib.sha256(g0_raw).hexdigest(),
        "g4_raw_sha256": hashlib.sha256(g4_raw).hexdigest(),
    },
    "scan_used_for_training": False,
    "training_continuation_authorized": False,
    "promotion_authorized": False,
    "automatic_next_job": None,
}
Path(out_name).write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
else
# Fetch only the evaluated G0/G4 and scientific manifest from immutable 0890bis.
python3 jobs/tools/fetch_result_files.py --prefix "$EVAL_0890BIS_PREFIX" \
  --file artefacts/l3-imbalance2-top3-p1-manifest.json=0890bis-manifest.json \
  --file artefacts/g0-material.pjtw.gz=0890bis-g0.pjtw.gz \
  --file artefacts/g4.pjtw.gz=0890bis-g4.pjtw.gz \
  --out-dir "$INPUTS" --report "$OUT/verified-0890bis-source.json" \
  > "$W/fetch-0890bis.log" 2>&1

python3 - "$OUT/verified-0842-source.json" "$OUT/verified-0890bis-source.json" \
  "$INPUTS" "$OUT/source-contract.json" "$W/search-params.txt" \
  "$W/g0.pjtw" "$W/g4.pjtw" <<'PY'
import gzip, hashlib, json, sys
from pathlib import Path

sreport_path, ereport_path, root_name, out_name, search_name, g0_name, g4_name = sys.argv[1:]
root = Path(root_name)
sreport = json.load(open(sreport_path, encoding="utf-8"))
ereport = json.load(open(ereport_path, encoding="utf-8"))

source_job = "cpx62-0842-l3-p1-frozen-v1"
source_code = "337ccbdc4889732af43d3a4a713b8dac06f2a864"
eval_job = "ccx33-0890bis-l3-imbalance2-top3-selfplay-2m-p1"
eval_code = "952bea08c6d4d657df841eb76627537677141f53"
if (sreport.get("job_id"), sreport.get("code_sha")) != (source_job, source_code):
    raise SystemExit("0842 identity/code mismatch")
if (ereport.get("job_id"), ereport.get("code_sha")) != (eval_job, eval_code):
    raise SystemExit("0890bis identity/code mismatch")

source_expected = {
    "0842-manifest.json": "672d28f14eb41cbf3a074adf407c6cd000726aadf0b9c6b756cf050c7719d9c5",
    "0842-g1-profile.json": "c97d6fecff10443075d131ea528225114faa793d34c924bc40a56b20cfa47585",
    "0842-g1.jnnw.gz": "a1f181ef61d06967a4f4a2e737faaf6f6bee3a80698a864bc1b1fd98f15ab604",
    "0842-g1.jsm.gz": "2e30b630d748c54a2c889cd76c07ce90a9453a27b86542b8bcdd920daaa1a5f0",
    "0842-g2-profile.json": "67ca0194070f7a23f5f46ed049938c5630bd08102f57e22f4b7db7e8c42677f7",
    "0842-g2.jnnw.gz": "2ac958bc29af102cf32ef3c19ba3b04f74be683b203cc8e8685d201abf971ba0",
    "0842-g2.jsm.gz": "05d300165196ef548f80cef83d6444f184bafb4aeff15435bc17ce4761b5062c",
    "0842-g3-profile.json": "8321e219f327015bd569cc2866e006c151f24aa9968df8dafbc63601a74a9c43",
    "0842-g3.jnnw.gz": "4ce6472bcf67cd8aaa9d830314bc2386edd763f8449b84511aa8c4ca64f1cc2e",
    "0842-g3.jsm.gz": "fa88eb09a38bc3f17e3b8b99f773925d58d6e4fe7c70feab84db62ff20c450a3",
    "0842-g4-profile.json": "4eaa0f1ad0207638678c4b65566aa8758766974e559f910ed38811daed1fb278",
    "0842-g4.jnnw.gz": "f98e2c59cfca1304e414823271170bdc4955fc70b2937094adc14c5e11551f60",
    "0842-g4.jsm.gz": "52e271f1482c93cfdb472c475680f922fd53bb56a5ce649f1e42c9bd4ed4d330",
}
eval_expected = {
    "0890bis-manifest.json": "08eb6be803519a35d7ef1135be03c58c2deebddb8440d560bf7c5cc181b51641",
    "0890bis-g0.pjtw.gz": "4e63338e95f703a080cb4f29f60f09c93d8109395c616736f0ef9d9ca0e56e8f",
    "0890bis-g4.pjtw.gz": "2f605b9a53d7ccfed017310a7f9574f5d9b1bfa50e0529b0346c6015f14bed36",
}
def report_map(report):
    return {row["local_name"]: row["sha256"] for row in report.get("files", [])}
if report_map(sreport) != source_expected:
    raise SystemExit("0842 selected inventory differs from pinned SHA256 set")
if report_map(ereport) != eval_expected:
    raise SystemExit("0890bis selected inventory differs from pinned SHA256 set")

smanifest = json.loads((root / "0842-manifest.json").read_text(encoding="utf-8"))
if smanifest.get("code_sha") != source_code or smanifest.get("experiment") != "L3-PURE-P1":
    raise SystemExit("0842 scientific manifest mismatch")
if smanifest.get("phase_complete") != "P1" or smanifest.get("recipe", {}).get("generations") != 4:
    raise SystemExit("0842 is not the complete four-generation P1 source")

profile_proofs = {}
for gen in range(1, 5):
    profile = json.loads((root / f"0842-g{gen}-profile.json").read_text(encoding="utf-8"))
    if profile.get("operation") != "profile_selfplay" or profile.get("records") != 500000:
        raise SystemExit(f"0842 G{gen}: invalid profile shape/count")
    sources = profile.get("source_records", {})
    if sources.get("standard") != 500000 or sources.get("frontier", 0) != 0:
        raise SystemExit(f"0842 G{gen}: corpus is not 100% standard self-play")
    raw_data = gzip.decompress((root / f"0842-g{gen}.jnnw.gz").read_bytes())
    raw_meta = gzip.decompress((root / f"0842-g{gen}.jsm.gz").read_bytes())
    data_sha = hashlib.sha256(raw_data).hexdigest()
    meta_sha = hashlib.sha256(raw_meta).hexdigest()
    if profile.get("input", {}).get("data_sha256") != data_sha:
        raise SystemExit(f"0842 G{gen}: decompressed JNNW/profile mismatch")
    if profile.get("input", {}).get("meta_sha256") != meta_sha:
        raise SystemExit(f"0842 G{gen}: decompressed JSM/profile mismatch")
    profile_proofs[f"G{gen}"] = {
        "records": 500000, "standard": 500000, "frontier": 0,
        "raw_data_sha256": data_sha, "raw_meta_sha256": meta_sha,
    }

emanifest = json.loads((root / "0890bis-manifest.json").read_text(encoding="utf-8"))
if emanifest.get("code_sha") != eval_code or emanifest.get("lineage") != "L3-IMBALANCE2-TOP3":
    raise SystemExit("0890bis scientific manifest mismatch")
if emanifest.get("geometry") != "8cf" or emanifest.get("search_params_count") != 63:
    raise SystemExit("0890bis geometry/search fingerprint shape mismatch")
search = str(emanifest.get("search_params", ""))
search_sha = hashlib.sha256(search.encode()).hexdigest()
expected_search = "61cdaf50cc1948537990331d78f5b296dc6aee71cc7c2b98bcbd0969977619e1"
if search_sha != expected_search:
    raise SystemExit("0890bis search fingerprint SHA256 mismatch")
if emanifest.get("student_sha256", {}).get("g4.pjtw.gz") != eval_expected["0890bis-g4.pjtw.gz"]:
    raise SystemExit("0890bis G4 digest differs inside scientific manifest")

g0_raw = gzip.decompress((root / "0890bis-g0.pjtw.gz").read_bytes())
g4_raw = gzip.decompress((root / "0890bis-g4.pjtw.gz").read_bytes())
if not g0_raw or not g4_raw:
    raise SystemExit("empty decompressed G0/G4 pattern")
Path(g0_name).write_bytes(g0_raw)
Path(g4_name).write_bytes(g4_raw)
Path(search_name).write_text(search + "\n", encoding="utf-8")

contract = {
    "schema": 1,
    "protocol": "stable-top3-causal-conversion-matrix",
    "selection_source": {
        "job_id": source_job, "code_sha": source_code,
        "prefix": sreport["prefix"], "selected_sha256": source_expected,
        "profiles": profile_proofs,
        "generation_recipe": smanifest.get("recipe"),
        "outcome_used_for_selection": False,
    },
    "evaluated_models": {
        "job_id": eval_job, "code_sha": eval_code,
        "prefix": ereport["prefix"], "selected_sha256": eval_expected,
        "geometry": "8cf", "search_params_count": 63,
        "search_params_sha256": search_sha,
        "g0_raw_sha256": hashlib.sha256(g0_raw).hexdigest(),
        "g4_raw_sha256": hashlib.sha256(g4_raw).hexdigest(),
    },
    "scan_used_for_training": False,
    "training_continuation_authorized": False,
    "promotion_authorized": False,
    "automatic_next_job": None,
}
Path(out_name).write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
fi

SEARCH_PARAMS="$(cat "$W/search-params.txt")"
[ "$(printf '%s' "$SEARCH_PARAMS" | sha256sum | awk '{print $1}')" = "$EXPECTED_SEARCH_SHA256" ] \
  || die "runtime search fingerprint mismatch"

# Materialise every performance-critical source from the reviewed, pinned SHA.
set_phase build_and_native_tests
mkdir -p "$W/pinned-src"
for source in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/movegen.cpp src/movegen.hpp; do
  target="$W/pinned-src/${source#src/}"
  git show "$EXPECTED_CODE_SHA:$source" > "$target"
  [ -s "$target" ] || die "pinned source missing: $source"
  cp "$target" "$source"
done
grep -q "g_emasks" src/scan_eval.cpp || die "scan_eval missing g_emasks"
grep -q "has_any_capture" src/search.cpp || die "search missing has_any_capture"
grep -q "has_any_capture" src/movegen.cpp || die "movegen missing has_any_capture"
say "architecture guard: pinned 8cf sources + g_emasks + has_any_capture OK"

python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen-patterns.log" 2>&1
NPAT="$(PYTHONPATH=pattern_jass/tools python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')"
[ "$NPAT" -eq 4251528 ] || die "8cf geometry mismatch: n_pat=$NPAT"
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=OFF -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
cmake -S . -B "$W/build" $FLAGS > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$JASS_BUILD_JOBS" --target jass jass_tests \
  > "$W/build.log" 2>&1
ctest --test-dir "$W/build" --output-on-failure > "$W/ctest.log" 2>&1 \
  || die "native engine/HUB regression tests failed"
J="$W/build/jass"
[ -x "$J" ] || die "Jass build missing"

POOL="$W/stable-top3.fen"
PROOF="$W/stable-top3.proof.jsonl"
POOL_MANIFEST="$OUT/stable-top3-pool-manifest.json"
AUDIT_MANIFEST="$OUT/stable-top3-pool-audit.json"
set_phase pool_build_and_audit
CORPUS_ARGS=()
for gen in 1 2 3 4; do
  CORPUS_ARGS+=(--corpus "$INPUTS/0842-g${gen}.jnnw.gz" "$INPUTS/0842-g${gen}.jsm.gz")
done
python3 tools/stable_conversion_pool.py build --jass "$J" \
  "${CORPUS_ARGS[@]}" \
  --piece-pair 16:18 --piece-pair 17:19 --piece-pair 18:20 \
  --max-positions "$POOL_POSITIONS" --min-positions "$POOL_POSITIONS" \
  --seed "$POOL_SEED" --out-pool "$POOL" --out-proof "$PROOF" \
  --manifest "$POOL_MANIFEST" > "$W/pool-build.log" 2>&1 \
  || die "stable pool could not fill all 12 cells to 32"
python3 tools/stable_conversion_pool.py audit --jass "$J" \
  "${CORPUS_ARGS[@]}" \
  --piece-pair 16:18 --piece-pair 17:19 --piece-pair 18:20 \
  --pool "$POOL" --proof "$PROOF" --manifest "$AUDIT_MANIFEST" \
  > "$W/pool-audit.log" 2>&1
python3 - "$POOL_MANIFEST" "$AUDIT_MANIFEST" "$OUT/pool-contract.json" <<'PY'
import json, sys
from pathlib import Path
build = json.load(open(sys.argv[1], encoding="utf-8"))
audit = json.load(open(sys.argv[2], encoding="utf-8"))
expected = {
    f"{low}v{high}|adv={adv}|stm={stm}": 32
    for low, high in ((16, 18), (17, 19), (18, 20))
    for adv in ("W", "B") for stm in ("W", "B")
}
if build.get("gate_ready") is not True or build.get("selected_positions") != 384:
    raise SystemExit("stable pool did not meet strict 384-position floor")
if build.get("selected_cells") != expected:
    raise SystemExit("stable pool is not 32-per-cell balanced")
if build.get("selected_source_units") != 384:
    raise SystemExit("stable pool does not have 384 independent opening ids")
if audit.get("positions") != 384 or audit.get("cells") != expected:
    raise SystemExit("independent stable pool audit mismatch")
if audit.get("pool_sha256") != build.get("outputs", {}).get("pool_sha256"):
    raise SystemExit("pool changed between build and audit")
if audit.get("proof_sha256") != build.get("outputs", {}).get("proof_sha256"):
    raise SystemExit("proof changed between build and audit")
payload = {
    "schema": 1, "gate_ready": True, "positions": 384,
    "positions_per_cell": 32, "cells": expected,
    "pool_sha256": audit["pool_sha256"], "proof_sha256": audit["proof_sha256"],
    "source_mode": "jnnw_jsm1_unseeded_selfplay",
    "one_position_per_opening_id": True,
    "stability_scope": "all_legal_first_plies_only",
    "certifies_theoretical_win": False,
}
Path(sys.argv[3]).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
cp "$POOL" "$OUT/stable-top3.fen"
cp "$PROOF" "$OUT/stable-top3.proof.jsonl"
say "pool: 384 self-play-reachable, design-balanced, first-ply-stable positions; 12 cells x32; not a natural-frequency or theoretical-win estimate; build+independent audit OK"

python3 - "$OUT/source-contract.json" "$OUT/pool-contract.json" \
  "$OUT/scan-runtime-manifest.json" "$OUT/run-config.json" \
  "$EXPECTED_CODE_SHA" "$SCAN_RUNTIME_BIN" "$SCAN_SOURCE_BIN" "$DEPTH" "$MAXPLIES" \
  "$GAME_TIMEOUT" "$SHARD_TIMEOUT" "$GLOBAL_TIMEOUT" "$NSHARDS" <<'PY'
import hashlib, json, sys
from pathlib import Path
source = json.load(open(sys.argv[1], encoding="utf-8"))
pool = json.load(open(sys.argv[2], encoding="utf-8"))
scan_manifest = json.load(open(sys.argv[3], encoding="utf-8"))
out, code, scan, scan_source, depth, maxplies, game_to, shard_to, global_to, nshards = sys.argv[4:]
file_hashes = {row["path"]: row["sha256"] for row in scan_manifest["active_files"]}
hub_params = scan_manifest["hub_params"]
hub_params_sha = hashlib.sha256(json.dumps(
    hub_params, sort_keys=True, separators=(",", ":"),
).encode()).hexdigest()
payload = {
    "schema": 1, "protocol": "stable-top3-causal-conversion-matrix",
    "code_sha": code, "selection_source": source["selection_source"],
    "evaluated_models": source["evaluated_models"], "pool": pool,
    "scan": {
        "source_path": scan_source, "runtime_path": scan,
        "binary_sha256": file_hashes["scan_linux"],
        "ini_sha256": file_hashes["scan.ini"],
        "eval_sha256": file_hashes["data/eval"],
        "runtime_sha256": scan_manifest["runtime_sha256"],
        "hub_params": hub_params, "hub_params_sha256": hub_params_sha,
        "snapshot_read_only": True,
    },
    "budget": {"kind": "fixed_depth", "depth": int(depth), "max_plies": int(maxplies)},
    "timeouts_seconds": {"game": int(game_to), "shard": int(shard_to), "global": int(global_to)},
    "nshards": int(nshards),
    "arms": [
        "scan_scan", "scan_g4", "g4_scan",
        "g0_g0", "g4_g0", "g0_g4", "g4_g4",
    ],
    "games_per_arm": 384, "total_games": 2688,
    "perspective": "initial_material_up_side",
    "move_identity": "exact_capture_set",
    "estimand": {
        "name": "equal_weight_12_cell_standardized",
        "unit": "one selected position per immutable opening_id",
        "weighting": "12 fixed cells with 32 positions each",
        "conditioning": [
            "0842 standard self-play G1-G4",
            "exactly +2 men, no kings, strata 16v18/17v19/18v20",
            "no capture or promotion for either colour on the first ply",
        ],
        "natural_corpus_prevalence_estimate": False,
        "theoretical_win_probability": False,
    },
    "inference": {
        "primary": "paired_deltas.global.attack",
        "non_primary_intervals": "exploratory",
    },
    "scan_comparison": (
        "Scan/Scan is the joint conversion benchmark; Scan/G4 and G4/Scan "
        "identify Scan attack and defense contrasts against G4"
    ),
    "pool_interpretation": "first-ply material stability only; no theoretical-win or two-ply guarantee",
    "training_continuation_authorized": False,
    "promotion_authorized": False, "automatic_next_job": None,
}
Path(out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

BENCHMARK_STARTED_EPOCH="$(date +%s)"
BENCHMARK_STARTED_SECONDS="$SECONDS"
stop_monitor
set_phase benchmark
start_monitor "$BENCHMARK_STARTED_EPOCH"

run_arm(){
  local arm="$1"
  local elapsed remaining shard_timeout shard
  elapsed=$((SECONDS - BENCHMARK_STARTED_SECONDS))
  remaining=$((GLOBAL_TIMEOUT - elapsed))
  [ "$remaining" -gt 0 ] || die "global benchmark cap exhausted before $arm"
  shard_timeout="$SHARD_TIMEOUT"
  [ "$remaining" -ge "$shard_timeout" ] || shard_timeout="$remaining"
  mkdir -p "$MATRIX/$arm"
  local -a pids=()
  for shard in $(seq 0 $((NSHARDS - 1))); do
    timeout -k 30s "${shard_timeout}s" python3 jobs/tools/stable_conversion_matrix.py run \
      --arm "$arm" --jass "$J" --scan "$SCAN_RUNTIME_BIN" \
      --scan-runtime-sha256 "$SCAN_RUNTIME_SHA256" \
      --g0 "$W/g0.pjtw" --g4 "$W/g4.pjtw" \
      --search-params "$SEARCH_PARAMS" --pool "$POOL" --proof "$PROOF" \
      --depth "$DEPTH" --max-plies "$MAXPLIES" --game-timeout "$GAME_TIMEOUT" \
      --shard-index "$shard" --nshards "$NSHARDS" \
      --output "$MATRIX/$arm/s${shard}.jsonl" \
      --progress-file "$MATRIX/$arm/s${shard}.progress.json" \
      > "$W/${arm}-s${shard}.log" 2>&1 &
    pids+=("$!")
    ACTIVE_PIDS=("${pids[@]}")
  done
  run_pids "$arm" "${pids[@]}"
  ACTIVE_PIDS=()
  say "arm_complete=$arm games=$POOL_POSITIONS/384"
}

for arm in "${ARMS[@]}"; do run_arm "$arm"; done
stop_monitor
[ $((SECONDS - BENCHMARK_STARTED_SECONDS)) -le "$GLOBAL_TIMEOUT" ] \
  || die "global benchmark cap exceeded"

RESULT_ARGS=()
SHARD_OUTPUT_COUNT=0
for arm in "${ARMS[@]}"; do
  for shard in $(seq 0 $((NSHARDS - 1))); do
    result="$MATRIX/$arm/s${shard}.jsonl"
    [ -s "$result" ] || die "missing/empty shard output: $arm/$shard"
    RESULT_ARGS+=(--result "$arm=$result")
    SHARD_OUTPUT_COUNT=$((SHARD_OUTPUT_COUNT+1))
  done
done
[ "$SHARD_OUTPUT_COUNT" -eq 112 ] || die "expected 112 shard outputs, got $SHARD_OUTPUT_COUNT"
python3 jobs/tools/stable_conversion_matrix.py aggregate \
  --pool "$POOL" --proof "$PROOF" "${RESULT_ARGS[@]}" \
  --run-config "$OUT/run-config.json" --expected-per-arm "$POOL_POSITIONS" \
  --bootstrap-samples "$BOOTSTRAP" --bootstrap-seed "$BOOTSTRAP_SEED" \
  --output "$OUT/stable-top3-causal-matrix.json" \
  > "$W/matrix-aggregate.log" 2>&1

python3 - "$OUT/stable-top3-causal-matrix.json" "$OUT/decision.json" "$PROG" \
  "$OUT/source-contract.json" "$OUT/run-config.json" <<'PY'
import json, sys
from pathlib import Path
p = json.load(open(sys.argv[1], encoding="utf-8"))
if p.get("status") != "ok" or p.get("gate_ready") is not True:
    raise SystemExit(f"matrix technical status is not complete: {p.get('status')}")
contract = p.get("contract", {})
if contract.get("positions") != 384 or contract.get("arms") != [
    "scan_scan", "scan_g4", "g4_scan",
    "g0_g0", "g4_g0", "g0_g4", "g4_g4"
]:
    raise SystemExit("strict 384-per-arm contract not met")
if p.get("technical_failures") or p.get("technical_rows"):
    raise SystemExit("matrix contains engine errors, caps, or provenance failures")
if p.get("errors") != 0 or p.get("game_time_caps") != 0 or p.get("ply_caps") != 0:
    raise SystemExit("matrix contains an engine error, game time cap, or ply cap")
for arm in contract["arms"]:
    if p.get("arms", {}).get(arm, {}).get("global", {}).get("n") != 384:
        raise SystemExit(f"{arm}: strict 384-game floor not met")
source = json.load(open(sys.argv[4], encoding="utf-8"))
run = json.load(open(sys.argv[5], encoding="utf-8"))
engines = p.get("inputs", {}).get("engines", {})
expected_engines = {
    "scan": run["scan"]["binary_sha256"],
    "scan_runtime": run["scan"]["runtime_sha256"],
    "scan_hub_params": run["scan"]["hub_params_sha256"],
    "g0": source["evaluated_models"]["g0_raw_sha256"],
    "g4": source["evaluated_models"]["g4_raw_sha256"],
    "search_params": source["evaluated_models"]["search_params_sha256"],
}
for name, expected in expected_engines.items():
    if engines.get(name) != expected:
        raise SystemExit(f"{name}: aggregate provenance hash mismatch")
decision = {
    "schema": 1, "decision": "CAUSAL_CONVERSION_MATRIX_READY",
    "technical_status": "complete", "games_per_arm": 384,
    "total_games": 2688, "scientific_gate_only": True,
    "training_continuation_authorized": False,
    "promotion_authorized": False, "automatic_next_job": None,
    "matrix_sha256": __import__("hashlib").sha256(Path(sys.argv[1]).read_bytes()).hexdigest(),
}
Path(sys.argv[2]).write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
Path(sys.argv[3]).write_text("completed_games=2688/2688\nstatus=complete\n", encoding="utf-8")
print("CAUSAL_CONVERSION_MATRIX_READY")
PY

tar -C "$W" -czf "$OUT/stable-top3-causal-matrix-raw.tar.gz" matrix
say "CAUSAL_CONVERSION_MATRIX_READY"
say "games=2688 arms=7 games_per_arm=384 depth=10 game_timeout=120s errors=0"
say "training_continuation_authorized=false promotion_authorized=false automatic_next_job=null"
