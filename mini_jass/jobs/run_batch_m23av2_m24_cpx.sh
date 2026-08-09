#!/usr/bin/env bash
# BATCH — M23-A v2 (40 graines) + M24 (plafond supervise), dans UN attempt.
#
# Pourquoi batcher : le cout fixe du runner est de ~24 min par attempt (creation
# du worktree a la SHA epinglee) et ne depend PAS du volume scientifique —
# mesure quatre fois. Deux jobs separes le paieraient deux fois pour ~25 min de
# science au total.
#
# ⚠️ Et la contrepartie est bordee : chaque cellule ECRIT SON RESULTAT DES
# QU'ELLE FINIT. `cpx62-1208` a perdu 28 min de science parce que tout etait
# ecrit au finalize et qu'une assertion a saute a la derniere ligne.
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

work="$result_root/mini-jass-shared-work"
build="$work/build"
venv="$work/venv"
local_artefacts="$repo/mini_jass/artefacts"
oracle="$local_artefacts/oracle.l1.batch-cpx.jsonl"
mkdir -p "$work" "$artefact_root"

phase_log="$work/phase_timings.txt"
: >"$phase_log"
t_job_start=$(date +%s)
phase() {
  local now
  now=$(date +%s)
  echo "$1=$((now - t_phase))" >>"$phase_log"
  t_phase=$now
}
t_phase=$t_job_start

on_failure() {
  local rc=$?
  [[ $rc -eq 0 ]] && return 0
  {
    echo "exit_code=$rc"
    echo "cells_completed:"
    ls -1 "$artefact_root"/cell-*.json 2>/dev/null || echo "  (aucune)"
    echo "phases:"
    cat "$phase_log" 2>/dev/null || echo "  (aucune)"
  } >"$artefact_root/FAILURE.txt" 2>/dev/null || true
  return $rc
}
trap on_failure EXIT

cmake -S "$repo/mini_jass" -B "$build" \
  -DCMAKE_BUILD_TYPE=Release -DMINI_JASS_BUILD_TESTS=ON
cmake --build "$build" --parallel 16
ctest --test-dir "$build" --output-on-failure
phase build_and_ctest

python3 -m venv --system-site-packages "$venv"
python_bin="$venv/bin/python"
if ! "$python_bin" -c 'import torch' >/dev/null 2>&1; then
  "$python_bin" -m pip install --index-url https://download.pytorch.org/whl/cpu 'torch==2.13.0'
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

# ---- CELLULE 1 : M23-A v2, 40 graines -------------------------------------
"$python_bin" "$repo/mini_jass/tools/run_mix_strategy_screen.py" \
  --config "$repo/mini_jass/configs/l1_mix_strategy_screen_v2.yaml" \
  --oracle "$oracle" \
  --run-dir "$local_artefacts/runs/m23a-v2-cpx" \
  --compact-output "$artefact_root/cell-m23a-v2.json" \
  --execution-host "$host"
phase cell_m23a_v2_40_seeds
cp -R "$local_artefacts/runs/m23a-v2-cpx" "$artefact_root/m23a-v2-run"

# ---- CELLULE 2 : M24, plafond supervise ------------------------------------
"$python_bin" "$repo/mini_jass/tools/run_supervised_ceiling.py" \
  --config "$repo/mini_jass/configs/l1_supervised_ceiling.yaml" \
  --oracle "$oracle" \
  --run-dir "$local_artefacts/runs/m24-ceiling-cpx" \
  --compact-output "$artefact_root/cell-m24.json" \
  --execution-host "$host"
phase cell_m24_supervised_ceiling
cp -R "$local_artefacts/runs/m24-ceiling-cpx" "$artefact_root/m24-ceiling-run"

echo "total=$(( $(date +%s) - t_job_start ))" >>"$phase_log"
cp "$phase_log" "$artefact_root/PHASE_TIMINGS.txt"

# ---- SUMMARY COMBINE : seul canal que le runner inline ----------------------
"$python_bin" - "$artefact_root" <<'PY'
import json
from pathlib import Path
import sys

art = Path(sys.argv[1])
timings = {}
for line in (art / "PHASE_TIMINGS.txt").read_text(encoding="utf-8").splitlines():
    key, _, value = line.partition("=")
    if value.strip().isdigit():
        timings[key.strip()] = int(value)


