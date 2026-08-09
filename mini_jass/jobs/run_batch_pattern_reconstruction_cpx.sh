#!/usr/bin/env bash
# BATCH — M14-P (bruit de la cible de valeur) puis M17-P (echelle de generations).
#
# POURQUOI UN BATCH. Le cout fixe du runner est de ~28 min par tentative
# (worktree au SHA epingle), mesure sur `cpx62-1216` : 52 s de science sur
# 29 min de mur. Deux jobs separes paieraient ce fixe deux fois pour ~48 min de
# science. Un seul job le paie une fois.
#
# POURQUOI CET ORDRE. M14-P (~11 min de science) avant M17-P (~37 min) : la
# cellule courte publie son verdict tot, donc une mort pendant M17-P laisse
# quand meme un resultat exploitable.
#
# CE QUE CE WRAPPER N'EST PAS. Il ne reimplemente pas les cellules : il appelle
# `run_pattern_reconstruction_cpx.sh` telle quelle, une fois par cellule, avec
# un `JASS_ARTEFACT_DIR` PROPRE A CHAQUE CELLULE. Sans cette isolation la
# seconde cellule ecraserait `scientific-summary.json` et `RESULTS.txt` de la
# premiere -- exactement la classe de bug qui a fait perdre le verdict de 0675
# et rendu 1206 invisible. Le surcout est un rebuild + un pytest en double,
# soit ~31 s d'apres les timings de 1216 : negligeable devant le fixe runner.
set -Eeuo pipefail

repo=${JASS_CODE_DIR:?JASS_CODE_DIR is required}
job_id=${JASS_JOB_ID:?JASS_JOB_ID is required}
result_root=${JASS_RESULT_DIR:?JASS_RESULT_DIR is required}
artefact_root=${JASS_ARTEFACT_DIR:?JASS_ARTEFACT_DIR is required}
host=$(hostname)

if [[ "$job_id" != cpx62-* || "$host" != cpx62 ]]; then
  echo "pattern reconstruction batch requires cpx62 (job=$job_id host=$host)" >&2
  exit 2
fi

work="$result_root/mini-jass-pattern-reconstruction-batch"
mkdir -p "$work" "$artefact_root"

# Hygiene disque obligatoire : les jobs qui meurent laissent leur scratch, ca
# s'accumule, et un /root plein tue le runner (ccx33, 2026-07-11).
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 \
  ! -path "$work" -exec rm -rf {} + 2>/dev/null || true
free_mb=$(df -Pm /root | awk 'NR==2 {print $4}')
if [[ "${free_mb:-0}" -le 3000 ]]; then
  echo "ABORT disk: less than 3 GiB free under /root" >&2
  exit 3
fi

progress="$artefact_root/PROGRESS.txt"
job_start=$(date +%s)
cells=(m14p m17p)

# Monitor de progression : la cellule courante et le temps ecoule, rafraichis
# toutes les 2 min. Sans lui le job est dark pendant ~50 min (0665 : 89 min de
# noir avant le kill).
# ⚠️ Le monitor tourne en fond mais AUCUN `wait` nu n'existe dans ce script --
# les cellules sont sequentielles et au premier plan. Le piege de deadlock
# monitor+`wait` (0665/0666/0668) ne peut donc pas se produire ici.
monitor() {
  while :; do
    {
      echo "job=$job_id"
      echo "elapsed_seconds=$(( $(date +%s) - job_start ))"
      echo "current_cell=$(cat "$work/.current" 2>/dev/null || echo pending)"
      echo "cells_published:"
      ls -1 "$artefact_root"/cell-*.json 2>/dev/null | sed 's/^/  /' || echo "  (none)"
    } >"$progress.tmp"
    mv "$progress.tmp" "$progress"
    sleep 120
  done
}
# ⚠️ SORTIE DU MONITOR REDIRIGEE, non negociable. Le runner capture stdout du
# job A TRAVERS UN TUYAU ; un processus de fond qui herite de ce stdout en
# retient l'extremite d'ecriture, et le lecteur n'atteint JAMAIS l'EOF meme
# apres la fin du job -- mesure ici : le job pendait indefiniment sur le
# chemin d'echec. Le monitor n'ecrit donc que dans des fichiers.
monitor >/dev/null 2>&1 & monitor_pid=$!

