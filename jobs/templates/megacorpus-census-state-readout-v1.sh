#!/usr/bin/env bash
# Lecture de la QUEUE RESTANTE du census MegaCorpus. Metadonnees uniquement.
#
# ⛔ CE JOB NE FAIT AUCUN CENSUS. Il copie UN fichier (`state.json`, ~270 ko),
# le parse, publie des compteurs. Aucun listing R2, aucun corpus, aucun modele,
# aucune lecture de frozen set, aucun fit, aucune promotion.
#
# POURQUOI. `cpx62-1264` a ete tue apres 8h47 : son debit etait tombe a ~15 min
# par shard, soit exactement `SHARD_TIMEOUT_SECONDS=900`. Chaque prefixe restant
# consommait son timeout complet avant de se subdiviser. ⚠️ Et ce timeout
# n'achete RIEN : quand un listing recursif expire, le listing partiel est jete,
# les 900 s ne financent que la DECISION de subdiviser. Recalibrer ce reglage
# suppose de savoir ce qui reste -- c'est ce que ce job rend.
set -Eeuo pipefail

repo=${JASS_CODE_DIR:?JASS_CODE_DIR is required}
job_id=${JASS_JOB_ID:?JASS_JOB_ID is required}
result_root=${JASS_RESULT_DIR:?JASS_RESULT_DIR is required}
artefact_root=${JASS_ARTEFACT_DIR:?JASS_ARTEFACT_DIR is required}
source_uri=${CENSUS_STATE_URI:?CENSUS_STATE_URI is required}

work="$result_root/census-state-readout"
mkdir -p "$work" "$artefact_root"

free_mb=$(df -Pm /root | awk 'NR==2 {print $4}')
if [[ "${free_mb:-0}" -le 3000 ]]; then
  echo "ABORT disk: less than 3 GiB free under /root" >&2
  exit 3
fi

command -v rclone >/dev/null || { echo "rclone missing" >&2; exit 4; }

# Un seul objet, nomme explicitement : impossible de traverser R2 par erreur.
timeout 300s rclone copyto "$source_uri" "$work/state.json" \
  --retries 3 --low-level-retries 10

bytes=$(stat -c %s "$work/state.json")
echo "state.json=${bytes} octets"
[[ "$bytes" -gt 0 ]] || { echo "state.json vide" >&2; exit 5; }

python3 "$repo/jobs/tools/megacorpus_census_state_readout.py" \
  --state "$work/state.json" \
  --output "$artefact_root/scientific-summary.json"

python3 - "$artefact_root/scientific-summary.json" "$artefact_root/RESULTS.txt" <<'PY'
import json
import sys

summary = json.loads(open(sys.argv[1], encoding="utf-8").read())
lines = [f"{key}={summary[key]}" for key in (
    "done_count", "split_count", "pending_count", "objects_indexed",
    "deepest_split_depth", "split_depth", "max_depth")]
lines.append("split_by_depth=" + json.dumps(summary["split_by_depth"]))
lines.append("pending_by_depth=" + json.dumps(summary["pending_by_depth"]))
lines.append("shallowest_pending:")
lines += [f"  {p or '/'}" for p in summary["shallowest_pending"]]
open(sys.argv[2], "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY

size=$(stat -c %s "$artefact_root/scientific-summary.json")
if [[ "$size" -gt 65536 ]]; then
  echo "scientific-summary.json exceeds 64 KiB: $size" >&2
  exit 6
fi
echo "readout complete: summary ${size} octets"
