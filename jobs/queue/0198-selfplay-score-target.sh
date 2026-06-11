#!/usr/bin/env bash
# id: 0198-selfplay-score-target
# description: RECETTE SCAN — étape 4 : la CIBLE, pas les données. 0196 a
# triangulé le goulot : master+WDL=0.22, self-play-1M+WDL=0.22, master+score
# (champion)=0.39 — même classe linéaire. Le plafond 0.22 est le LABEL WDL,
# pas le modèle ni les données. On teste ça directement : MÊME data self-play
# 1M, on swappe juste la cible WDL→SCORE (le champ score = eval de recherche
# du champion @movetime 30ms, déjà écrit par --gen-data-wdl, donc AUCUN
# re-label). Recette score IDENTIQUE au champion, sur self-play au lieu du
# master.
#
#   * self-play+score ≈ 0.39 (champion) ⇒ la cible EST le levier ; la data
#     self-play vaut le master pour la distillation ; on a un signal dense
#     teacher-free (le compounding façon AlphaZero = labels de recherche
#     profonde, pas WDL). On itère sur la cible/profondeur, PAS sur NNUE.
#   * self-play+score ≈ 0.22 (= WDL) ⇒ surprise : ce n'est pas la cible →
#     re-poser la question (features ? data self-play pauvre ?).
#
#   Réutilise sp-all.jnnw + sp.feat de 0196 (persistent sur le runner) → pas
#   de génération. Sweep l2 ∈ {1e-4, 3e-4}. Benches identiques à 0196.
#
# expected_duration: ~30-45 min (build + 2 fits + benches ; pas de génération).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/0198-selfplay-score-target/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
SP=/root/jass/jobs/results/0196-selfplay-wdl-1M/artefacts.src/sp-all.jnnw
FEAT=/root/jass/jobs/results/0196-selfplay-wdl-1M/artefacts.src/sp.feat
[ -f "$SP" ]   || { echo "ABORT: sp-all.jnnw de 0196 introuvable (runner reclamé ?) — re-générer 0196 d'abord"; exit 3; }
[ -f "$FEAT" ] || { echo "ABORT: sp.feat de 0196 introuvable"; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }
echo "=== reuse 0196 : $(ls -lh "$SP" | awk '{print $5}') data + $(ls -lh "$FEAT" | awk '{print $5}') feat ==="

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
./build-prod/jass_tests >"$ART/tests.log" 2>&1 && echo "tests OK" || { echo TESTS FAIL; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }
bench(){ ./build-prod/jass --benchmark-scan-eval "$1.pjtw" "$V15" 9  6 1 0   "" 64 >"$1-v15d9.log" 2>&1
         ./build-prod/jass --benchmark-scan-eval "$1.pjtw" "$V15" 64 4 1 300 "" 64 >"$1-v15mt.log" 2>&1
         ./build-prod/jass --benchmark-scan-eval "$1.pjtw" hc    8  6 1 0   "" 64 >"$1-hc.log"    2>&1; }

# sanity : le champ score est-il exploitable (pas tout à zéro) ?
echo "=== stats du champ score dans sp-all.jnnw ==="
python3 - "$SP" <<'PY'
import sys,struct,numpy as np
raw=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',raw[4:8])[0]; REC=38
sc=np.frombuffer(raw[8:8+n*REC], dtype=np.uint8).reshape(n,REC)[:,33:37].copy().view('<i4').ravel()
print(f"n={n}  score range=[{sc.min()},{sc.max()}]  std={sc.std():.1f}  nonzero={100*(sc!=0).mean():.1f}%  |s|>4900={100*(np.abs(sc)>4900).mean():.1f}%")
PY

# --- score-target, recette IDENTIQUE au champion, sweep l2 -----------------
train_score(){ # <tag> <l2>
  python3 pattern_jass/tools/train.py --data "$SP" --scan-eval --eval-features-file "$FEAT" \
    --target score --score-clip 5000 --score-drop 4900 --l2 "$2" --max-iter 200 --scale 1000 \
    --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/$1.pjtw" >"$ART/$1-train.log" 2>&1
  [ -f "$ART/$1.pjtw" ] && bench "$ART/$1" || echo "  ABORT train $1"; }

for pair in "sps1e-4 1e-4" "sps3e-4 3e-4"; do
  set -- $pair
  echo "=== self-play + SCORE, l2=$2 ==="; train_score "$1" "$2"
  echo "  l2=$2 : v15 d9=$(rate "$ART/$1-v15d9.log")  mt=$(rate "$ART/$1-v15mt.log")  hc=$(rate "$ART/$1-hc.log")"
done

echo; echo "=========================================================="
echo "   0198 SELF-PLAY + SCORE (recette Scan étape 4) — VERDICT"
echo "  self-play+score l2=1e-4 : v15 d9=$(rate "$ART/sps1e-4-v15d9.log")  mt=$(rate "$ART/sps1e-4-v15mt.log")  hc=$(rate "$ART/sps1e-4-hc.log")"
echo "  self-play+score l2=3e-4 : v15 d9=$(rate "$ART/sps3e-4-v15d9.log")  mt=$(rate "$ART/sps3e-4-v15mt.log")  hc=$(rate "$ART/sps3e-4-hc.log")"
echo "  ANCRES : self-play+WDL 1M (0196)   = 0.22 d9   (même data, cible WDL)"
echo "           master+score champion     = 0.39 d9 / 0.33 mt"
echo "           master+WDL  (0194)        = 0.22 d9"
echo "  → score ≈ 0.39 = LA CIBLE est le levier (data self-play = master pour distill)"
echo "       → chemin compounding = labels de recherche PROFONDE, pas WDL. Pas NNUE."
echo "  → score ≈ 0.22 = ce n'est PAS la cible → features/data à ré-interroger."
echo "=========================================================="
