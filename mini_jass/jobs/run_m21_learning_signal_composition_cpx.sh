#!/usr/bin/env bash
# M21 — quelle information s'accumule entre les generations ? 20 graines.
set -Eeuo pipefail

repo=${JASS_CODE_DIR:?JASS_CODE_DIR is required}
job_id=${JASS_JOB_ID:?JASS_JOB_ID is required}
result_root=${JASS_RESULT_DIR:?JASS_RESULT_DIR is required}
artefact_root=${JASS_ARTEFACT_DIR:?JASS_ARTEFACT_DIR is required}
host=$(hostname)

if [[ "$job_id" != cpx62-* ]]; then
  echo "M21 requires a cpx62-routed job id, got: $job_id" >&2
  exit 2
fi
if [[ "$host" != cpx62 ]]; then
  echo "M21 requires host cpx62, got: $host" >&2
  exit 2
fi

# 🔥 SCRATCH PARTAGE, ET C'EST DELIBERE. cpx62-1209 a mesure 106 s de science
# pour 32 min de mural : tout le cout est dans cmake + ctest + venv + torch. Il
# n'etait chaud QUE parce qu'il reutilisait le scratch de 1208 (meme nom de
# repertoire). Un nom par jalon paie donc ~26-30 min de setup a froid a CHAQUE
# nouvelle cellule, pour une science qui dure deux minutes. Un nom PARTAGE rend
# tous les jalons mini-jass chauds. Sans risque de course : le runner n'execute
# qu'un job a la fois, et `ctest` reste execute a chaque fois, donc un build
# stale est attrape et non subi.
work="$result_root/mini-jass-shared-work"
build="$work/build"
venv="$work/venv"
local_artefacts="$repo/mini_jass/artefacts"
oracle="$local_artefacts/oracle.l1.m21-cpx.jsonl"
run_dir="$local_artefacts/runs/m21-learning-signal-composition-cpx"
summary="$local_artefacts/m21_learning_signal_composition.cpx.json"
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

# cpx62-1208 est mort en ne publiant que `runner-launch.json` : tout ce qui
# ecrit dans $ART se trouve apres la science.
on_failure() {
  local rc=$?
  [[ $rc -eq 0 ]] && return 0
  {
    echo "exit_code=$rc"
    echo "failed_after_phases:"
    cat "$phase_log" 2>/dev/null || echo "  (aucune phase terminee)"
  } >"$artefact_root/FAILURE.txt" 2>/dev/null || true
  return $rc
}
trap on_failure EXIT

cmake -S "$repo/mini_jass" -B "$build" \
  -DCMAKE_BUILD_TYPE=Release \
  -DMINI_JASS_BUILD_TESTS=ON
cmake --build "$build" --parallel 16
ctest --test-dir "$build" --output-on-failure
phase build_and_ctest

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
phase venv_and_pip

export PYTHONPATH="$repo/mini_jass/python"
"$python_bin" -m pytest "$repo/mini_jass/tests/python"
phase pytest

"$python_bin" "$repo/mini_jass/tools/export_oracle.py" \
  --level l1 \
  --executable "$build/mini_jass_cli" \
  --output "$oracle"
phase oracle_export_l1

"$python_bin" "$repo/mini_jass/tools/run_learning_signal_composition.py" \
  --config "$repo/mini_jass/configs/l1_learning_signal_composition.yaml" \
  --oracle "$oracle" \
  --run-dir "$run_dir" \
  --compact-output "$summary" \
  --execution-host "$host"
phase science_20_packs_plus_120_trainings
echo "total=$(( $(date +%s) - t_job_start ))" >>"$phase_log"

cp -R "$run_dir" "$artefact_root/m21-learning-signal-composition-run"
cp "$phase_log" "$artefact_root/PHASE_TIMINGS.txt"

"$python_bin" - "$summary" "$phase_log" \
  "$artefact_root/scientific-summary.json" <<'PY'
import json
from pathlib import Path
import sys

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
timings = {}
for line in Path(sys.argv[2]).read_text(encoding="utf-8").splitlines():
    key, _, value = line.partition("=")
    if value.strip().isdigit():
        timings[key.strip()] = int(value)
# Fusionne APRES le hash : le temps mural n'appartient pas au protocole.
summary["phase_timings_seconds"] = timings
Path(sys.argv[3]).write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

summary_bytes=$(stat -c %s "$artefact_root/scientific-summary.json")
echo "summary_bytes=$summary_bytes" >>"$artefact_root/PHASE_TIMINGS.txt"
if [[ "$summary_bytes" -gt 65536 ]]; then
  echo "ABORT reporting: scientific-summary.json = $summary_bytes o > 65536," \
       "le runner ne l'inlinera pas et le verdict sera invisible" >&2
  exit 6
fi

"$python_bin" - "$artefact_root/scientific-summary.json" \
  "$artefact_root/RESULTS.txt" <<'PY'
import json
from pathlib import Path
import sys

s = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
a = s["aggregate"]
r = s["recommendation"]
c = a["contrasts"]
lines = [
    f"milestone={s['milestone']}",
    f"status={s['status']}",
    f"finding={r['finding']}",
    f"result_hash={s['result_hash']}",
    f"protocol_hash={s['protocol_hash']}",
    f"execution_host={a['execution']['execution_host']}",
    f"seed_count={a['execution']['seed_count']}",
    f"primary_contrast={r['primary_contrast']}",
    f"composition_is_the_mechanism={r['composition_is_the_mechanism']}",
    f"mechanism_attributed={r.get('mechanism_attributed')}",
]
# LE controle qui rend le primaire attribuable : MIX et G1_WIDE doivent porter
# le meme compte unique. Le job a deja abort si ce n'est pas le cas ; on le
# reimprime pour que le lecteur du RESULTS le voie sans ouvrir le JSON.
census = s.get("census_summary", {})
for key in ("unit_samples_per_generation", "unique_samples_by_arm",
            "unique_states_by_arm", "novel_late_candidates",
            "matched_late_drawn", "matched_strata_dimensions",
            "matched_strata_preregistered_dimensions",
            "matched_strata_reduction"):
    if key in census:
        lines.append(f"census_{key}={census[key]}")
for name in sorted(c):
    for endpoint in ("learning", "arena"):
        row = c[name][endpoint]
        lines.append(f"{name}__{endpoint}={row['mean']}")
        lines.append(f"{name}__{endpoint}_ci95={row['confidence_95']}")
for arm in sorted(a["arms"]):
    row = a["arms"][arm]
    lines.append(f"arm_{arm}_learning_delta={row['mean_learning_delta']}")
    lines.append(f"arm_{arm}_arena_vs_initial={row['mean_arena_vs_initial']}")
    lines.append(f"arm_{arm}_unique_samples={row['mean_unique_samples']}")
lines.extend([
    f"volume_effect_learning={r['volume_effect_learning']}",
    f"recency_effect_learning={r['recency_effect_learning']}",
    f"novelty_minus_matched_learning={r['novelty_minus_matched_learning']}",
    f"next_step={r['next_step']}",
    "m21_promotable=false",
    "direct_10x10_transfer_authorized=false",
])
for key, value in sorted(s.get("phase_timings_seconds", {}).items()):
    lines.append(f"phase_{key}_seconds={value}")
Path(sys.argv[2]).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
