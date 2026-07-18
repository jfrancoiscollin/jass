#!/usr/bin/env bash
# id: 0142-pattern-tdleaf
# description: TD-leaf(λ) sur le pattern — entraînement SEARCH-AWARE (le
# pattern apprend à partir des valeurs de FEUILLE de sa propre recherche,
# pas de scores statiques). C'est le levier méthodo Scan jamais fait.
#
# Boucle (réutilise la machinerie testée) :
#   gen-tdleaf (self-play pattern → feuilles PV + valeurs)
#   → td_leaf_targets.py (λ-return) → handcrafted aligné
#   → train.py (re-fit pattern sur cibles bootstrappées) → nouveau .pjtw
# itéré N fois. Bench vs pattern de départ + vs v15 movetime.
#
# Pattern de départ : celui de 0141 (propre+tuné) si dispo, sinon 0131.
# expected_duration: ~1.5-2.5 h (N itérations).
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0142-pattern-tdleaf"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

PAT0=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/pattern_clean.pjtw
[ -f "$PAT0" ] || PAT0=/root/jass/jobs/results/0131-phase3-scan-bootstrap-full/artefacts.src/pattern_jass_v9_scan_full.pjtw
[ -f "$PAT0" ] || PAT0=$(find /root/jass/jobs/results -name '*.pjtw' 2>/dev/null | head -1)
[ -n "$PAT0" ] && [ -f "$PAT0" ] || { echo "ABORT: pattern de départ introuvable"; exit 3; }
echo "pattern départ : $PAT0"
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)

echo; echo "=== deps + build ==="
python3 -c "import numpy, scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }

