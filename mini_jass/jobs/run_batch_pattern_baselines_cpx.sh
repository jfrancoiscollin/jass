#!/usr/bin/env bash
# BATCH — baseline PatternEval supervise exact + baseline self-play WDL.
#
# Les deux cellules valident le cablage de l'architecture production-like
# (patterns plies, valeur seule, actions par recherche). Elles ne sont ni une
# porte de promotion ni une autorisation de transfert vers le Jass 10x10.
set -Eeuo pipefail

repo=${JASS_CODE_DIR:?JASS_CODE_DIR is required}
job_id=${JASS_JOB_ID:?JASS_JOB_ID is required}
result_root=${JASS_RESULT_DIR:?JASS_RESULT_DIR is required}
artefact_root=${JASS_ARTEFACT_DIR:?JASS_ARTEFACT_DIR is required}
host=$(hostname)

if [[ "$job_id" != cpx62-* ]]; then
  echo "batch requires a cpx62-routed job id, got: $job_id" >&2
  exit 2
fi
if [[ "$host" != cpx62 ]]; then
  echo "batch requires host cpx62, got: $host" >&2
  exit 2
fi

work="$result_root/mini-jass-pattern-baselines"
build="$work/build"
venv="$work/venv"
local_artefacts="$repo/mini_jass/artefacts"
oracle="$local_artefacts/oracle.l1.pattern-baselines-cpx.jsonl"
exact_run="$local_artefacts/runs/l1-pattern-exact-supervised-cpx"
selfplay_run="$local_artefacts/runs/l1-pattern-outcome-selfplay-cpx"
mkdir -p "$work" "$artefact_root"

# Garde disque obligatoire du runner. Seuls les scratch cw-* abandonnes depuis
# plus de trois heures sont nettoyes ; le scratch courant n'est jamais vise.
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 \
  ! -path "$work" -exec rm -rf {} + 2>/dev/null || true
free_mb=$(df -Pm /root | awk 'NR==2 {print $4}')
if [[ "${free_mb:-0}" -le 3000 ]]; then
  echo "ABORT disk: less than 3 GiB free under /root" >&2
  exit 3
fi

phase_log="$work/phase_timings.txt"
: >"$phase_log"
job_start=$(date +%s)
phase_start=$job_start
phase() {
  local now
  now=$(date +%s)
  echo "$1=$((now - phase_start))" >>"$phase_log"
  phase_start=$now
}

on_failure() {
  local rc=$?
  [[ $rc -eq 0 ]] && return 0
  {
    echo "exit_code=$rc"
    echo "cells_completed:"
    ls -1 "$artefact_root"/cell-*.json 2>/dev/null || echo "  (none)"
    echo "phases:"
    cat "$phase_log" 2>/dev/null || echo "  (none)"
  } >"$artefact_root/FAILURE.txt" 2>/dev/null || true
  return $rc
}
trap on_failure EXIT

cpu_count=$(nproc)
echo "nproc=$cpu_count" >"$artefact_root/RUNTIME.txt"
echo "free_mb_at_start=$free_mb" >>"$artefact_root/RUNTIME.txt"

cmake -S "$repo/mini_jass" -B "$build" \
  -DCMAKE_BUILD_TYPE=Release -DMINI_JASS_BUILD_TESTS=ON
cmake --build "$build" --parallel "$cpu_count"
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
phase venv_and_pip

export PYTHONPATH="$repo/mini_jass/python"
"$python_bin" -m pytest "$repo/mini_jass/tests/python"
phase pytest

"$python_bin" "$repo/mini_jass/tools/export_oracle.py" \
  --level l1 --executable "$build/mini_jass_cli" --output "$oracle"
phase oracle_export_l1

# Cellule 1 : capacite supervisee exacte de l'architecture PatternEval.
timeout -k 60s 2700s "$python_bin" "$repo/mini_jass/tools/train.py" \
  --config "$repo/mini_jass/configs/l1_pattern_exact_supervised.yaml" \
  --oracle "$oracle" --run-dir "$exact_run" \
  >"$work/exact-supervised.stdout.json"
