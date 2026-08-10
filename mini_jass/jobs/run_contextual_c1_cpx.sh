#!/usr/bin/env bash
# C1-only contextual training. C2 and frozen_test remain sealed.
set -Eeuo pipefail

repo=${JASS_CODE_DIR:?JASS_CODE_DIR is required}
job_id=${JASS_JOB_ID:?JASS_JOB_ID is required}
result_root=${JASS_RESULT_DIR:?JASS_RESULT_DIR is required}
artefact_root=${JASS_ARTEFACT_DIR:?JASS_ARTEFACT_DIR is required}
implementation_sha=${CONTEXTUAL_C1_IMPLEMENTATION_SHA:?CONTEXTUAL_C1_IMPLEMENTATION_SHA is required}
host=$(hostname)

if [[ "$job_id" != cpx62-* || "$host" != cpx62 ]]; then
  echo "contextual C1 requires cpx62 (job=$job_id host=$host)" >&2
  exit 2
fi
if [[ ! "$implementation_sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "CONTEXTUAL_C1_IMPLEMENTATION_SHA must be a full Git SHA" >&2
  exit 3
fi
actual_sha=$(git -C "$repo" rev-parse HEAD)
if [[ "$actual_sha" != "$implementation_sha" ]]; then
  echo "contextual C1 implementation mismatch: $actual_sha != $implementation_sha" >&2
  exit 4
fi

work="$result_root/mini-jass-contextual-c1"
build="$work/build"
venv="$work/venv"
oracle="$repo/mini_jass/artefacts/oracle.contextual-c1-$job_id.jsonl"
run_dir="$work/result"
compact="$work/scientific-summary.json"
progress="$work/progress.json"
mkdir -p "$work" "$run_dir" "$artefact_root"

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
  "$repo/mini_jass/tests/python/test_context_power.py" \
  "$repo/mini_jass/tests/python/test_context_scaffold.py" \
  "$repo/mini_jass/tests/python/test_context_training.py" \
  "$repo/mini_jass/tests/python/test_pattern_reconstruction_program.py"
phase contextual_pytest

"$python_bin" "$repo/mini_jass/tools/export_oracle.py" \
  --level l1 --executable "$build/mini_jass_cli" --output "$oracle"
phase oracle_export_l1

timeout -k 120s 21600s \
  "$python_bin" "$repo/mini_jass/tools/run_contextual_c1.py" \
    --config "$repo/mini_jass/configs/contextual_outcome_supervision.yaml" \
    --oracle "$oracle" --run-dir "$run_dir" --compact-output "$compact" \
    --progress-output "$progress" --execution-host "$host" \
    --implementation-sha "$implementation_sha"
phase contextual_c1

cp "$compact" "$artefact_root/scientific-summary.json"
cp "$run_dir/result.full.json" "$artefact_root/contextual-c1.full.json"
cp "$run_dir/replay-start-manifest.json" "$artefact_root/"
cp "$run_dir/arena-start-manifest.json" "$artefact_root/"
tar -C "$run_dir" -czf "$artefact_root/contextual-c1-checkpoints.tgz" checkpoints
cp "$progress" "$artefact_root/PROGRESS.json"
cp "$phase_log" "$artefact_root/PHASE_TIMINGS.txt"
printf '%s\n' "$implementation_sha" >"$artefact_root/IMPLEMENTATION_SHA.txt"

"$python_bin" - "$compact" "$artefact_root/RESULTS.txt" <<'PY'
import json
from pathlib import Path
import sys

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
primary = report["aggregate"]["primary_common_search_arena_score"]
lines = [
    "milestone=C1",
    f"status={report['status']}",
    f"protocol_hash={report['protocol_hash']}",
    f"result_hash={report['result_hash']}",
    f"primary_mean={primary['mean']}",
    f"primary_ci95_lower={primary['lower']}",
    f"primary_ci95_upper={primary['upper']}",
    "c2_required=true",
    "sealed_test_read=false",
]
Path(sys.argv[2]).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

summary_bytes=$(stat -c %s "$artefact_root/scientific-summary.json")
if [[ "$summary_bytes" -gt 65536 ]]; then
  echo "scientific-summary.json exceeds 64 KiB: $summary_bytes" >&2
  exit 6
fi
