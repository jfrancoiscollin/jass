#!/usr/bin/env bash
# id: 0133-rebaseline-v15-vs-scan
# description: Phase 0 du programme "battre Scan time-search". Re-mesure
# la référence actuelle (v15 NNUE 128-64 distillé Scan) contre Scan sur
# le HEAD courant — les chiffres -500/-550 ELO et 0.870 vs Scan d10
# datent de jobs antérieurs (0090+) et doivent être re-confirmés avant
# d'investir 3-4 mois. Fige le benchmark "north-star".
#
# Mesures :
#   A. movetime 0.5s, 1 thread, no-book  → north-star (eval+search pur)
#   B. movetime 0.5s, 4 threads, no-book → gain Lazy SMP en time-search
#   C. depth 10, 1 thread, no-book       → qualité à profondeur fixe
#      (doit re-confirmer ~0.87 — l'éval est censée battre Scan d10)
#
# no-book partout : on isole eval+search (le levier qu'on va travailler),
# pas le livre d'ouvertures.
#
# expected_duration: ~2-3 h wall (3 matches ; mt=0.5 ≈ 40-50 min/match
# à pairs=3, depth-10 plus rapide).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0133-rebaseline-v15-vs-scan"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"
NCPU=$(nproc)

echo "=== host : $(hostname)  nproc=$NCPU  mem=$(free -h | awk '/^Mem:/{print $2}') ==="

# --- v15 weights lookup (même source que 0132) -----------------------------
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
if [ -z "$V15" ] || [ ! -f "$V15" ]; then
    # fallback : n'importe quel 128-64 q.bin déjà produit
    V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
fi
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 128-64 weights introuvables"; exit 3; }
echo "v15 weights : $V15 ($(ls -lh "$V15" | awk '{print $5}'))"

echo
echo "=== Phase 1 : build prod ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }
echo "jass : $(./build-prod/jass --version 2>/dev/null)"

# --- Scan install (même pattern que 0019) ----------------------------------
SCAN_DIR=/root/jass/.scan
if [ ! -x "$SCAN_DIR/scan_linux" ]; then
    echo "=== installing Scan (rhalbersma/scan) ==="
    rm -rf "$SCAN_DIR"
    git clone --depth 1 https://github.com/rhalbersma/scan "$SCAN_DIR" \
        || { echo "ABORT: git clone scan failed"; exit 4; }
    chmod +x "$SCAN_DIR/scan_linux"
fi
SCAN="$SCAN_DIR/scan_linux"
echo "scan : $SCAN ($(ls -lh "$SCAN" | awk '{print $5}'))"

run_match () {  # $1=label  $2=logfile  shift 2 -> extra calibrate args
    local label="$1"; local log="$2"; shift 2
    echo
    echo "=== $label ==="
    local start; start=$(date +%s)
    # books off by default (no --jass-book / --scan-book) → eval+search pur
    python3 tools/calibrate_vs_scan.py \
        --jass /root/jass/build-prod/jass \
        --scan "$SCAN" \
        --nnue "$V15" \
        --pairs 3 \
        "$@" 2>&1 | tee "$log"
    echo "  wall : $(( $(date +%s) - start ))s"
}

run_match "A. movetime 0.5s, 1 thread (NORTH-STAR)" \
    "$ART/A-mt500-1t.log"   --movetime 0.5 --jass-threads 1
run_match "B. movetime 0.5s, 4 threads (SMP)" \
    "$ART/B-mt500-4t.log"   --movetime 0.5 --jass-threads 4
run_match "C. depth 10, 1 thread (qualité profondeur fixe)" \
    "$ART/C-d10-1t.log"     --depth 10     --jass-threads 1

# --- Résumé ----------------------------------------------------------------
extract () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }
RA=$(extract "$ART/A-mt500-1t.log"); RB=$(extract "$ART/B-mt500-4t.log"); RC=$(extract "$ART/C-d10-1t.log")

echo
echo "=========================================================="
echo "      0133 RE-BASELINE v15 vs SCAN — VERDICT"
echo "=========================================================="
echo "  v15 : $(basename "$V15")"
python3 - "$RA" "$RB" "$RC" <<'EOF'
import sys, math
def elo(r):
    try:
        r=float(r)
    except: return "n/a"
    if r<=0: return "-inf"
    if r>=1: return "+inf"
    return f"{-400*math.log10(1/r-1):+.0f}"
A,B,C=sys.argv[1:4]
print(f"  A  mt=0.5s 1t  : rate {A or 'n/a':>6}   ELO {elo(A)}   (north-star vs Scan)")
print(f"  B  mt=0.5s 4t  : rate {B or 'n/a':>6}   ELO {elo(B)}   (Lazy SMP)")
print(f"  C  depth 10    : rate {C or 'n/a':>6}   ELO {elo(C)}   (profondeur fixe)")
print()
print("  Rappel cibles : C devrait re-confirmer ~0.87 (éval > Scan d10).")
print("  A est le chiffre à faire monter sur 3-4 mois (cible -200 ELO ~ rate 0.24).")
EOF
echo "=========================================================="
