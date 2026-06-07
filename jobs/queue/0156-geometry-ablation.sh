#!/usr/bin/env bash
# id: 0156-geometry-ablation
# description: ABLATION par orientation du modèle 32-patterns de 0154 (A, qui
# fait 0.75 vs hc contre 0.444 pour les 8 verticales). Question : quelle
# géométrie porte le gain ? On annule (zéro) les buckets d'un groupe et on
# benche vs hc. Groupes : V(0-7) D(8-14) A(15-22) H(23-27) S(28-31).
#
#   full        : les 32 (réf 0154 ~0.75)
#   only-V      : 8 verticales seules → cross-check ≈ config A (0.444)
#   no-V/D/A/H/S : leave-one-out → contribution MARGINALE de chaque groupe
#                  (chute du taux quand on le retire ; les groupes se
#                   chevauchent donc non parfaitement additif — cf notes)
# + énergie de poids par groupe (Σw², nnz) — proxy gratuit.
# Lecture : groupes dont le retrait fait le plus chuter = à garder ; ceux
# quasi sans effet = candidats à l'élagage (→ éval plus rapide).
#
# expected_duration: ~40-60 min.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0156-geometry-ablation"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

A=$(ls -t /root/jass/jobs/results/0154-richer-patterns-distill/artefacts.src/A.pjtw 2>/dev/null | head -1)
[ -n "$A" ] && [ -f "$A" ] || { echo "ABORT: modèle 32-patterns A (0154) manquant"; exit 3; }
echo "modèle 32-patterns : $A"

echo; echo "=== build prod + tests (32 patterns) ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || { echo TESTS FAIL; tail -20 "$ART/tests.log"; exit 6; }
python3 -c "import numpy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy

# Helper : écrit une copie de A avec les patterns listés (indices) mis à ZÉRO.
ablate () {  # $1 out  $2 "comma,sep,pattern,indices to zero"
python3 - "$A" "$1" "$2" <<'PYEOF'
import struct, sys, numpy as np
src, out, zero = sys.argv[1], sys.argv[2], sys.argv[3]
raw = bytearray(open(src,'rb').read())
magic, ver, scale, n_pat, n_ext = struct.unpack_from('<IIIII', raw, 0)
B = 531441
off_mg = 20
off_eg = 20 + 4*n_pat
zeros = [int(x) for x in zero.split(',') if x != '']
for p in zeros:
    for base in (off_mg, off_eg):
        s = base + p*B*4
        raw[s : s + B*4] = b'\x00' * (B*4)
open(out,'wb').write(raw)
print(f"  wrote {out} (zeroed patterns {zeros})")
PYEOF
}

anyrate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }
bench () { ./build-prod/jass --benchmark-scan-eval "$1" hc 8 3 1 0 "" 64 > "$2" 2>&1; anyrate "$2"; }

# groupes (indices de patterns)
V="0,1,2,3,4,5,6,7"; D="8,9,10,11,12,13,14"; Aa="15,16,17,18,19,20,21,22"
H="23,24,25,26,27"; S="28,29,30,31"
ALL="$V,$D,$Aa,$H,$S"

echo; echo "=== énergie de poids par groupe (proxy gratuit) ==="
python3 - "$A" <<'PYEOF'
import struct, sys, numpy as np
raw=open(sys.argv[1],'rb').read()
_,_,s,n_pat,n_ext=struct.unpack_from('<IIIII',raw,0); B=531441
pm=np.frombuffer(raw,'<i4',n_pat,20).astype(np.float64)/s
pe=np.frombuffer(raw,'<i4',n_pat,20+4*n_pat).astype(np.float64)/s
groups={'V':range(0,8),'D':range(8,15),'A':range(15,23),'H':range(23,28),'S':range(28,32)}
for g,rng in groups.items():
    e=0.0; nz=0; npat=0
    for p in rng:
        a=pm[p*B:(p+1)*B]; b=pe[p*B:(p+1)*B]
        e+=float((a*a).sum()+(b*b).sum()); nz+=int((a!=0).sum()+(b!=0).sum()); npat+=1
    print(f"  {g}: {npat} patterns  Σw²={e:8.1f}  nnz={nz:7d}  énergie/pattern={e/npat:6.1f}")
PYEOF

echo; echo "=== benchs vs hc (depth 8) ==="
cp "$A" "$ART/full.pjtw"
echo "  full (32)   vs hc = $(bench "$ART/full.pjtw" "$ART/full-vs-hc.log")   (réf 0154 ~0.75)"
ablate "$ART/onlyV.pjtw" "$D,$Aa,$H,$S"
echo "  only-V (8)  vs hc = $(bench "$ART/onlyV.pjtw" "$ART/onlyV-vs-hc.log")   (cross-check ≈ 0.444)"
ablate "$ART/noV.pjtw" "$V";  echo "  no-V        vs hc = $(bench "$ART/noV.pjtw" "$ART/noV-vs-hc.log")"
ablate "$ART/noD.pjtw" "$D";  echo "  no-D        vs hc = $(bench "$ART/noD.pjtw" "$ART/noD-vs-hc.log")"
ablate "$ART/noA.pjtw" "$Aa"; echo "  no-A        vs hc = $(bench "$ART/noA.pjtw" "$ART/noA-vs-hc.log")"
ablate "$ART/noH.pjtw" "$H";  echo "  no-H        vs hc = $(bench "$ART/noH.pjtw" "$ART/noH-vs-hc.log")"
ablate "$ART/noS.pjtw" "$S";  echo "  no-S        vs hc = $(bench "$ART/noS.pjtw" "$ART/noS-vs-hc.log")"
rm -f "$ART"/*.pjtw

echo; echo "=========================================================="
echo "        0156 ABLATION GÉOMÉTRIE — VERDICT (vs hc)"
echo "=========================================================="
FULL=$(anyrate "$ART/full-vs-hc.log")
echo "  full (32)  = $FULL"
echo "  only-V (8) = $(anyrate "$ART/onlyV-vs-hc.log")   (attendu ≈ 0.444)"
for g in V D A H S; do
  r=$(anyrate "$ART/no${g}-vs-hc.log")
  echo "  no-$g       = ${r:-?}   → chute = contribution marginale de $g"
done
echo "  → grosse chute = orientation clé (garder) ; chute ~nulle = élaguer (vitesse)."
echo "=========================================================="
