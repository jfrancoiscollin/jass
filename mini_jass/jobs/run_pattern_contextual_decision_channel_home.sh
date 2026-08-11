#!/usr/bin/env bash
# M15-C6 HOME entrypoint. Usage: ... probe|full
set -Eeuo pipefail

mode=${1:?expected probe or full}
repo=${JASS_CODE_DIR:?JASS_CODE_DIR is required}
job_id=${JASS_JOB_ID:?JASS_JOB_ID is required}
result_root=${JASS_RESULT_DIR:?JASS_RESULT_DIR is required}
artefact_root=${JASS_ARTEFACT_DIR:?JASS_ARTEFACT_DIR is required}
host=$(hostname)

[[ "$mode" == probe || "$mode" == full ]] || {
  echo "expected probe or full, got $mode" >&2
  exit 2
}
[[ "$job_id" == home-* && "$host" == User ]] || {
  echo "M15-C6 requires HOME (job=$job_id host=$host)" >&2
  exit 2
}
[[ "$(nproc)" -eq 16 ]] || {
  echo "M15-C6 sizing is valid only for HOME nproc=16" >&2
  exit 2
}

work="$result_root/mini-jass-pattern-m15c6-$mode"
build="$work/build"
run_dir="$work/run"
full_result="$work/result.full.json"
oracle="$repo/mini_jass/artefacts/oracle.l1.pattern-m15c6-$job_id.jsonl"
venv="${MINI_JASS_PATTERN_VENV:-/home/jf/.cache/mj-m15p-venv}"
mkdir -p "$work" "$artefact_root"
stage_file="$work/.stage"
echo start >"$stage_file"
monitor_pid=""
monitor() {
  ( started=$(date +%s)
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$stage_file" 2>/dev/null || echo unknown)"
        printf 'elapsed_seconds=%s\n' "$(( $(date +%s) - started ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$result_root" | awk 'NR==2{print $4}')"
        printf 'python=%s\n' "$venv/bin/python"
      } >"$work/PROGRESS.runtime.tmp"
      mv "$work/PROGRESS.runtime.tmp" "$work/PROGRESS.runtime.txt"
      cp "$work/PROGRESS.runtime.txt" "$artefact_root/PROGRESS.runtime.txt"
      sleep 60
    done ) >/dev/null 2>&1 &
  monitor_pid="$!"
}
cleanup() {
  rc=$?
  trap - EXIT TERM INT
  set +e
  [ -z "$monitor_pid" ] || {
    kill "$monitor_pid" 2>/dev/null
    wait "$monitor_pid" 2>/dev/null
  }
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

# Build, oracle, per-seed reports and runner publication stay below this guard.
available_kib=$(df -Pk "$result_root" | awk 'NR==2 {print $4}')
[[ "$available_kib" -ge 10485760 ]] || {
  echo "M15-C6 disk guard: ${available_kib} KiB available, need 10485760" >&2
  exit 3
}
[[ -x "$venv/bin/python" ]] || {
  echo "persistent HOME venv missing: $venv" >&2
  exit 4
}
python_bin="$venv/bin/python"
"$python_bin" -c 'import numpy, pytest, torch, yaml' || {
  echo "persistent HOME venv is incomplete; this job never reinstalls PyTorch" >&2
  exit 4
}

phase_log="$work/phase_timings.txt"
: >"$phase_log"
phase_start=$(date +%s)
phase() {
  local now
  now=$(date +%s)
  echo "$1=$((now - phase_start))" >>"$phase_log"
  echo "$1" >"$stage_file"
  phase_start=$now
}

monitor
cmake -S "$repo/mini_jass" -B "$build" \
  -DCMAKE_BUILD_TYPE=Release -DMINI_JASS_BUILD_TESTS=ON
cmake --build "$build" --parallel 16
ctest --test-dir "$build" --output-on-failure
phase build_and_ctest

export PYTHONPATH="$repo/mini_jass/python"
"$python_bin" -m pytest "$repo/mini_jass/tests/python"
phase pytest
"$python_bin" "$repo/mini_jass/tools/export_oracle.py" \
  --level l1 --executable "$build/mini_jass_cli" --output "$oracle"
phase oracle_export_l1

extra=(--progress-output "$artefact_root/PROGRESS.json")
timeout_seconds=10800
if [[ "$mode" == probe ]]; then
  extra+=(--probe-only)
  timeout_seconds=3600
fi
timeout -k 60s "${timeout_seconds}s" \
  "$python_bin" "$repo/mini_jass/tools/run_pattern_contextual_decision_channel.py" \
    --config "$repo/mini_jass/configs/l1_pattern_contextual_decision_channel.yaml" \
    --oracle "$oracle" --run-dir "$run_dir" \
    --compact-output "$full_result" --execution-host "$host" \
    "${extra[@]}"
phase "m15c6_$mode"

cp "$full_result" "$artefact_root/result.full.json"
cp "$phase_log" "$artefact_root/PHASE_TIMINGS.txt"
"$python_bin" - "$full_result" "$artefact_root" "$mode" <<'PY'
import json
from pathlib import Path
import sys

full = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
out = Path(sys.argv[2])
mode = sys.argv[3]
if mode == "probe":
    if full.get("status") != "TIMING_ONLY" or full.get("scientific_metrics_published") is not False:
        raise SystemExit("invalid M15-C6 timing probe")
    summary = full
    lines = [
        "cell=m15c6probe",
        f"status={full['status']}",
        f"result_hash={full['result_hash']}",
        f"seed={full['seed']}",
        f"total_seconds={full['timing']['total_seconds']}",
        f"decision_activation_count={full['activation_contract']['decision_activation_count']}",
        "scientific_metrics_published=false",
        "promotable=false",
    ]
else:
    if int(full.get("aggregate", {}).get("paired_seed_count", 0)) == 0:
        raise SystemExit("M15-C6 n=0 is a hard failure")
    summary = {
        "schema": full["schema"],
        "milestone": full["milestone"],
        "status": full["status"],
        "protocol_hash": full["protocol_hash"],
        "result_hash": full["result_hash"],
        "aggregate": full["aggregate"],
        "recommendation": full["recommendation"],
        "sealed_cohort_contract": full["sealed_cohort_contract"],
        "promotable": False,
    }
    lines = [
        "cell=m15c6",
        f"status={full['status']}",
        f"result_hash={full['result_hash']}",
        f"finding={full['recommendation']['finding']}",
        f"n={full['aggregate']['paired_seed_count']}",
        f"aligned_minus_shuffled={full['recommendation']['aligned_minus_shuffled_mean']}",
        f"aligned_minus_lambda={full['recommendation']['aligned_minus_lambda_mean']}",
        "promotable=false",
    ]
(out / "scientific-summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
(out / "RESULTS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
if (out / "scientific-summary.json").stat().st_size > 65536:
    raise SystemExit("scientific-summary.json exceeds 64 KiB")
json.loads((out / "scientific-summary.json").read_text(encoding="utf-8"))
PY
phase reporting_smoke
