#!/usr/bin/env bash
# Architecture-correct reconstruction cells. Prepare one CPX job per cell:
#   run_pattern_reconstruction_cpx.sh m24p|m14p|m15p|m15c|m15c2|m17p|m17p2|m17p2r|m18p|m21p
#
# This entrypoint deliberately does not choose the order.  M24-P is the first
# scientific read; M14-P and M17-P are launched only after its interpretation.
set -Eeuo pipefail

cell=${1:?expected one of: m24p, m14p, m15p, m15c, m15c2, m17p, m17p2, m17p2r, m18p, m21p}
repo=${JASS_CODE_DIR:?JASS_CODE_DIR is required}
job_id=${JASS_JOB_ID:?JASS_JOB_ID is required}
result_root=${JASS_RESULT_DIR:?JASS_RESULT_DIR is required}
artefact_root=${JASS_ARTEFACT_DIR:?JASS_ARTEFACT_DIR is required}
host=$(hostname)

if [[ "$job_id" != cpx62-* || "$host" != cpx62 ]]; then
  echo "pattern reconstruction requires cpx62 (job=$job_id host=$host)" >&2
  exit 2
fi

case "$cell" in
  m24p)
    tool=run_pattern_supervised_ceiling.py
    config=l1_pattern_supervised_ceiling.yaml
    timeout_seconds=14400
    ;;
  m14p)
    tool=run_pattern_value_target_ablation.py
    config=l1_pattern_value_target_ablation.yaml
    timeout_seconds=21600
    ;;
  m15p)
    tool=run_pattern_value_target_screen.py
    config=l1_pattern_value_target_screen.yaml
    timeout_seconds=21600
    ;;
  m15c)
    tool=run_pattern_conditional_target_screen.py
    config=l1_pattern_conditional_target_screen.yaml
    timeout_seconds=28800
    ;;
  m15c2)
    tool=run_pattern_conditional_dose_screen.py
    config=l1_pattern_conditional_dose_screen.yaml
    timeout_seconds=43200
    ;;
  m17p)
    tool=run_pattern_generation_ladder.py
    config=l1_pattern_generation_ladder.yaml
    timeout_seconds=43200
    ;;
  m17p2)
    tool=run_pattern_generation_ladder.py
    config=l1_pattern_generation_ladder_v2.yaml
    timeout_seconds=43200
    ;;
  m17p2r)
    tool=run_pattern_generation_ladder.py
    config=l1_pattern_generation_ladder_replication.yaml
    timeout_seconds=43200
    ;;
  m18p)
    tool=run_pattern_state_distribution_decomposition.py
    config=l1_pattern_state_distribution_decomposition.yaml
    timeout_seconds=43200
    ;;
  m21p)
    tool=run_pattern_learning_signal_composition.py
    config=l1_pattern_learning_signal_composition.yaml
    timeout_seconds=43200
    ;;
  *)
    echo "unknown reconstruction cell: $cell" >&2
    exit 2
    ;;
esac

work="$result_root/mini-jass-pattern-reconstruction-$cell"
build="$work/build"
venv="$work/venv"
run_dir="$work/run"
full_result="$work/result.full.json"
oracle="$repo/mini_jass/artefacts/oracle.l1.pattern-reconstruction-$job_id.jsonl"
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
"$python_bin" -m pytest "$repo/mini_jass/tests/python"
phase pytest

"$python_bin" "$repo/mini_jass/tools/export_oracle.py" \
  --level l1 --executable "$build/mini_jass_cli" --output "$oracle"
phase oracle_export_l1

extra_args=()
if [[ "$cell" == "m15p" || "$cell" == "m15c" || "$cell" == "m15c2" || "$cell" == "m18p" || "$cell" == "m21p" ]]; then
  extra_args+=(--progress-output "$artefact_root/PROGRESS.json")
fi
timeout -k 60s "${timeout_seconds}s" \
  "$python_bin" "$repo/mini_jass/tools/$tool" \
    --config "$repo/mini_jass/configs/$config" \
    --oracle "$oracle" --run-dir "$run_dir" \
    --compact-output "$full_result" --execution-host "$host" \
    "${extra_args[@]}"
phase "$cell"

cp "$full_result" "$artefact_root/result.full.json"
cp "$phase_log" "$artefact_root/PHASE_TIMINGS.txt"

# The runner-facing summary remains bounded even when 20 paired seed rows are
# retained in result.full.json for audit.
"$python_bin" - "$full_result" "$artefact_root" "$cell" <<'PY'
import json
from pathlib import Path
import sys

full = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
out = Path(sys.argv[2])
cell = sys.argv[3]
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
(out / "scientific-summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
lines = [
    f"cell={cell}",
    f"milestone={summary['milestone']}",
    f"status={summary['status']}",
    f"protocol_hash={summary['protocol_hash']}",
    f"result_hash={summary['result_hash']}",
    f"finding={summary['recommendation']['finding']}",
    f"promotable={str(summary['promotable']).lower()}",
]
(out / "RESULTS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

summary_bytes=$(stat -c %s "$artefact_root/scientific-summary.json")
if [[ "$summary_bytes" -gt 65536 ]]; then
  echo "scientific-summary.json exceeds 64 KiB: $summary_bytes" >&2
  exit 6
fi
