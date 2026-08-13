#!/usr/bin/env bash
# Autopsie d'une tentative de census : le message d'abort ET la queue restante.
#
# ⛔ AUCUN CENSUS. Trois copies nommees explicitement (`RESULTS.txt`,
# `logs.tar.gz`, `checkpoints/state.json`), un parse, des compteurs. Aucun
# listing R2, aucun corpus, aucun modele, aucun frozen set, aucun fit.
#
# POURQUOI LES TROIS ENSEMBLE. `cpx62-1267` est sorti en `exit 2`, c'est-a-dire
# le chemin `except (OSError, ValueError, RuntimeError, TimeoutExpired)` de
# `census()`. Plusieurs causes y menent et elles n'appellent pas le meme
# correctif -- plafond de profondeur, listing invalide, disque. Le message exact
# est dans `RESULTS.txt` et le detail dans le log ; la queue restante dit ce
# qu'il reste a faire une fois la cause levee. Deduire l'un sans l'autre, c'est
# ce qui a coute la tentative precedente.
set -Eeuo pipefail

repo=${JASS_CODE_DIR:?JASS_CODE_DIR is required}
result_root=${JASS_RESULT_DIR:?JASS_RESULT_DIR is required}
artefact_root=${JASS_ARTEFACT_DIR:?JASS_ARTEFACT_DIR is required}
attempt_uri=${CENSUS_ATTEMPT_URI:?CENSUS_ATTEMPT_URI is required}

work="$result_root/census-autopsy"
mkdir -p "$work" "$artefact_root"

free_mb=$(df -Pm /root | awk 'NR==2 {print $4}')
[[ "${free_mb:-0}" -gt 3000 ]] || { echo "ABORT disk: <3 GiB free" >&2; exit 3; }
command -v rclone >/dev/null || { echo "rclone missing" >&2; exit 4; }

fetch() {  # objet nomme explicitement : impossible de traverser R2 par erreur
  timeout 300s rclone copyto "$attempt_uri/$1" "$work/$2" \
    --retries 3 --low-level-retries 10 || return 1
}

fetch "RESULTS.txt" "RESULTS.txt" || echo "(RESULTS.txt absent)" >"$work/RESULTS.txt"
fetch "logs.tar.gz" "logs.tar.gz" || true
fetch "checkpoints/state.json" "state.json" || true

{
  echo "=== RESULTS.txt de la tentative ==="
  cat "$work/RESULTS.txt"
  echo
  echo "=== journaux ==="
  if [[ -s "$work/logs.tar.gz" ]]; then
    mkdir -p "$work/logs" && tar -xzf "$work/logs.tar.gz" -C "$work/logs" 2>/dev/null || true
    # ⚠️ On TRONQUE par la fin : l'abort est la derniere chose ecrite, et un log
    # entier ferait sauter le plafond de transport de 64 KiB du runner.
    find "$work/logs" -type f -name '*.log' | sort | while read -r f; do
      echo "--- ${f#$work/logs/} (40 dernieres lignes)"
      tail -n 40 "$f"
    done
  else
    echo "(logs.tar.gz absent ou vide)"
  fi
} >"$artefact_root/AUTOPSY.txt"

if [[ -s "$work/state.json" ]]; then
  python3 "$repo/jobs/tools/megacorpus_census_state_readout.py" \
    --state "$work/state.json" --output "$artefact_root/scientific-summary.json"
else
  echo '{"schema":"jass.megacorpus_census_state_readout.v1","state_json":"absent"}' \
    >"$artefact_root/scientific-summary.json"
fi

# ⛔ Le runner n'inline que <= 64 KiB et SAUTE le reste EN SILENCE (cpx62-1206).
for f in AUTOPSY.txt scientific-summary.json; do
  size=$(stat -c %s "$artefact_root/$f")
  if [[ "$size" -gt 65536 ]]; then
    tail -c 60000 "$artefact_root/$f" >"$artefact_root/$f.tail"
    mv "$artefact_root/$f.tail" "$artefact_root/$f"
    echo "$f tronque a 60 ko pour rester sous le plafond de transport" >&2
  fi
done
cp "$artefact_root/AUTOPSY.txt" "$artefact_root/RESULTS.txt"
echo "autopsy complete"
