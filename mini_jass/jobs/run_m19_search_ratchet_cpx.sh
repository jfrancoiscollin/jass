#!/usr/bin/env bash
# M19 — le cliquet de recherche, sur une sonde a profondeur commune.
#
# ⚠️ ORACLE L1, comme M17/M18 : la recette M8 gelee est un 5x5.
set -Eeuo pipefail

repo=${JASS_CODE_DIR:?JASS_CODE_DIR is required}
job_id=${JASS_JOB_ID:?JASS_JOB_ID is required}
result_root=${JASS_RESULT_DIR:?JASS_RESULT_DIR is required}
artefact_root=${JASS_ARTEFACT_DIR:?JASS_ARTEFACT_DIR is required}
host=$(hostname)

if [[ "$job_id" != cpx62-* ]]; then
  echo "M19 requires a cpx62-routed job id, got: $job_id" >&2
  exit 2
fi
if [[ "$host" != cpx62 ]]; then
  echo "M19 requires host cpx62, got: $host" >&2
  exit 2
fi

work="$result_root/mini-jass-m19-work"
build="$work/build"
venv="$work/venv"
local_artefacts="$repo/mini_jass/artefacts"
oracle="$local_artefacts/oracle.l1.m19-cpx.jsonl"
run_dir="$local_artefacts/runs/m19-search-ratchet-cpx"
summary="$local_artefacts/m19_search_ratchet.cpx.json"
mkdir -p "$work" "$artefact_root"

# C. Le partage setup/science, enfin ancre -- et par le canal qui ARRIVE.
# `cpx62-1206` ecrivait deja ces timings, mais dans un PHASE_TIMINGS.txt que le
# runner n'inline pas (seul `scientific-summary.json` est sur sa liste blanche),
# donc la mesure existait sans jamais parvenir. Ici elle est fusionnee dans le
# summary APRES coup, hors du `result_hash` : le temps mural n'appartient pas
# au protocole scientifique et ne doit pas en perturber l'identite.
# cpx62-1208 est mort a `exit 1` en ne publiant QUE `runner-launch.json` : tout
# ce qui ecrit dans $ART se trouve apres la science, donc un plantage ne laisse
# aucune trace exploitable et il faut un job de plus rien que pour lire le log.
# Le trap rend le diagnostic disponible dans les artefacts du run qui echoue.
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

"$python_bin" "$repo/mini_jass/tools/run_search_ratchet.py" \
  --config "$repo/mini_jass/configs/l1_search_ratchet.yaml" \
  --oracle "$oracle" \
  --run-dir "$run_dir" \
  --compact-output "$summary" \
  --execution-host "$host"
phase science_10_runs_of_8_generations
echo "total=$(( $(date +%s) - t_job_start ))" >>"$phase_log"

cp -R "$run_dir" "$artefact_root/m19-search-ratchet-run"
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
# Ajoute APRES le hash : le temps mural n'est pas du protocole. `result_hash`
# reste calcule sur la science seule, donc comparable d'un run a l'autre meme
# si la box est plus chargee.
summary["phase_timings_seconds"] = timings
Path(sys.argv[3]).write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

# La garde de cpx62-1206 : au-dela de 64 KiB le runner saute le summary EN
# SILENCE et le verdict n'existe plus que dans le stockage objet.
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
c = a["contrasts"]
r = s["recommendation"]
lines = [
    f"milestone={s['milestone']}",
    f"status={s['status']}",
    f"finding={r['finding']}",
    f"result_hash={s['result_hash']}",
    f"protocol_hash={s['protocol_hash']}",
    f"execution_host={a['execution']['execution_host']}",
    f"common_probe_search_depth={s['protocol']['common_probe_search_depth']}",
    # LE CONTROLE, en tete : sans lui le contraste de niveau ne vaut rien.
    f"rung0_level_gap={r['rung0_level_gap']}",
]
for name in ("reference_minus_shallow_level_g8",
             "reference_minus_shallow_gain",
             "reference_minus_shallow_level_g0"):
    row = c[name]
    lines.append(f"{name}={row['mean']}")
    lines.append(f"{name}_ci95={row['confidence_95']}")
for arm in sorted(a["arms"]):
    row = a["arms"][arm]
    lines.append(f"arm_{arm}_advancing_generations={row['mean_advancing_generations']}")
    lines.append(f"arm_{arm}_arena_vs_initial={row['mean_final_arena_score_vs_initial']}")
    lines.append(f"arm_{arm}_loop_consumed_nodes={row['mean_loop_consumed_nodes']}")
    by_rung = row["mean_probe_start_exact_rate_by_rung"]
    for rung in sorted(by_rung, key=int):
        lines.append(f"arm_{arm}_probe_exact_g{rung}={by_rung[rung]}")
lines.extend([
    f"consumed_node_imbalance={r['consumed_node_imbalance']}",
    f"compute_balanced_within_m8_tolerance={r['compute_balanced_within_m8_tolerance']}",
    f"search_is_cliquet={r['search_is_cliquet']}",
    f"next_step={r['next_step']}",
    "m19_promotable=false",
    "direct_10x10_transfer_authorized=false",
])
for key, value in sorted(s.get("phase_timings_seconds", {}).items()):
    lines.append(f"phase_{key}_seconds={value}")
Path(sys.argv[2]).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