def compact(path, keep):
    """Ne garde que ce qui DECIDE : deux cellules doivent tenir sous 64 KiB."""
    full = json.loads(path.read_text(encoding="utf-8"))
    return {key: full[key] for key in keep if key in full}


summary = {
    "batch": True,
    "cells": {
        "M23A_v2": compact(art / "cell-m23a-v2.json",
                           ("milestone", "status", "result_hash", "protocol_hash",
                            "recommendation", "aggregate", "census_summary")),
        "M24": compact(art / "cell-m24.json",
                       ("milestone", "status", "result_hash", "protocol_hash",
                        "recommendation", "aggregate")),
    },
    # Fusionnes APRES les hashes de chaque cellule : le temps mural n'appartient
    # pas au protocole et ne doit perturber aucune identite scientifique.
    "phase_timings_seconds": timings,
}
(art / "scientific-summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

summary_bytes=$(stat -c %s "$artefact_root/scientific-summary.json")
echo "summary_bytes=$summary_bytes" >>"$artefact_root/PHASE_TIMINGS.txt"
if [[ "$summary_bytes" -gt 65536 ]]; then
  echo "ABORT reporting: scientific-summary.json = $summary_bytes o > 65536," \
       "le runner ne l'inlinera pas et les verdicts seront invisibles" >&2
  exit 6
fi

"$python_bin" - "$artefact_root/scientific-summary.json" \
  "$artefact_root/RESULTS.txt" <<'PY'
import json
from pathlib import Path
import sys

s = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
lines = ["batch=True"]

m23 = s["cells"]["M23A_v2"]
r = m23["recommendation"]
lines += [
    "--- CELLULE 1 : M23-A v2 (40 graines) ---",
    f"m23a_status={m23['status']}",
    f"m23a_finding={r['finding']}",
    f"m23a_result_hash={m23['result_hash']}",
    f"m23a_seed_count={m23['aggregate']['execution']['seed_count']}",
    f"m23a_primary_contrast={r['primary_contrast']}",
    f"m23a_primary_arena_mean={r['primary_arena_mean']}",
    f"m23a_primary_arena_ci95={r['primary_arena_ci95']}",
    f"m23a_mixing_beats_current_only={r['mixing_beats_current_only']}",
    f"m23a_shape_candidate={r['shape_candidate']['arm']}",
    f"m23a_shape_candidate_is_a_result={r['shape_candidate']['is_a_result']}",
]
for arm in sorted(m23["aggregate"]["arms"]):
    row = m23["aggregate"]["arms"][arm]
    lines.append(f"m23a_arm_{arm}_arena={row['mean_arena_vs_initial']}")
census = m23.get("census_summary", {})
if "unique_samples_by_arm" in census:
    lines.append(f"m23a_census_uniques={census['unique_samples_by_arm']}")

m24 = s["cells"]["M24"]
c = m24["recommendation"]
lines += [
    "--- CELLULE 2 : M24 (plafond supervise) ---",
    f"m24_status={m24['status']}",
    f"m24_finding={c['finding']}",
    f"m24_result_hash={m24['result_hash']}",
    f"m24_primary_metric={c['primary_metric']}",
    f"m24_dose_ladder={c['dose_ladder']}",
    f"m24_frozen_test_by_dose={c['frozen_test_by_dose']}",
    f"m24_last_dose_step={c['last_dose_step']}",
    f"m24_saturation_tolerance={c['saturation_tolerance']}",
    f"m24_is_an_upper_bound_not_a_candidate={c['is_an_upper_bound_not_a_candidate']}",
]
if c.get("ceiling"):
    for cohort, row in sorted(c["ceiling"].items()):
        for key, value in sorted(row.items()):
            lines.append(f"m24_ceiling_{cohort}_{key}={value}")
    lines += [
        f"m24_ceiling_primary_frozen_test={c['ceiling_primary_frozen_test']}",
        f"m24_distance_to_oracle={c['distance_to_oracle']}",
        f"m24_capacity_gain_from_bigger_models={c['capacity_gain_from_bigger_models']}",
        f"m24_architecture_is_the_binding_constraint={c['architecture_is_the_binding_constraint']}",
    ]
lines += [
    f"m24_next_step={c['next_step']}",
    "cells_promotable=false",
    "direct_10x10_transfer_authorized=false",
]
for key, value in sorted(s.get("phase_timings_seconds", {}).items()):
    lines.append(f"phase_{key}_seconds={value}")
Path(sys.argv[2]).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
