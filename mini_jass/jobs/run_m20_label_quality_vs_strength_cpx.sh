#!/usr/bin/env bash
# M20 — etiquettes contre force, en contraste apparie, 20 graines.
set -Eeuo pipefail

repo=${JASS_CODE_DIR:?JASS_CODE_DIR is required}
job_id=${JASS_JOB_ID:?JASS_JOB_ID is required}
result_root=${JASS_RESULT_DIR:?JASS_RESULT_DIR is required}
artefact_root=${JASS_ARTEFACT_DIR:?JASS_ARTEFACT_DIR is required}
host=$(hostname)

if [[ "$job_id" != cpx62-* ]]; then
  echo "M20 requires a cpx62-routed job id, got: $job_id" >&2
  exit 2
fi
if [[ "$host" != cpx62 ]]; then
  echo "M20 requires host cpx62, got: $host" >&2
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
oracle="$local_artefacts/oracle.l1.m20-cpx.jsonl"
run_dir="$local_artefacts/runs/m20-label-quality-vs-strength-cpx"
summary="$local_artefacts/m20_label_quality_vs_strength.cpx.json"
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

"$python_bin" "$repo/mini_jass/tools/run_label_quality_vs_strength.py" \
  --config "$repo/mini_jass/configs/l1_label_quality_vs_strength.yaml" \
  --oracle "$oracle" \
  --run-dir "$run_dir" \
  --compact-output "$summary" \
  --execution-host "$host"
phase science_80_runs_of_8_generations
echo "total=$(( $(date +%s) - t_job_start ))" >>"$phase_log"

cp -R "$run_dir" "$artefact_root/m20-label-quality-vs-strength-run"
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
lines = [
    f"milestone={s['milestone']}",
    f"status={s['status']}",
    f"finding={r['finding']}",
    f"result_hash={s['result_hash']}",
    f"protocol_hash={s['protocol_hash']}",
    f"execution_host={a['execution']['execution_host']}",
    f"seed_count={a['execution']['seed_count']}",
    # LES CONTROLES, en tete.
    f"worst_rung0_label_gap={r['worst_rung0_label_gap']}",
    f"reference_arm_divergence={r['reference_arm_divergence']}",
    f"oracle_has_no_causal_role={a['execution']['oracle_has_no_causal_role']}",
    f"anti_correlation_established={r['anti_correlation_established']}",
    f"established_in_pairs={r.get('established_in_pairs')}",
]
for name in sorted(a["pairs"]):
    pair = a["pairs"][name]
    verdict = r["pairs"].get(name, {})
    lines.append(f"pair_{name}_single_factor={pair['single_factor']}")
    lines.append(f"pair_{name}_arms={pair['high_label_arm']}_minus_{pair['reference_arm']}")
    for endpoint in ("label_delta", "arena_delta", "rung0_label_delta"):
        row = pair[endpoint]
        lines.append(f"pair_{name}_{endpoint}={row['mean']}")
        lines.append(f"pair_{name}_{endpoint}_ci95={row['confidence_95']}")
    lines.append(f"pair_{name}_within_pair_correlation={pair['within_pair_correlation']}")
    for key in ("label_gap_practical_and_confident",
                "arena_gap_practical_and_confident",
                "signs_opposed", "anti_correlated"):
        lines.append(f"pair_{name}_{key}={verdict.get(key)}")
for arm in sorted(a["arms"]):
    row = a["arms"][arm]
    lines.append(f"arm_{arm}_label_g8={row['mean_probe_start_exact_rate_by_rung']['8']}")
    lines.append(f"arm_{arm}_arena_vs_initial={row['mean_final_arena_score_vs_initial']}")
    lines.append(f"arm_{arm}_advancing_generations={row['mean_advancing_generations']}")
    lines.append(f"arm_{arm}_loop_consumed_nodes={row['mean_loop_consumed_nodes']}")
lines.extend([
    f"next_step={r['next_step']}",
    "m20_promotable=false",
    "direct_10x10_transfer_authorized=false",
])
for key, value in sorted(s.get("phase_timings_seconds", {}).items()):
    lines.append(f"phase_{key}_seconds={value}")
Path(sys.argv[2]).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
