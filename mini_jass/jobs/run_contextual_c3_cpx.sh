#!/usr/bin/env bash
# Train-only C3 baseline diagnostic. Never reads development or frozen_test.
set -Eeuo pipefail

repo=${JASS_CODE_DIR:?JASS_CODE_DIR is required}
job_id=${JASS_JOB_ID:?JASS_JOB_ID is required}
result_root=${JASS_RESULT_DIR:?JASS_RESULT_DIR is required}
artefact_root=${JASS_ARTEFACT_DIR:?JASS_ARTEFACT_DIR is required}
implementation_sha=${CONTEXTUAL_C3_IMPLEMENTATION_SHA:?CONTEXTUAL_C3_IMPLEMENTATION_SHA is required}
sealed_result=${CONTEXTUAL_SEALED_RESULT_PATH:?CONTEXTUAL_SEALED_RESULT_PATH is required}
host=$(hostname)

if [[ "$job_id" != cpx62-* || "$host" != cpx62 ]]; then
  echo "contextual C3 requires cpx62 (job=$job_id host=$host)" >&2
  exit 2
fi
if [[ ! "$implementation_sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "CONTEXTUAL_C3_IMPLEMENTATION_SHA must be a full Git SHA" >&2
  exit 3
fi
actual_sha=$(git -C "$repo" rev-parse HEAD)
if [[ "$actual_sha" != "$implementation_sha" ]]; then
  echo "C3 implementation mismatch: $actual_sha != $implementation_sha" >&2
  exit 4
fi
if [[ ! -f "$sealed_result" ]]; then
  echo "missing frozen sealed-result prerequisite: $sealed_result" >&2
  exit 5
fi

work="$result_root/mini-jass-contextual-c3"
build="$work/build"
venv="$work/venv"
oracle="$repo/mini_jass/artefacts/oracle.contextual-c3-$job_id.jsonl"
report="$work/contextual-c3.full.json"
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

python3 -m venv --system-site-packages "$venv"
python_bin="$venv/bin/python"
if ! "$python_bin" -c 'import torch' >/dev/null 2>&1; then
  "$python_bin" -m pip install --index-url https://download.pytorch.org/whl/cpu \
    'torch==2.13.0'
fi
if ! "$python_bin" -c 'import numpy, pytest, yaml' >/dev/null 2>&1; then
  "$python_bin" -m pip install 'numpy>=1.26,<3' 'PyYAML>=6,<7' 'pytest>=8,<10'
fi
phase venv_and_dependencies

export PYTHONPATH="$repo/mini_jass/python"
"$python_bin" -m pytest \
  "$repo/mini_jass/tests/python/test_context.py" \
  "$repo/mini_jass/tests/python/test_context_c3.py" \
  "$repo/mini_jass/tests/python/test_context_power.py"
phase contextual_pytest

"$python_bin" "$repo/mini_jass/tools/export_oracle.py" \
  --level l1 --executable "$build/mini_jass_cli" --output "$oracle"
phase oracle_export_l1

timeout -k 60s 3600s \
  "$python_bin" "$repo/mini_jass/tools/run_contextual_c3.py" \
    --config "$repo/mini_jass/configs/contextual_outcome_supervision.yaml" \
    --oracle "$oracle" --sealed-result "$sealed_result" --output "$report" \
    --implementation-sha "$implementation_sha" --execution-host "$host"
phase contextual_c3

cp "$report" "$artefact_root/scientific-summary.json"
cp "$report" "$artefact_root/contextual-c3.full.json"
cp "$phase_log" "$artefact_root/PHASE_TIMINGS.txt"
printf '%s\n' "$implementation_sha" >"$artefact_root/IMPLEMENTATION_SHA.txt"

"$python_bin" - "$report" "$artefact_root/RESULTS.txt" <<'PY'
import json
from pathlib import Path
import sys

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
fitted = report["fitted_gain"]
lookup = report["lookup_gain"]
lines = [
    "milestone=CONTEXTUAL_C3",
    f"status={report['status']}",
    f"protocol_hash={report['protocol_hash']}",
    f"result_hash={report['result_hash']}",
    f"interpretation={report['interpretation']}",
    f"fitted_spearman_gain={fitted['spearman_gain']}",
    f"fitted_mae_reduction={fitted['mae_reduction']}",
    f"lookup_spearman_gain={lookup['spearman_gain']}",
    f"lookup_mae_reduction={lookup['mae_reduction']}",
    "train_only=true",
    "sealed_test_read_count_added=0",
    "decision_reopened=false",
    "promotable=false",
]
Path(sys.argv[2]).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

summary_bytes=$(stat -c %s "$artefact_root/scientific-summary.json")
if [[ "$summary_bytes" -gt 65536 ]]; then
  echo "scientific-summary.json exceeds 64 KiB: $summary_bytes" >&2
  exit 6
fi
