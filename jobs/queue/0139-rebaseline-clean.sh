#!/usr/bin/env bash
# id: 0139-rebaseline-clean
# description: Re-baseline PROPRE après correctif du bridge. Le job 0137
# (match depth-fixe) était contaminé : 46/54 parties forfaitaient sur
# "illegal move from Scan" à cause d'une dérive de buffer stdout dans
# calibrate_vs_scan.py (déclenchée par un Jass lent / NNUE). Corrigé par
# un lecteur threadé + queue drainable. Ce job relance les 3 mesures avec
# le bridge corrigé pour obtenir le VRAI chiffre — surtout la question
# fondatrice : notre éval bat-elle Scan à profondeur égale (match C) ?
#
#   A. movetime 0.5s, 1 thread  (north-star ; était -685, doit re-confirmer)
#   B. movetime 0.5s, 4 threads (Lazy SMP)
#   C. depth 10, 1 thread       (éval à profondeur égale — était bidon 0.870)
#
# expected_duration: ~2-3 h wall.
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0139-rebaseline-clean"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"
NCPU=$(nproc)
export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

echo "=== host : $(hostname)  nproc=$NCPU ==="

V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 weights manquants"; exit 3; }
echo "v15 : $V15"

echo "=== build prod ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }

SCAN_DIR=/root/jass/.scan
if [ ! -x "$SCAN_DIR/scan_linux" ]; then
    rm -rf "$SCAN_DIR"
    git clone --depth 1 https://github.com/rhalbersma/scan "$SCAN_DIR" \
        || { echo "ABORT: git clone scan failed"; exit 4; }
    chmod +x "$SCAN_DIR/scan_linux"
fi
SCAN="$SCAN_DIR/scan_linux"

run_match () {  # $1=label $2=log ; shift 2 -> extra args
    local label="$1"; local log="$2"; shift 2
    echo; echo "=== $label ==="
    local start; start=$(date +%s)
    python3 tools/calibrate_vs_scan.py \
        --jass /root/jass/build-prod/jass --scan "$SCAN" --nnue "$V15" \
        --pairs 3 "$@" 2>&1 | tee "$log"
    echo "  wall : $(( $(date +%s) - start ))s"
    # garde-fou : signale toute partie 'illegal' (signe d'une régression bridge)
    local ill; ill=$(grep -cE 'illegal move' "$log" 2>/dev/null || echo 0)
    echo "  parties 'illegal' (doit être 0 avec le bridge corrigé) : $ill"
}

run_match "A. movetime 0.5s, 1 thread (NORTH-STAR)" "$ART/A-mt500-1t.log" --movetime 0.5 --jass-threads 1
run_match "B. movetime 0.5s, 4 threads (SMP)"       "$ART/B-mt500-4t.log" --movetime 0.5 --jass-threads 4
run_match "C. depth 10, 1 thread (ÉVAL @ prof. égale)" "$ART/C-d10-1t.log" --depth 10 --jass-threads 1

ext () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }
illc () { grep -cE 'illegal move' "$1" 2>/dev/null || echo 0; }
RA=$(ext "$ART/A-mt500-1t.log"); RB=$(ext "$ART/B-mt500-4t.log"); RC=$(ext "$ART/C-d10-1t.log")

echo
echo "=========================================================="
echo "      0139 RE-BASELINE PROPRE (bridge corrigé) — VERDICT"
echo "=========================================================="
echo "  illegal A/B/C : $(illc "$ART/A-mt500-1t.log")/$(illc "$ART/B-mt500-4t.log")/$(illc "$ART/C-d10-1t.log") (doivent être 0)"
python3 - "$RA" "$RB" "$RC" <<'EOF'
import sys, math
def elo(r):
    try: r=float(r)
    except: return "n/a"
    if r<=0: return "-inf"
    if r>=1: return "+inf"
    return f"{-400*math.log10(1/r-1):+.0f}"
A,B,C=sys.argv[1:4]
print(f"  A mt0.5s 1t : rate {A or 'n/a':>6}  ELO {elo(A)}  (north-star)")
print(f"  B mt0.5s 4t : rate {B or 'n/a':>6}  ELO {elo(B)}  (SMP)")
print(f"  C depth 10  : rate {C or 'n/a':>6}  ELO {elo(C)}  (ÉVAL @ prof. égale)")
print()
print("  Lecture de C (LA question fondatrice) :")
print("   - C >> 0.5  → notre éval bat Scan à prof. égale → 'speed-first' valide")
print("   - C ~ 0.5   → à parité → speed aide mais éval à améliorer aussi")
print("   - C << 0.5  → éval inférieure → la cible -200 exige du travail d'éval")
EOF
echo "=========================================================="