cp "$exact_run/result.json" "$artefact_root/cell-pattern-exact-supervised.json"
cp -R "$exact_run" "$artefact_root/pattern-exact-supervised-run"
phase cell_pattern_exact_supervised

# Cellule 2 : controle WDL pur, deux generations, actions fournies par search.
timeout -k 60s 2700s "$python_bin" "$repo/mini_jass/tools/run_selfplay.py" \
  --config "$repo/mini_jass/configs/l1_pattern_outcome_selfplay.yaml" \
  --oracle "$oracle" --run-dir "$selfplay_run" \
  >"$work/outcome-selfplay.stdout.json"
cp "$selfplay_run/result.json" "$artefact_root/cell-pattern-outcome-selfplay.json"
cp -R "$selfplay_run" "$artefact_root/pattern-outcome-selfplay-run"
phase cell_pattern_outcome_selfplay

echo "total=$(( $(date +%s) - job_start ))" >>"$phase_log"
cp "$phase_log" "$artefact_root/PHASE_TIMINGS.txt"

"$python_bin" - "$artefact_root" <<'PY'
import json
from pathlib import Path
import sys

art = Path(sys.argv[1])
exact = json.loads((art / "cell-pattern-exact-supervised.json").read_text())
selfplay = json.loads((art / "cell-pattern-outcome-selfplay.json").read_text())

timings = {}
for line in (art / "PHASE_TIMINGS.txt").read_text().splitlines():
    key, _, value = line.partition("=")
    if value.isdigit():
        timings[key] = int(value)

summary = {
    "batch": True,
    "cells": {
        "pattern_exact_supervised": {
            key: exact[key]
            for key in (
                "schema", "mode", "seed", "parameter_count", "model",
                "model_hash", "epochs", "best_epoch", "gate",
                "final_metrics", "result_hash",
            )
        },
        "pattern_outcome_selfplay": {
            key: selfplay[key]
            for key in (
                "schema", "mode", "seed", "deterministic",
                "parameter_count", "model", "initial_model_hash",
                "final_model_hash", "execution_hash", "gate",
                "training_target_contract",
            )
            if key in selfplay
        },
    },
    "phase_timings_seconds": timings,
    "cells_promotable": False,
    "direct_10x10_transfer_authorized": False,
}
summary["cells"]["pattern_outcome_selfplay"]["generations"] = [
    {
        key: row[key]
        for key in ("generation", "training", "development", "arena", "promotion")
        if key in row
    }
    for row in selfplay["generations"]
]
(art / "scientific-summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n"
)

exact_cell = summary["cells"]["pattern_exact_supervised"]
selfplay_cell = summary["cells"]["pattern_outcome_selfplay"]
lines = [
    "batch=True",
    "--- PATTERN EXACT SUPERVISED ---",
    f"exact_gate={exact_cell['gate']['status']}",
    f"exact_parameters={exact_cell['parameter_count']}",
    f"exact_best_epoch={exact_cell['best_epoch']}",
    f"exact_result_hash={exact_cell['result_hash']}",
    "--- PATTERN OUTCOME SELFPLAY ---",
    f"selfplay_gate={selfplay_cell['gate']['status']}",
    f"selfplay_parameters={selfplay_cell['parameter_count']}",
    f"selfplay_initial_hash={selfplay_cell['initial_model_hash']}",
    f"selfplay_final_hash={selfplay_cell['final_model_hash']}",
    f"selfplay_execution_hash={selfplay_cell['execution_hash']}",
    "cells_promotable=false",
    "direct_10x10_transfer_authorized=false",
]
for key, value in sorted(timings.items()):
    lines.append(f"phase_{key}_seconds={value}")
(art / "RESULTS.txt").write_text("\n".join(lines) + "\n")
PY

summary_bytes=$(stat -c %s "$artefact_root/scientific-summary.json")
echo "summary_bytes=$summary_bytes" >>"$artefact_root/RUNTIME.txt"
if [[ "$summary_bytes" -gt 65536 ]]; then
  echo "ABORT reporting: scientific-summary.json exceeds 64 KiB" >&2
  exit 6
fi
