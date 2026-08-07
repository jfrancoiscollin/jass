#!/usr/bin/env bash
set -euo pipefail

repo=${JASS_CODE_DIR:?JASS_CODE_DIR is required}
job_id=${JASS_JOB_ID:?JASS_JOB_ID is required}
result_root=${JASS_RESULT_DIR:?JASS_RESULT_DIR is required}
artefact_root=${JASS_ARTEFACT_DIR:?JASS_ARTEFACT_DIR is required}
host=$(hostname)

if [[ "$job_id" != cpx62-* ]]; then
  echo "M13 requires a cpx62-routed job id, got: $job_id" >&2
  exit 2
fi
if [[ "$host" != cpx62 ]]; then
  echo "M13 requires host cpx62, got: $host" >&2
  exit 2
fi

work="$result_root/mini-jass-m13-work"
build="$work/build"
venv="$work/venv"
local_artefacts="$repo/mini_jass/artefacts"
oracle="$local_artefacts/oracle.l2.m13-cpx.jsonl"
run_dir="$local_artefacts/runs/m13-seed-variance-cpx"
summary="$local_artefacts/m13_seed_variance_replication.cpx.json"
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
"$python_bin" "$repo/mini_jass/tools/run_seed_variance_replication.py" \
  --config "$repo/mini_jass/configs/l2_seed_variance_replication.yaml" \
  --oracle "$oracle" \
  --run-dir "$run_dir" \
  --compact-output "$summary" \
  --execution-host "$host"

cp "$summary" "$artefact_root/scientific-summary.json"
cp -R "$run_dir" "$artefact_root/m13-seed-variance-run"

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
    f"protocol_hash={summary['protocol_hash']}",
    f"execution_host={summary['contracts']['execution_host']}",
    f"decision={summary['recommendation']['decision']}",
]
Path(sys.argv[2]).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
