#!/usr/bin/env bash
set -Eeuo pipefail

repo=${JASS_CODE_DIR:?JASS_CODE_DIR is required}
job_id=${JASS_JOB_ID:?JASS_JOB_ID is required}
result_root=${JASS_RESULT_DIR:?JASS_RESULT_DIR is required}
artefact_root=${JASS_ARTEFACT_DIR:?JASS_ARTEFACT_DIR is required}
host=$(hostname)

if [[ "$job_id" != cpx62-* ]]; then
  echo "M18 requires a cpx62-routed job id, got: $job_id" >&2
  exit 2
fi
if [[ "$host" != cpx62 ]]; then
  echo "M18 requires host cpx62, got: $host" >&2
  exit 2
fi

work="$result_root/mini-jass-m18-work"
build="$work/build"
venv="$work/venv"
local_artefacts="$repo/mini_jass/artefacts"
oracle="$local_artefacts/oracle.l1.m18-cpx.jsonl"
run_dir="$local_artefacts/runs/m18-wdl-policy-iteration-microscope-cpx"
summary="$local_artefacts/m18_wdl_policy_iteration_microscope.cpx.json"
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
  --level l1 \
  --executable "$build/mini_jass_cli" \
  --output "$oracle"
"$python_bin" "$repo/mini_jass/tools/run_wdl_policy_iteration_microscope.py" \
  --config "$repo/mini_jass/configs/l1_wdl_policy_iteration_microscope.yaml" \
  --oracle "$oracle" \
  --run-dir "$run_dir" \
  --compact-output "$summary" \
  --execution-host "$host"

cp "$summary" "$artefact_root/scientific-summary.json"
cp -R "$run_dir" "$artefact_root/m18-wdl-policy-iteration-microscope-run"

"$python_bin" - "$artefact_root/scientific-summary.json" \
  "$artefact_root/RESULTS.txt" <<'PY'
import json
from pathlib import Path
import sys

s = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
a = s["aggregate"]
c = a["contrasts"]
e = a["arms"]["evolving_arena_gate"]
r = s["recommendation"]
lines = [
    f"milestone={s['milestone']}",
    f"status={s['status']}",
    f"finding={r['finding']}",
    f"result_hash={s['result_hash']}",
    f"execution_host={a['execution']['execution_host']}",
    f"mean_advancing_generations={e['mean_advancing_generations']}",
    f"evolving_probe_exact_g0={e['mean_probe_start_exact_rate_by_rung']['0']}",
    f"evolving_probe_exact_g8={e['mean_probe_start_exact_rate_by_rung']['8']}",
    f"loop_gain={c['evolving_g8_minus_g0']['mean']}",
    f"loop_gain_ci95={c['evolving_g8_minus_g0']['confidence_95']}",
    f"feedback_gain={c['evolving_gain_minus_frozen_gain']['mean']}",
    f"feedback_gain_ci95={c['evolving_gain_minus_frozen_gain']['confidence_95']}",
    f"search_gain={c['evolving_gain_minus_shallow_gain']['mean']}",
    f"search_gain_ci95={c['evolving_gain_minus_shallow_gain']['confidence_95']}",
    f"gate_gain={c['evolving_gain_minus_forced_gain']['mean']}",
    f"final_arena_score_vs_initial={e['mean_final_arena_score_vs_initial']}",
    f"loop_is_virtuous={r['loop_is_virtuous']}",
    f"generator_feedback_is_causal={r['generator_feedback_is_causal']}",
    f"search_is_cliquet={r['search_is_cliquet']}",
    "oracle_used_for_training=false",
    "oracle_used_for_generation=false",
    "oracle_used_for_promotion=false",
    "m18_promotable=false",
    "direct_10x10_transfer_authorized=false",
]
Path(sys.argv[2]).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
