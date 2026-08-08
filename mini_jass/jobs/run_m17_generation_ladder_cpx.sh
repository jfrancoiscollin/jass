#!/usr/bin/env bash
# M17 — l'echelle de generations, sur L1.
#
# ⚠️ ORACLE L1, PAS L2. M13 a M16 tournent sur le 6x6 (`--level l2`) ; M17
# rejoue la recette M8 gelee, qui est un L1 5x5. Exporter le mauvais oracle
# ferait echouer la garde de split, mais autant ne pas l'exporter du tout.
set -euo pipefail

repo=${JASS_CODE_DIR:?JASS_CODE_DIR is required}
job_id=${JASS_JOB_ID:?JASS_JOB_ID is required}
result_root=${JASS_RESULT_DIR:?JASS_RESULT_DIR is required}
artefact_root=${JASS_ARTEFACT_DIR:?JASS_ARTEFACT_DIR is required}
host=$(hostname)

if [[ "$job_id" != cpx62-* ]]; then
  echo "M17 requires a cpx62-routed job id, got: $job_id" >&2
  exit 2
fi
if [[ "$host" != cpx62 ]]; then
  echo "M17 requires host cpx62, got: $host" >&2
  exit 2
fi

work="$result_root/mini-jass-m17-work"
build="$work/build"
venv="$work/venv"
local_artefacts="$repo/mini_jass/artefacts"
oracle="$local_artefacts/oracle.l1.m17-cpx.jsonl"
run_dir="$local_artefacts/runs/m17-generation-ladder-cpx"
summary="$local_artefacts/m17_generation_ladder.cpx.json"
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

# L1 : pas de --level, c'est le defaut (cf README M3/M4).
"$python_bin" "$repo/mini_jass/tools/export_oracle.py" \
  --executable "$build/mini_jass_cli" \
  --output "$oracle"

"$python_bin" "$repo/mini_jass/tools/run_generation_ladder.py" \
  --config "$repo/mini_jass/configs/l1_generation_ladder.yaml" \
  --oracle "$oracle" \
  --run-dir "$run_dir" \
  --compact-output "$summary" \
  --execution-host "$host"

cp "$summary" "$artefact_root/scientific-summary.json"
cp -R "$run_dir" "$artefact_root/m17-generation-ladder-run"

"$python_bin" - "$artefact_root/scientific-summary.json" \
  "$artefact_root/RESULTS.txt" <<'PY'
import json
from pathlib import Path
import sys

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
aggregate = summary["aggregate"]
recommendation = summary["recommendation"]
lines = [
    f"milestone={summary['milestone']}",
    f"status={summary['status']}",
    f"result_hash={summary['result_hash']}",
    f"protocol_hash={summary['protocol_hash']}",
    f"execution_host={summary['protocol']['execution_host']}",
    f"paired_seeds={aggregate['paired_seed_count']}",
    # LE controle : sans promotion, l'echelle a mesure N fois la meme
    # generation et un plateau ne veut rien dire.
    f"mean_advancing_generations={aggregate['mean_advancing_generations']}",
    f"seeds_with_zero_advance={aggregate['seeds_with_zero_advance']}",
]
for rung in aggregate["rungs"]:
    lines.append(
        f"value_sign_delta_gen{rung}="
        f"{aggregate['mean_value_sign_delta_by_rung'][str(rung)]}"
    )
for rung in aggregate["rungs"]:
    lines.append(
        f"optimal_mass_delta_gen{rung}="
        f"{aggregate['mean_optimal_mass_delta_by_rung'][str(rung)]}"
    )
lines.extend(
    [
        f"finding={recommendation['finding']}",
        f"decision={recommendation['decision']}",
        f"iteration_compounds={recommendation['iteration_compounds']}",
        f"promotable={recommendation['promotable']}",
    ]
)
Path(sys.argv[2]).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
