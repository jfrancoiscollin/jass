#!/usr/bin/env bash
# id: 0151-v3-diagnose
# description: DIAGNOSTIC du prior v3 qui perd 0/90 vs v15 (0147). On localise
# la v3 par rapport au SQUELETTE handcrafted (le baseline robuste qu'elle a
# REMPLACÉ en mode standalone), et on inspecte si elle valorise le MATÉRIEL.
# But : distinguer « éval faible (plafond) » de « standalone CASSÉE / pire que
# le baseline » → repasser HYBRIDE (skeleton + correction).
#
# Triangle de calibration (tout depth 8, vitesse neutre) :
#   - v3 vs handcrafted  (--benchmark-scan-eval <v3> hc) : bat-elle le baseline ?
#   - v15 vs handcrafted (--benchmark-nnue <v15>)        : réf. de force de v15
#   (v3 vs v15 = 0/90, déjà connu)
# Lecture :
#   v3 > hc  → éval OK, juste plus faible que v15 = plafond de capacité.
#   v3 ≈ hc  → distillation n'apporte rien mais ne casse rien.
#   v3 < hc  → standalone CASSÉE → HYBRIDE.
# + inspection poids matériel : homme<<1pu ou roi<<3pu ⇒ gaffes ⇒ 0/90.
#
# expected_duration: ~30-45 min.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0151-v3-diagnose"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

V3=$(ls -t /root/jass/jobs/results/0147-scan-eval-full/artefacts.src/scan_eval_v3.pjtw 2>/dev/null | head -1)
[ -n "$V3" ] && [ -f "$V3" ] || { echo "ABORT: v3 (0147) manquant"; exit 3; }
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }
echo "v3 : $V3"; echo "v15: $V15"

echo; echo "=== build prod + tests ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || { echo "TESTS FAIL"; tail -20 "$ART/tests.log"; exit 6; }

anyrate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }

echo; echo "########## (1) TRIANGLE DE CALIBRATION (depth 8) ##########"
echo "--- v3 vs handcrafted ---"
./build-prod/jass --benchmark-scan-eval "$V3" hc 8 5 1 0 "" 64 2>&1 | tee "$ART/v3-vs-hc.log"
R_V3HC=$(anyrate "$ART/v3-vs-hc.log")
echo "--- v15 vs handcrafted (réf.) ---"
./build-prod/jass --benchmark-nnue "$V15" 8 5 1 0 2>&1 | tee "$ART/v15-vs-hc.log"
R_V15HC=$(anyrate "$ART/v15-vs-hc.log")

echo; echo "########## (2) INSPECTION DES POIDS MATÉRIEL ##########"
python3 - "$V3" <<'PYEOF'
import struct, sys
import numpy as np
raw=open(sys.argv[1],'rb').read()
magic,ver,scale,n_pat,n_ext=struct.unpack_from('<IIIII',raw,0)
off=20
pat_mg=np.frombuffer(raw,dtype='<i4',offset=off,count=n_pat); off+=4*n_pat
pat_eg=np.frombuffer(raw,dtype='<i4',offset=off,count=n_pat); off+=4*n_pat
ext_mg=np.frombuffer(raw,dtype='<i4',offset=off,count=n_ext); off+=4*n_ext
ext_eg=np.frombuffer(raw,dtype='<i4',offset=off,count=n_ext)
s=float(scale)
def pu(x): return x/s
# layout: bk PST 0..49, wk PST 50..99, blackmen 100, whitemen 101,
# blackmob 102, whitemob 103, blackbal 104, whitebal 105
print(f"scale={scale} (poids/{scale}=piece-units ; ~1.0=un homme, ~3=un roi)")
print(f"HOMMES   : black_men mg={pu(ext_mg[100]):+.2f} eg={pu(ext_eg[100]):+.2f}"
      f"   white_men mg={pu(ext_mg[101]):+.2f} eg={pu(ext_eg[101]):+.2f}")
bk=pu(ext_mg[0:50]); wk=pu(ext_mg[50:100])
print(f"ROIS(PST): black moy={bk.mean():+.2f} (somme {bk.sum():+.1f}, max {bk.max():+.2f})"
      f"   white moy={wk.mean():+.2f}")
print(f"MOBILITÉ : black={pu(ext_mg[102]):+.3f} white={pu(ext_mg[103]):+.3f}")
print(f"BALANCE  : black={pu(ext_mg[104]):+.3f} white={pu(ext_mg[105]):+.3f}")
print(f"PATTERNS : nnz={(pat_mg!=0).sum()}/{n_pat}  |w|max={pu(np.abs(pat_mg).max()):.2f}pu")
print()
man=pu(ext_mg[100]); king=bk.mean()
verdict_mat = ("⚠️ MATÉRIEL SOUS-ÉVALUÉ" if (abs(man)<0.5 or abs(king)<1.5)
               else "matériel plausible")
print(f"  → homme≈{man:+.2f}pu (cible ~+1), roi≈{king:+.2f}pu (cible ~+3) : {verdict_mat}")
PYEOF

echo; echo "=========================================================="
echo "        0151 DIAGNOSTIC v3 — LECTURE"
echo "=========================================================="
echo "  v3 vs hc  = ${R_V3HC:-?}   |   v15 vs hc = ${R_V15HC:-?}"
python3 - "${R_V3HC:-}" "${R_V15HC:-}" <<'EOF'
import sys
def f(x):
    try: return float(x)
    except: return None
v3hc,v15hc=f(sys.argv[1]),f(sys.argv[2])
if v3hc is not None:
    if v3hc < 0.40:
        print("  → v3 PERD vs handcrafted → la distillation standalone est PIRE")
        print("    que le baseline qu'elle remplace → REPASSER HYBRIDE")
        print("    (eval = handcrafted skeleton + correction structurée).")
    elif v3hc < 0.55:
        print("  → v3 ≈ handcrafted : ne casse rien mais n'apporte rien en jeu")
        print("    (le fit 29% R² ne se traduit pas en force) → hybride + fine-tune.")
    else:
        print("  → v3 BAT handcrafted : éval saine, plus faible que v15 = plafond")
        print("    de capacité → fine-tune (0149) + profondeur (0150).")
EOF
echo "=========================================================="