# `kill` ne fait pas tomber le `sleep` en cours, qui survit en orphelin ; comme
# il n'a plus aucun descripteur du job, il est inoffensif et sort seul.
stop_monitor() {
  kill "$monitor_pid" 2>/dev/null || true
  wait "$monitor_pid" 2>/dev/null || true
}

on_failure() {
  local rc=$?
  [[ $rc -eq 0 ]] && return 0
  stop_monitor
  {
    echo "exit_code=$rc"
    echo "failed_cell=$(cat "$work/.current" 2>/dev/null || echo unknown)"
    echo "elapsed_seconds=$(( $(date +%s) - job_start ))"
    echo "cells_published:"
    ls -1 "$artefact_root"/cell-*.json 2>/dev/null | sed 's/^/  /' || echo "  (none)"
  } >"$artefact_root/FAILURE.txt"
}
trap on_failure EXIT

for cell in "${cells[@]}"; do
  echo "$cell" >"$work/.current"
  cell_artefacts="$artefact_root/$cell"
  mkdir -p "$cell_artefacts"
  JASS_ARTEFACT_DIR="$cell_artefacts" \
    bash "$repo/mini_jass/jobs/run_pattern_reconstruction_cpx.sh" "$cell"
  # Publie DES QUE la cellule finit : un resultat acquis ne doit pas dependre
  # de la survie de la suivante.
  cp "$cell_artefacts/scientific-summary.json" "$artefact_root/cell-$cell.json"
  echo "  $cell done at $(( $(date +%s) - job_start ))s" >>"$work/.timeline"
done
echo "combine" >"$work/.current"

python3 - "$artefact_root" "${cells[@]}" <<'PY'
import json
from pathlib import Path
import sys

out = Path(sys.argv[1])
cells = sys.argv[2:]
loaded = {cell: json.loads((out / f"cell-{cell}.json").read_text(encoding="utf-8"))
          for cell in cells}

summary = {"batch": True, "cells": loaded, "promotable": False,
           "direct_10x10_transfer_authorized": False}
text = json.dumps(summary, indent=2, sort_keys=True) + "\n"

# ⛔ Le runner N'INLINE QUE les fichiers <= 64 KiB, et il SAUTE les autres EN
# SILENCE (cpx62-1206 : 530 163 octets, verdict invisible, republication
# manuelle). Au-dela on degrade vers une forme reduite PLUTOT QUE d'echouer :
# perdre l'aggregat est supportable, perdre le verdict ne l'est pas. Les
# cellules completes restent dans cell-*.json et result.full.json.
LIMIT = 64 * 1024
if len(text.encode("utf-8")) > LIMIT:
    summary["cells"] = {
        cell: {key: value for key, value in body.items() if key != "aggregate"}
        for cell, body in loaded.items()
    }
    summary["reduced"] = "aggregate dropped to stay under the 64 KiB runner cap"
    text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if len(text.encode("utf-8")) > LIMIT:
        summary["cells"] = {
            cell: {key: body[key] for key in
                   ("milestone", "status", "protocol_hash", "result_hash")}
            for cell, body in loaded.items()
        }
        summary["reduced"] = "only verdicts retained under the 64 KiB runner cap"
        text = json.dumps(summary, indent=2, sort_keys=True) + "\n"

(out / "scientific-summary.json").write_text(text, encoding="utf-8")

lines = []
for cell, body in loaded.items():
    lines += [
        f"cell={cell}",
        f"  milestone={body['milestone']}",
        f"  status={body['status']}",
        f"  finding={body['recommendation']['finding']}",
        f"  result_hash={body['result_hash']}",
    ]
lines.append("promotable=false")
(out / "RESULTS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(" | ".join(f"{cell}={body['status']}" for cell, body in loaded.items()))
PY

cp "$work/.timeline" "$artefact_root/CELL_TIMELINE.txt" 2>/dev/null || true
echo "total_seconds=$(( $(date +%s) - job_start ))" >>"$artefact_root/CELL_TIMELINE.txt"

size=$(stat -c %s "$artefact_root/scientific-summary.json")
echo "batch complete: summary ${size} bytes, $(( $(date +%s) - job_start ))s"
stop_monitor
trap - EXIT