rate_pj () { grep -oE 'rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | tail -1; }
rate_pv () { grep -oE 'PATTERN score rate vs NNUE: [0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }

# moniteur de convergence (cheap) : 90 parties pour un signal moins bruité
bench_hc () { ./build-prod/jass --benchmark-pattern-jass "$1" 6 5 2>&1 | tee "$2"; }

# baseline : pattern de départ
cp "$PAT0" "$ART/pattern_iter0.pjtw"
bench_hc "$ART/pattern_iter0.pjtw" "$ART/bench-iter0-hc.log" >/dev/null
R0_HC=$(rate_pj "$ART/bench-iter0-hc.log")
echo "iter0 (départ) vs handcrafted : $R0_HC"

# Self-play TD-leaf jusqu'à CONVERGENCE (on ne benche le pattern contre
# v15/Scan que sur le pattern convergé — sinon faux négatif). Le moniteur
# cheap (vs handcrafted) sert de thermomètre : on garde le MEILLEUR et on
# s'arrête sur plateau.
N_ITERS=15; NG=2500; DEPTH=8; LAM=0.7; STALL_MAX=4
CUR="$ART/pattern_iter0.pjtw"
BEST="$CUR"; BEST_R="${R0_HC:-0}"; BEST_IT=0; STALL=0
for it in $(seq 1 $N_ITERS); do
    echo; echo "=== TD-leaf itération $it/$N_ITERS ==="
    LEAVES="$ART/td-it${it}.jnnw"; TGT="$ART/targets-it${it}.jnnw"; HC="$ART/hc-it${it}.jnnw"
    NEW="$ART/pattern_iter${it}.pjtw"
    ./build-prod/jass --gen-tdleaf "$CUR" "$NG" "$DEPTH" "$LEAVES" 200 "$it" \
        > "$ART/gen-it${it}.log" 2>&1
    python3 tools/td_leaf_targets.py --leaves "$LEAVES" --games "${LEAVES}.games" \
        --out "$TGT" --lam "$LAM" --terminal-cp 5000 >> "$ART/gen-it${it}.log" 2>&1
    ./build-prod/jass --rewrite-scores-with-handcrafted "$TGT" "$HC" >> "$ART/gen-it${it}.log" 2>&1
    python3 pattern_jass/tools/train.py --data "$TGT" --skeleton-data "$HC" \
        --out "$NEW" --target score --score-clip 5000 --l2 1e-5 --max-iter 200 --scale 1000 \
        > "$ART/train-it${it}.log" 2>&1 || { echo "  train it$it FAIL"; tail "$ART/train-it${it}.log"; break; }
    bench_hc "$NEW" "$ART/bench-it${it}-hc.log" >/dev/null
    R=$(rate_pj "$ART/bench-it${it}-hc.log")
    echo "  iter$it vs handcrafted : ${R:-n/a}  (best=$BEST_R @ it$BEST_IT)"
    # suivi du meilleur + plateau (le moniteur dit quand on a convergé)
    improved=$(awk -v r="${R:-0}" -v b="$BEST_R" 'BEGIN{print (r>b+0.01)?1:0}')
    if [ "$improved" = "1" ]; then BEST="$NEW"; BEST_R="$R"; BEST_IT="$it"; STALL=0;
    else STALL=$((STALL+1)); fi
    rm -f "$LEAVES" "${LEAVES}.games" "$TGT" "$HC"
    CUR="$NEW"
    if [ "$STALL" -ge "$STALL_MAX" ]; then
        echo "  plateau ($STALL itérations sans gain) → convergence, arrêt"; break
    fi
done
FINAL="$BEST"     # pattern CONVERGÉ (meilleur via moniteur), pas le dernier
echo; echo "convergé : meilleur pattern = iter$BEST_IT (vs handcrafted $BEST_R)"

echo; echo "=== bench final : pattern(TD-leaf) convergé vs v15 (depth + movetime) ==="
if [ -n "${V15:-}" ] && [ -f "$V15" ]; then
    ./build-prod/jass --benchmark-pattern-vs-nnue "$PAT0"  "$V15" 64 5 1 300 "" 2>&1 | tee "$ART/start-vs-v15-mt.log"
    R_START_V15=$(rate_pv "$ART/start-vs-v15-mt.log")
    # convergé : à profondeur fixe (vitesse invisible) ET movetime (vitesse compte)
    ./build-prod/jass --benchmark-pattern-vs-nnue "$FINAL" "$V15" 8 5 1 0   "" 2>&1 | tee "$ART/final-vs-v15-d8.log"
    R_FINAL_V15_D=$(rate_pv "$ART/final-vs-v15-d8.log")
    ./build-prod/jass --benchmark-pattern-vs-nnue "$FINAL" "$V15" 64 5 1 300 "" 2>&1 | tee "$ART/final-vs-v15-mt.log"
    R_FINAL_V15=$(rate_pv "$ART/final-vs-v15-mt.log")
    # Watch-item (cf docs/archives/PATTERN_PROGRAM_NOTES.md §1) : un pattern rapide
    # doit faire MIEUX en movetime qu'à profondeur fixe. Si movetime < depth,
    # sa recherche profonde ne paie pas → suspecter time-mgmt/aspiration en
    # haute profondeur (ou instabilité éval).
    awk -v mt="${R_FINAL_V15:-1}" -v d="${R_FINAL_V15_D:-0}" 'BEGIN{
        if (mt+0 < d+0 - 0.03)
            print "  ⚠️  ALERTE watch-item : movetime("mt") < depth("d") — la recherche profonde du pattern ne paie pas. Voir docs/archives/PATTERN_PROGRAM_NOTES.md §1 (time-mgmt haute profondeur)."
        else
            print "  ✓ movetime("mt") >= depth("d") : la vitesse paie (pas de souci time-mgmt)."
    }'
fi

echo; echo "=========================================================="
echo "        0142 TD-LEAF PATTERN — VERDICT"
echo "=========================================================="
echo "  vs handcrafted par itération :"
echo "    iter0 (départ) : $R0_HC"
for it in $(seq 1 $N_ITERS); do
    r=$(rate_pj "$ART/bench-it${it}-hc.log" 2>/dev/null)
    [ -n "$r" ] && echo "    iter$it          : $r"
done
echo
echo "  pattern vs v15 @ movetime : départ=${R_START_V15:-n/a}  TD-leaf=${R_FINAL_V15:-n/a}"
python3 - "${R0_HC:-}" "$(rate_pj "$ART/bench-it${N_ITERS}-hc.log" 2>/dev/null)" "${R_START_V15:-}" "${R_FINAL_V15:-}" <<'EOF'
import sys
def f(x):
    try: return float(x)
    except: return None
r0,rN,sv,fv=map(f,sys.argv[1:5])
print()
if r0 is not None and rN is not None:
    d=rN-r0
    print(f"  → TD-leaf vs handcrafted : {r0:.3f} → {rN:.3f} ({d:+.3f})",
          "→ TD-leaf AMÉLIORE le pattern" if d>0.02 else "→ pas d'amélioration nette")
if sv is not None and fv is not None:
    print(f"  → vs v15 movetime : {sv:.3f} → {fv:.3f} ({fv-sv:+.3f})")
    if fv>=0.50: print("     → pattern(TD-leaf) >= v15 à temps égal : path pattern validé.")
EOF
echo "=========================================================="
