#!/usr/bin/env bash
# C0-only verification for contextual supervision. This job never trains C1.
set -Eeuo pipefail

repo=${JASS_CODE_DIR:?JASS_CODE_DIR is required}
job_id=${JASS_JOB_ID:?JASS_JOB_ID is required}
result_root=${JASS_RESULT_DIR:?JASS_RESULT_DIR is required}
artefact_root=${JASS_ARTEFACT_DIR:?JASS_ARTEFACT_DIR is required}
host=$(hostname)

if [[ "$job_id" != cpx62-* || "$host" != cpx62 ]]; then
  echo "contextual C0 requires cpx62 (job=$job_id host=$host)" >&2
  exit 2
fi

work="$result_root/mini-jass-contextual-c0"
build="$work/build"
venv="$work/venv"
oracle="$repo/mini_jass/artefacts/oracle.contextual-c0-$job_id.jsonl"
report="$work/contextual-c0.full.json"
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
  "$repo/mini_jass/tests/python/test_context_power.py" \
  "$repo/mini_jass/tests/python/test_context_scaffold.py"
phase contextual_pytest

"$python_bin" "$repo/mini_jass/tools/export_oracle.py" \
  --level l1 --executable "$build/mini_jass_cli" --output "$oracle"
phase oracle_export_l1

timeout -k 60s 3600s \
  "$python_bin" "$repo/mini_jass/tools/run_contextual_outcome_supervision.py" \
    --config "$repo/mini_jass/configs/contextual_outcome_supervision.yaml" \
    --oracle "$oracle" --output "$report"
phase contextual_c0

cp "$report" "$artefact_root/scientific-summary.json"
cp "$report" "$artefact_root/contextual-c0.full.json"
cp "$phase_log" "$artefact_root/PHASE_TIMINGS.txt"

"$python_bin" - "$report" "$artefact_root/RESULTS.txt" <<'PY'
import json
from pathlib import Path
import sys

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
lines = [
    "milestone=C0",
    f"status={report['status']}",
    f"report_hash={report['report_hash']}",
    f"spearman={report['checks']['baseline_spearman_vs_exact_value']}",
    f"ordering_rate={report['checks']['baseline_pairwise_ordering_rate']}",
    "value_error="
    + str(report['implementation_proof']['maximum_absolute_value_error']),
    "action_match_rate="
    + str(report['implementation_proof']['common_search_action_match_rate']),
    f"c1_training_authorized={str(report['c1_training_authorized']).lower()}",
]
Path(sys.argv[2]).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

summary_bytes=$(stat -c %s "$artefact_root/scientific-summary.json")
if [[ "$summary_bytes" -gt 65536 ]]; then
  echo "scientific-summary.json exceeds 64 KiB: $summary_bytes" >&2
  exit 6
fi
