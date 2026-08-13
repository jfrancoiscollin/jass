#!/usr/bin/env bash
# Rend LISIBLES les compteurs du catalogue MegaCorpus.
#
# ⛔ POURQUOI CE JOB EXISTE, ET IL NE DEVRAIT PAS. `cpx62-1271` a produit
# `catalog-summary.json` (1 470 o) — mais le runner n'inline que les noms de
# `STATUS_SUMMARY_NAMES`, et `catalog-summary.json` n'en fait pas partie. Le
# verdict existe sur R2 et reste illisible de la ou on decide. C'est la
# TROISIEME occurrence de cette classe dans ce seul fil (cpx62-1206, l'autopsie
# 1268, ici) et la lecon est toujours la meme : un resultat n'existe pas tant
# qu'il n'est pas TRANSPORTE.
#
# AUCUN census, aucun corpus, aucun payload : trois copies nommees, un parse.
set -Eeuo pipefail

result_root=${JASS_RESULT_DIR:?}; artefact_root=${JASS_ARTEFACT_DIR:?}
attempt_uri=${CENSUS_ATTEMPT_URI:?}
work="$result_root/catalog-readout"; mkdir -p "$work" "$artefact_root"
command -v rclone >/dev/null || { echo "rclone missing" >&2; exit 4; }

for name in catalog-summary.json JASS_CONTROL_SUMMARY.json RESULTS.txt; do
  timeout 300s rclone copyto "$attempt_uri/$name" "$work/$name" \
    --retries 3 --low-level-retries 10 || echo "(absent: $name)" >&2
done

python3 - "$work" "$artefact_root/scientific-summary.json" <<'PY'
import json
import sys
from pathlib import Path

work, output = Path(sys.argv[1]), Path(sys.argv[2])
summary = {"schema": "jass.megacorpus_catalog_readout.v1"}
for name in ("catalog-summary.json", "JASS_CONTROL_SUMMARY.json"):
    path = work / name
    if not path.exists():
        summary[name] = "absent"
        continue
    try:
        summary[name] = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        summary[name] = f"illisible: {exc}"
results = work / "RESULTS.txt"
summary["RESULTS.txt"] = (
    results.read_text(encoding="utf-8")[-8000:] if results.exists() else "absent"
)
text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
# Le plafond de transport est a 64 KiB ; ces fichiers pesent des centaines
# d'octets, mais on ne publie pas un resume qu'on n'a pas borne.
if len(text.encode("utf-8")) > 60000:
    summary = {k: v for k, v in summary.items() if k != "RESULTS.txt"}
    summary["truncated"] = "RESULTS.txt dropped to stay under the runner cap"
    text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
output.write_text(text, encoding="utf-8")
print(text[:2000])
PY
cp "$artefact_root/scientific-summary.json" "$artefact_root/RESULTS.txt"
echo "catalog readout complete"
