#!/usr/bin/env bash
# id: ccx33-0305-weight-sweep
# description: BALAYAGE des poids du gradient (ALPHA matériel, GAMMA centralité) pour trouver le réglage
# qui étale bien la cible sur [0.55,1] sans trop clamper (0304 : trop comprimé, std=0.03). Cheap :
# 1 coverage ≤7 fixe, relabel avec une grille (ALPHA,GAMMA) via env, mesure la distribution des
# gains gradués (std, % au plancher 0.55, % au plafond 1.0, moyenne). Recommande l'optimum DISTRIBUTION
# (std max avec % plancher modéré). NB : l'optimum CONVERSION (le vrai) = A/B d'entraînement ensuite.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0305-weight-sweep/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
WLD=/root/egdb_extracted/app; MTC=/root/egdb_mtc/app
ls "$WLD"/db2.idx1 "$MTC"/*.idx_mtc >/dev/null 2>&1 || { echo "ABORT: bases absentes"; exit 4; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
rm -rf build-egdb
cmake -S . -B build-egdb -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
cmake --build build-egdb -j"$NCPU" --target jass >"$ART/build.log" 2>&1 && echo "BUILD OK" || { echo BUILD FAIL; tail -15 "$ART/build.log"; exit 5; }
JASS=./build-egdb/jass

$JASS --gen-egdb-wld 120000 "$ART/cov.jnnw" "$WLD" 7 512 9999 2>&1 | tail -1

echo "ALPHA GAMMA | win-graded: n  mean  std  %floor(0.55)  %ceil(1.0)"
for A in 0.04 0.08 0.12 0.16 0.20; do
  for G in 0.008 0.02 0.04; do
    MTC_ALPHA=$A MTC_GAMMA=$G MTC_BETA=0.03 \
      $JASS --egdb-mtc-relabel "$ART/cov.jnnw" "$WLD" "$MTC" "$ART/s.jnnw" 1024 >/dev/null 2>&1
    python3 - "$ART/s.jnnw" "$A" "$G" <<'PY'
import sys,struct,numpy as np
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]; REC=38
sc=np.frombuffer(bytes().join(body[i*REC+33:i*REC+37] for i in range(n)),dtype='<i4').astype(np.float64)/10000.0
w=sc[sc>0.5]                 # win side (wld win: 0.55..1.0)
if len(w)==0: print(f"{sys.argv[2]:>5} {sys.argv[3]:>5} | aucune"); raise SystemExit
floor=float((np.isclose(w,0.55)).mean()*100); ceil=float((np.isclose(w,1.0)).mean()*100)
print(f"{sys.argv[2]:>5} {sys.argv[3]:>5} | n={len(w):6d}  mean={w.mean():.3f}  std={w.std():.3f}  floor={floor:5.1f}%  ceil={ceil:5.1f}%")
PY
  done
done

echo; echo "=========================================================="
echo "   ccx33-0305 — sweep poids gradient"
echo "  Optimum DISTRIBUTION = std la plus grande avec %floor raisonnable (<~20%) et %ceil pas trop"
echo "  haut → bonne utilisation de [0.55,1]. Puis A/B d'entraînement sur 2-3 finalistes = vrai optimum."
echo "=========================================================="
