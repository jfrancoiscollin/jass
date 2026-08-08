#!/usr/bin/env bash
# Recupere le verdict de cpx62-1206 (M18) depuis le stockage objet.
#
# POURQUOI CE JOB EXISTE. Le runner n'inline un summary dans le statut GitOps
# que sous 64 KiB (`STATUS_SUMMARY_MAX_FILE_BYTES`), et il saute le fichier EN
# SILENCE au-dela. M18 a rendu 530 163 octets -- 20 lignes bras x graine, chacune
# avec ses matrices de confusion par barreau -- donc `scientific_summaries` est
# ressorti VIDE et le verdict n'existe que dans R2. La science est faite et
# valide (exit_code 0, 24 artefacts) : il n'y a rien a recalculer, seulement a
# republier au bon format. Cout : quelques secondes, contre 37 min de re-run.
set -Eeuo pipefail

job_id=${JASS_JOB_ID:?JASS_JOB_ID is required}
artefact_root=${JASS_ARTEFACT_DIR:?JASS_ARTEFACT_DIR is required}
src="r2:jass-data/runs/cpx62-1206-mini-jass-m18-wdl-policy-iteration-microscope-v1/20260808T151806Z-153b4b12/artefacts"
mkdir -p "$artefact_root"

rclone cat "$src/RESULTS.txt"        >"$artefact_root/RESULTS.txt"
rclone cat "$src/PHASE_TIMINGS.txt"  >"$artefact_root/PHASE_TIMINGS.txt"
rclone cat "$src/scientific-summary.json" >"$artefact_root/m18-full-summary.json"

# Le compact : agregat + contrastes + recommandation + hashes, SANS les lignes
# par graine. C'est ce qui decide, et ca passe sous les 64 KiB.
python3 - "$artefact_root/m18-full-summary.json" \
  "$artefact_root/scientific-summary.json" <<'PY'
import json
from pathlib import Path
import sys

full = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
rows = full.get("seed_results", {})
compact = {key: value for key, value in full.items() if key != "seed_results"}
compact["seed_results"] = {
    "omitted_from_compact_output": True,
    "reason": "runner inlines a status summary only under 64 KiB",
    "full_record": "m18-full-summary.json (artefact of this job)",
    "row_count": sum(len(v) for v in rows.values()) if isinstance(rows, dict) else 0,
}
out = Path(sys.argv[2])
out.write_text(json.dumps(compact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
size = out.stat().st_size
# Sans cette garde on rejouerait exactement le bug qu'on repare.
if size > 65536:
    raise SystemExit(f"compact summary still {size} bytes > 65536")
print(f"compact_summary_bytes={size}")
PY

echo "job_id=$job_id" >>"$artefact_root/RESULTS.txt"
cat "$artefact_root/PHASE_TIMINGS.txt" >>"$artefact_root/RESULTS.txt"
