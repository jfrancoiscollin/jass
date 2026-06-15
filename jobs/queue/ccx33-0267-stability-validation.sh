#!/usr/bin/env bash
# id: ccx33-0267-stability-validation
# description: VALIDATION de l'idée « stabilité → fiabilité du label » (filtrage par confiance
# de recherche). Hypothèse : un score qui OSCILLE entre profondeurs n'a pas convergé = label-
# bruit ; un score STABLE (même signe, faible Δ) est fiable. On le TESTE contre la VÉRITÉ Scan :
# parmi les FINALES du master, les positions où NOTRE recherche est stable s'accordent-elles avec
# Scan bien plus que les instables ? Si oui → le filtre extrait proprement les labels fiables de
# notre recherche (faible) → on entraînera l'éval de finale dessus. Outils EXISTANTS (pas de C++).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0267-stability-validation/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
MASTER=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
[ -f "$MASTER" ] || { echo "ABORT: master introuvable"; exit 3; }

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "KING-AWARE patterns ENABLED" "$ART/cmake.log" || { echo "ABORT: pas king-aware"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- 1) labeler king-aware = distillation SCORE sur le master (≈ 0261 noPW) ---
echo "=== distille un labeler king-aware (score, l2=1e-4) ==="
$JASS --dump-eval-features "$MASTER" "$ART/featM" 2>&1 | tail -1
python3 pattern_jass/tools/train.py --data "$MASTER" --scan-eval --king-patterns \
    --eval-features-file "$ART/featM" --target score --score-clip 2000 --score-drop 4900 \
    --l2 1e-4 --max-iter 300 --scale 1000 --prune --full-fold --out "$ART/labeler.pjtw" >"$ART/labeler-train.log" 2>&1
[ -f "$ART/labeler.pjtw" ] || { echo "ABORT: labeler échoué"; tail -8 "$ART/labeler-train.log"; exit 7; }

# --- 2) extrait un sous-ensemble FINALES (popcount<=14) du master (cap 150k pour la vitesse) ---
echo "=== extrait les finales (popcount<=14) du master ==="
python3 - "$MASTER" "$ART/endg.jnnw" 150000 <<'PY'
import sys; sys.path.insert(0,'pattern_jass/tools')
import numpy as np, struct, master_loader
src,dst,cap=sys.argv[1],sys.argv[2],int(sys.argv[3])
ds=master_loader.load(src); REC=38
def pc(a): return np.unpackbits(a.view(np.uint8)).reshape(len(a),64).sum(axis=1)
pieces=pc(ds.white_men)+pc(ds.white_kings)+pc(ds.black_men)+pc(ds.black_kings)
idx=np.flatnonzero(pieces<=14)[:cap]
raw=open(src,'rb').read(); body=raw[8:]
out=bytearray(b'JNNW'); out+=struct.pack('<I',len(idx))
mv=memoryview(body)
for i in idx: out+=mv[i*REC:(i+1)*REC]
open(dst,'wb').write(out)
print(f"finales extraites : {len(idx)} (popcount<=14) sur {ds.n_records}")
PY

# --- 3) re-label ces finales avec NOTRE recherche à d8/d10/d12 (le labeler en moteur) ---
for D in 8 10 12; do
  echo "=== rewrite-scores-with-search depth=$D ==="
  $JASS --rewrite-scores-with-search "$ART/endg.jnnw" "$ART/endg-d$D.jnnw" --nnue "$ART/labeler.pjtw" --depth "$D" >"$ART/rw-d$D.log" 2>&1 \
    || { echo "ABORT rewrite d$D"; tail -5 "$ART/rw-d$D.log"; exit 8; }
done

# --- 4) la stabilité prédit-elle l'accord avec Scan ? ---
echo "=== analyse stabilité → justesse ==="
python3 tools/stability_filter.py --base "$ART/endg.jnnw" \
    --scored "$ART/endg-d8.jnnw" "$ART/endg-d10.jnnw" "$ART/endg-d12.jnnw" \
    --depths 8 10 12 --delta 30 --pieces-max 14 --score-drop 4900 --out "$ART/report.txt"

echo; echo "=========================================================="
echo "   ccx33-0267 — VALIDATION : la STABILITÉ de recherche prédit-elle la JUSTESSE (vs Scan) ?"
echo "----------------------------------------------------------"
cat "$ART/report.txt"
echo "----------------------------------------------------------"
echo "  accord(stable) >> accord(instable) → FILTRE VALIDE : prochaine étape = entraîner l'éval"
echo "     de finale UNIQUEMENT sur les positions stables (labels fiables extraits de notre recherche)."
echo "  ≈ égal → la stabilité ne discrimine pas ; il faut un teacher plus fort (Scan/bitbases)."
echo "=========================================================="
