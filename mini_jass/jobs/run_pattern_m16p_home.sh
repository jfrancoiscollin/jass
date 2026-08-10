#!/usr/bin/env bash
# HOME entrypoint for the architecture-correct M16-P cell and its timing probe.
set -Eeuo pipefail

mode=${1:-full}
if [[ "$mode" != "full" && "$mode" != "probe" ]]; then
  echo "expected M16-P mode full or probe, got: $mode" >&2
  exit 2
fi

repo=${JASS_CODE_DIR:?JASS_CODE_DIR is required}
job_id=${JASS_JOB_ID:?JASS_JOB_ID is required}
result_root=${JASS_RESULT_DIR:?JASS_RESULT_DIR is required}
artefact_root=${JASS_ARTEFACT_DIR:?JASS_ARTEFACT_DIR is required}
host=$(hostname)

if [[ "$job_id" != home-* || "$host" != "User" ]]; then
  echo "M16-P requires HOME (job=$job_id host=$host)" >&2
  exit 2
fi

work="$result_root/mini-jass-pattern-m16p-$mode"
build="$work/build"
run_dir="$work/run"
full_result="$work/result.full.json"
oracle="$repo/mini_jass/artefacts/oracle.l1.pattern-m16p-$job_id.jsonl"
venv="/home/jf/.cache/mj-m15p-venv"
mkdir -p "$work" "$artefact_root"

phase_log="$work/phase_timings.txt"
: >"$phase_log"
phase_start=$(date +%s)
phase() {
  local now
  now=$(date +%s)
  echo "$1=$((now - phase_start))" >>"$phase_log"
  phase_start=$now
}

cmake -S "$repo/mini_jass" -B "$build" \
  -DCMAKE_BUILD_TYPE=Release -DMINI_JASS_BUILD_TESTS=ON
cmake --build "$build" --parallel "$(nproc)"
ctest --test-dir "$build" --output-on-failure
phase build_and_ctest

if [[ ! -x "$venv/bin/python" ]]; then
  echo "persistent HOME venv missing: $venv" >&2
  exit 3
fi
python_bin="$venv/bin/python"
"$python_bin" -c 'import numpy, pytest, torch, yaml'
phase persistent_venv_check

export PYTHONPATH="$repo/mini_jass/python"
"$python_bin" -m pytest "$repo/mini_jass/tests/python"
phase pytest

"$python_bin" "$repo/mini_jass/tools/export_oracle.py" \
  --level l1 --executable "$build/mini_jass_cli" --output "$oracle"
phase oracle_export_l1

extra_args=(--progress-output "$artefact_root/PROGRESS.json")
if [[ "$mode" == "probe" ]]; then
  extra_args=(--probe-only)
fi
"$python_bin" "$repo/mini_jass/tools/run_pattern_temporal_value_target_screen.py" \
  --config "$repo/mini_jass/configs/l1_pattern_temporal_value_target_screen.yaml" \
  --oracle "$oracle" --run-dir "$run_dir" \
  --compact-output "$full_result" --execution-host "$host" \
  "${extra_args[@]}"
phase "m16p_$mode"

cp "$phase_log" "$artefact_root/PHASE_TIMINGS.txt"
cp "$full_result" "$artefact_root/result.full.json"

"$python_bin" - "$full_result" "$artefact_root" "$mode" <<'PY'
import json
from pathlib import Path
import sys

full = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
out = Path(sys.argv[2])
mode = sys.argv[3]
if mode == "probe":
    summary = full
    lines = [
        "cell=m16p-probe",
        f"status={full['status']}",
        f"result_hash={full['result_hash']}",
        f"seed={full['seed']}",
        f"total_seconds={full['timing']['total_seconds']}",
        f"generation_seconds={full['timing']['generation_seconds']}",
        f"training_and_response_seconds={full['timing']['training_and_response_seconds']}",
        f"arena_seconds={full['timing']['arena_seconds']}",
        f"train_sample_count={full['workload']['train_sample_count']}",
        "scientific_metrics_published=false",
        "promotable=false",
    ]
else:
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
        "cell=m16p",
        f"status={full['status']}",
        f"protocol_hash={full['protocol_hash']}",
        f"result_hash={full['result_hash']}",
        f"finding={full['recommendation']['finding']}",
        f"primary_mean={full['recommendation']['primary_mean']}",
        f"primary_ci95={full['recommendation']['primary_ci95']}",
        f"oracle_gap_mean={full['recommendation']['oracle_gap_mean']}",
        f"required_primary_mean={full['recommendation']['required_primary_mean']}",
        "promotable=false",
    ]
(out / "scientific-summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
(out / "RESULTS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

summary_bytes=$(stat -c %s "$artefact_root/scientific-summary.json")
if [[ "$summary_bytes" -gt 65536 ]]; then
  echo "scientific-summary.json exceeds 64 KiB: $summary_bytes" >&2
  exit 6
fi
