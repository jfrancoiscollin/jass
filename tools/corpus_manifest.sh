#!/usr/bin/env bash
# corpus_manifest.sh — inventaire TRAÇABLE des shards du corpus 30M committés sur origin/main.
#
# Pourquoi : historiquement les gros datasets (0106 2M, 0084 6.74M, le 9.48M...) ont été
# PERDUS car ils vivaient en artefacts.src (éphémère, box) et jamais committés. Cette fois
# chaque maillon committe un shard gzippé <=95Mo dans artefacts/ (durable, git). Ce script
# liste ces shards + leur compte d'enregistrements (lu dans l'en-tête JNNW) pour qu'aucun
# morceau ne se "volatilise" sans qu'on le voie, et donne le point de réassemblage.
#
# Usage :
#   tools/corpus_manifest.sh                 # imprime le manifeste + écrit docs/CORPUS_30M_MANIFEST.md
#   tools/corpus_manifest.sh assemble OUT    # décompresse+fusionne tous les shards en UN .jnnw (OUT)
#
# Format JNNW : 4o magic 'JNNW' + 4o uint32 LE (n_records) + body (REC=38o/record).
set -uo pipefail
cd "$(dirname "$0")/.."
REC=38
git fetch origin main -q 2>/dev/null || true

# liste des shards corpus committés (chemins git), triés
mapfile -t SHARDS < <(git ls-tree -r --name-only origin/main 2>/dev/null \
  | grep -E 'jobs/results/.*/artefacts/.*corpus.*\.jnnw\.gz$' | sort)

count_of(){ # lit n_records depuis l'en-tête JNNW d'un shard gzippé (8 premiers octets décompressés)
  git cat-file blob "origin/main:$1" 2>/dev/null | gunzip 2>/dev/null | head -c 8 \
    | python3 -c "import sys,struct; b=sys.stdin.buffer.read(); print(struct.unpack('<I',b[4:8])[0] if b[:4]==b'JNNW' else -1)" 2>/dev/null
}
blobsize_of(){ git cat-file -s "origin/main:$1" 2>/dev/null || echo 0; }

if [ "${1:-}" = "assemble" ]; then
  OUT="${2:?usage: corpus_manifest.sh assemble OUT.jnnw}"
  TMP="$(mktemp)"; : > "$TMP"; TOT=0
  echo "assemblage de ${#SHARDS[@]} shards -> $OUT" >&2
  for s in "${SHARDS[@]}"; do
    n=$(count_of "$s"); [ -z "$n" ] && n=-1
    if [ "$n" -le 0 ]; then echo "  ⚠️  SKIP (en-tête illisible/vide) : $s" >&2; continue; fi
    git cat-file blob "origin/main:$s" | gunzip | tail -c +9 >> "$TMP"   # body (saute les 8o d'en-tête)
    TOT=$((TOT+n)); echo "  + $n  ($s)" >&2
  done
  python3 - "$TMP" "$OUT" "$TOT" <<'PY'
import sys,struct
tmp,out,tot=sys.argv[1],sys.argv[2],int(sys.argv[3])
body=open(tmp,'rb').read()
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body)
print(f"écrit {out} : {tot} records, {len(body)+8} octets")
PY
  rm -f "$TMP"; exit 0
fi

# --- mode manifeste ---
DOC="docs/CORPUS_30M_MANIFEST.md"
TOTN=0; TOTB=0; ROWS=""
for s in "${SHARDS[@]}"; do
  n=$(count_of "$s"); [ -z "$n" ] && n=-1
  b=$(blobsize_of "$s"); mb=$(awk "BEGIN{printf \"%.1f\", $b/1048576}")
  flag=""; [ "$n" -le 0 ] && flag=" ⚠️VIDE/ILLISIBLE"
  [ "$n" -gt 0 ] && { TOTN=$((TOTN+n)); TOTB=$((TOTB+b)); }
  ROWS="${ROWS}| \`${s}\` | ${n} | ${mb} Mo${flag} |\n"
done
TOTMB=$(awk "BEGIN{printf \"%.0f\", $TOTB/1048576}")
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)

{
  echo "# Manifeste du corpus 30M — shards committés (traçabilité durable)"
  echo
  echo "> Généré par \`tools/corpus_manifest.sh\` le **${NOW}**. Ne PAS éditer à la main : re-lancer le script."
  echo "> Raison d'être : éviter qu'un shard se \"volatilise\" sans trace (cf. 0106/0084/9.48M perdus, faute"
  echo "> d'avoir été committés). Chaque shard ci-dessous est dans git (\`artefacts/\`, durable), pas en \`artefacts.src\`."
  echo
  echo "**Total : ${TOTN} positions · ${TOTMB} Mo gz · ${#SHARDS[@]} shards.**"
  echo
  echo "| Shard (chemin git origin/main) | Records | Taille gz |"
  echo "|---|---|---|"
  echo -e "$ROWS" | sed '/^$/d'
  echo
  echo "## Réassemblage (point de reconstruction)"
  echo '```bash'
  echo "tools/corpus_manifest.sh assemble /root/cw-corpus/big.jnnw   # décompresse+fusionne tous les shards en UN .jnnw"
  echo '```'
  echo "Puis le fit au scale : \`pattern_jass/tools/train_stream.py --data big.jnnw ...\` (streaming disque, gradient exact)."
  echo
  echo "## Vérification d'intégrité"
  echo "- Un shard à \`⚠️VIDE/ILLISIBLE\` = en-tête JNNW absent → **alerte** (comme 0106 dont les shards committés font 0 octet)."
  echo "- Re-lancer ce script après chaque finalize de maillon corpus pour rafraîchir le total."
} > "$DOC"

echo "=== manifeste écrit dans $DOC ==="
cat "$DOC"
