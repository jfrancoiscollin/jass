#!/usr/bin/env bash
set -euo pipefail

repo=${JASS_CODE_DIR:?JASS_CODE_DIR is required}
job_id=${JASS_JOB_ID:?JASS_JOB_ID is required}
result_root=${JASS_RESULT_DIR:?JASS_RESULT_DIR is required}
artefact_root=${JASS_ARTEFACT_DIR:?JASS_ARTEFACT_DIR is required}
host=$(hostname)

if [[ "$job_id" != cpx62-* ]]; then
  echo "M15 requires a cpx62-routed job id, got: $job_id" >&2
  exit 2
fi
if [[ "$host" != cpx62 ]]; then
  echo "M15 requires host cpx62, got: $host" >&2
  exit 2
fi

work="$result_root/mini-jass-m15-work"
build="$work/build"
venv="$work/venv"
local_artefacts="$repo/mini_jass/artefacts"
oracle="$local_artefacts/oracle.l2.m15-cpx.jsonl"
run_dir="$local_artefacts/runs/m15-search-value-target-screen-cpx"
summary="$local_artefacts/m15_search_value_target_screen.cpx.json"
mkdir -p "$work" "$artefact_root"

cmake -S "$repo/mini_jass" -B "$build" \
  -DCMAKE_BUILD_TYPE=Release \
  -DMINI_JASS_BUILD_TESTS=ON
cmake --build "$build" --parallel 16
ctest --test-dir "$build" --output-on-failure

python3 -m venv --system-site-packages "$venv"
python_bin="$venv/bin/python"
if ! "$python_bin" -c 'import torch' >/dev/null 2>&1; then
  "$python_bin" -m pip install \
    --index-url https://download.pytorch.org/whl/cpu \
    'torch==2.13.0'
fi
if ! "$python_bin" -c 'import numpy, pytest, yaml' >/dev/null 2>&1; then
  "$python_bin" -m pip install \
    'numpy>=1.26,<3' 'PyYAML>=6,<7' 'pytest>=8,<10'
fi

export PYTHONPATH="$repo/mini_jass/python"
"$python_bin" -m pytest "$repo/mini_jass/tests/python"
"$python_bin" "$repo/mini_jass/tools/export_oracle.py" \
  --level l2 \
  --executable "$build/mini_jass_cli" \
  --output "$oracle"
"$python_bin" "$repo/mini_jass/tools/run_m15_search_value_target_screen.py" \
  --config "$repo/mini_jass/configs/l2_search_value_target_screen.yaml" \
  --oracle "$oracle" \
  --run-dir "$run_dir" \
  --compact-output "$summary" \
  --execution-host "$host"

cp "$summary" "$artefact_root/scientific-summary.json"
cp -R "$run_dir" "$artefact_root/m15-search-value-target-screen-run"

"$python_bin" - "$artefact_root/scientific-summary.json" \
  "$artefact_root/RESULTS.txt" <<'PY'
import json
from pathlib import Path
import sys

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
lines = [
    f"milestone={summary['milestone']}",
    f"status={summary['status']}",
    f"result_hash={summary['result_hash']}",
    f"execution_host={summary['contracts']['execution_host']}",
    f"selected_mechanism={summary['selected_mechanism']}",
    f"oracle_confirmation_gain={summary['oracle_upper_bound_gain']['confirmation_value_sign']}",
]
for arm in ("search", "blend"):
    row = summary["feasible_target_results"][arm]
    delta = row["contrast_vs_baseline"]
    lines.extend([
        f"{arm}_scientific_pass={str(row['scientific_pass']).lower()}",
        f"{arm}_oracle_recovery_fraction={row['oracle_gain_recovery_fraction']}",
        f"{arm}_confirmation_value_gain={delta['mean_confirmation_value_sign_delta']}",
        f"{arm}_development_value_gain={delta['mean_development_value_sign_delta']}",
        f"{arm}_confirmation_policy_shift={delta['mean_confirmation_optimal_mass_delta']}",
        f"{arm}_target_value_mae_shift={delta['mean_target_value_mae']}",
    ])
lines.extend([
    "m15_arms_promotable=false",
    "direct_10x10_transfer_authorized=false",
])
Path(sys.argv[2]).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
