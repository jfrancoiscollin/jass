#!/usr/bin/env bash
# id: 0138-search-features-ab
# description: Phase 1 (search) — A/B de 3 nouvelles règles vs le défaut
# actuel (PVS on), réseau v15, à temps fixe (le test qui compte) :
#   - razoring        (razor_max_depth=3, razor_margin=200)
#   - probcut         (probcut_min_depth=5, margin=150, reduction=4)
#   - ext_promotion   (extension +1 ply quand un pion dame)
#   - combiné (les 3)
# Gate par feature : rate >= 0.53 à movetime → activer ce défaut.
# NB : en draughts les captures sont forcées → probcut ne se déclenche
# qu'aux nœuds tactiques (effet probablement faible, mesuré ici).
#
# expected_duration: ~2-3 h (4 matches × 90 games à mt 0.3s).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0138-search-features-ab"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"
NCPU=$(nproc)
export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 weights manquants"; exit 3; }
echo "v15 : $V15"

echo "=== build prod ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }

RAZOR="razor_max_depth=3,razor_margin=200"
PROBCUT="probcut_min_depth=5,probcut_margin=150,probcut_reduction=4"
EXT="ext_promotion=1"
COMBINED="$RAZOR,$PROBCUT,$EXT"

ab () {  # $1=label  $2=spec  $3=logfile  → match vs défaut à mt 0.3s, 90 games
    echo
    echo "=== $1 : A=[$2] vs B=[défaut] @ mt 0.3s, 90 games ==="
    ./build-prod/jass --benchmark-search-params "$V15" "$2" "" 64 5 1 300 \
        2>&1 | tee "$3"
}
ab "razoring"      "$RAZOR"    "$ART/razor.log"
ab "probcut"       "$PROBCUT"  "$ART/probcut.log"
ab "ext_promotion" "$EXT"      "$ART/ext.log"
ab "combined"      "$COMBINED" "$ART/combined.log"

rate () { grep -oE 'A score rate: [0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }

echo
echo "=========================================================="
echo "        0138 SEARCH FEATURES A/B — VERDICT (vs défaut, mt 0.3s)"
echo "=========================================================="
python3 - "$(rate "$ART/razor.log")" "$(rate "$ART/probcut.log")" \
            "$(rate "$ART/ext.log")" "$(rate "$ART/combined.log")" <<'EOF'
import sys, math
def elo(r):
    try: r=float(r)
    except: return "n/a"
    if r<=0: return "-inf"
    if r>=1: return "+inf"
    return f"{-400*math.log10(1/r-1):+.0f}"
labels=["razoring","probcut","ext_promotion","combined"]
specs =["razor_max_depth=3,razor_margin=200",
        "probcut_min_depth=5,probcut_margin=150,probcut_reduction=4",
        "ext_promotion=1",
        "(les 3)"]
keep=[]
for lab,sp,r in zip(labels,specs,sys.argv[1:5]):
    print(f"  {lab:14s}: rate {r or 'n/a':>6}  ELO {elo(r)}")
    try:
        if float(r) >= 0.53: keep.append((lab,sp))
    except: pass
print()
if keep:
    print("  → ACTIVER (rate>=0.53) :")
    for lab,sp in keep: print(f"      {lab}  [{sp}]")
    print("    committer ces défauts dans src/search_params.hpp.")
else:
    print("  → aucune feature ne passe le gate. Garder off ; passer à SPSA v2 / autres axes.")
print("  (95% CI ≈ ±84 ELO à 90 games — un rate ~0.53 est faible, à reconfirmer si limite.)")
EOF
echo "=========================================================="
