#!/usr/bin/env bash
# id: cpx62-0211-cumulative-loop-1M
# description: DEBUG Nœud 2ter·B2 — CORPUS CUMULÉ, GROS VOLUME (box 32GB/16c). Même
# fix que ccx33-0210 (on ACCUMULE le self-play au lieu de régénérer 300k frais →
# couverture qui grandit gen-après-gen → compounding possible), mais à 1M/gen pour
# remplir la table 17M plus vite. gen_g s'entraîne sur l'UNION de tout le self-play
# jusqu'à g. Question : le proxy MONTE-t-il au-dessus de 0.41 quand la couverture
# grandit ? (0205b = 300k FRAIS/gen = plat ~0.41). Jeu profondeur FIXE (depth4) pour
# générer vite : on teste la DONNÉE/couverture, pas la profondeur.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0211-cumulative-loop-1M/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
REF=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
[ -f "$REF" ] || { echo "ABORT: master de référence (committé) introuvable"; exit 3; }

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
./build-prod/jass_tests >"$ART/tests.log" 2>&1 && echo "tests OK" || { echo TESTS FAIL; exit 6; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

proxy(){ python3 tools/eval_proxy.py --jass "$JASS" --eval "$1.pjtw" --testset "$REF" \
           --offset 1300000 --max 50000 --score-drop 4900 2>/dev/null | grep -oE 'spearman=[-0-9.]+' | head -1 | cut -d= -f2; }
fit_wdl(){ python3 pattern_jass/tools/train.py --data "$1" --scan-eval --eval-features-file "$2" \
            --loss logistic --l2 "$4" --max-iter 200 --scale 1000 --out "$3.pjtw" >"$3-train.log" 2>&1; }
coverage(){ python3 - "$1" <<'PY'
import numpy as np,struct,sys
sys.path.insert(0,'pattern_jass/tools'); import patterns as P
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38
a=np.frombuffer(b[8:8+n*REC],dtype=np.uint8).reshape(n,REC)
bb=a[:,0:32].copy().view('<u8').reshape(n,4)
c=np.bincount(P.flat_feature_columns(P.extract_indices(bb[:,2],bb[:,0])).ravel(),minlength=P.TOTAL_BUCKETS)
d=int((c>0).sum()); print(f"n={n} coverage={d} ({100*d/P.TOTAL_BUCKETS:.3f}%) ≤2visites={100*(c[c>0]<=2).mean():.0f}%des_touchés")
PY
}
# self-play N @ depth4, sharded, APPEND merged records into $CUM (a growing JNNW)
gen_and_append(){ local NN=$1; local OUTP=$2; local CUM=$3; shift 3; local PER=$(( (NN + NCPU - 1) / NCPU ))
  for s in $(seq 1 "$NCPU"); do
    $JASS --gen-data-wdl "$PER" "${OUTP}-$s.jnnw" 6 4 200 $((RANDOM)) "$@" >"${OUTP}-$s.log" 2>&1 &
  done; wait
  python3 - "$OUTP" "$NCPU" "$CUM" <<'PY'
import struct,glob,sys,re,os
outp,ncpu,cum=sys.argv[1],sys.argv[2],sys.argv[3]; REC=38
shards=sorted(glob.glob(outp+"-*.jnnw"),key=lambda p:int(re.search(r"-(\d+)\.jnnw$",p).group(1)))
body=b""; add=0
for s in shards:
    b=open(s,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; add+=n; body+=b[8:8+n*REC]
if os.path.exists(cum):
    raw=open(cum,'rb').read(); old=struct.unpack('<I',raw[4:8])[0]
    o=open(cum,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+add)); o.close(); tot=old+add
else:
    o=open(cum,'wb'); o.write(b'JNNW'); o.write(struct.pack('<I',add)); o.write(body); o.close(); tot=add
print("appended",add,"cumulative",tot)
PY
  rm -f "${OUTP}-"*.jnnw
}

CUM="$ART/cumulative.jnnw"
# --- gen0 : seed matériel (200k embarqué) → 1er apport au corpus cumulé ---
echo "=== gen0 : seed matériel (200k self-play embarqué, l2=3e-2) ==="
gen_and_append 200000 "$ART/sp0" "$CUM"        # pas de --nnue = réseau embarqué
$JASS --dump-eval-features "$CUM" "$ART/feat0" 2>&1 | tail -1
fit_wdl "$CUM" "$ART/feat0" "$ART/gen0" 3e-2
[ -f "$ART/gen0.pjtw" ] || { echo ABORT seed; exit 7; }
echo "  gen0 proxy = $(proxy "$ART/gen0")  [$(coverage "$CUM")]"

# --- boucle CUMULÉE 1M/gen : chaque gen ajoute 1M au corpus, puis re-fit sur TOUT ---
PREV="$ART/gen0"
for g in 1 2 3 4 5; do
  echo "=== gen$g : +1M self-play @depth4 avec gen$((g-1)) → corpus cumulé → logistic ==="
  gen_and_append 1000000 "$ART/sp$g" "$CUM" --nnue "$PREV.pjtw"
  $JASS --dump-eval-features "$CUM" "$ART/feat$g" 2>&1 | tail -1
  fit_wdl "$CUM" "$ART/feat$g" "$ART/gen$g" 3e-4
  [ -f "$ART/gen$g.pjtw" ] || { echo "ABORT gen$g"; exit 7; }
  echo "  gen$g proxy = $(proxy "$ART/gen$g")  [$(coverage "$CUM")]"
  PREV="$ART/gen$g"
done

echo; echo "=========================================================="
echo "   cpx62-0211 — BOUCLE WDL à CORPUS CUMULÉ (1M/gen) — VERDICT"
echo "  COURBE proxy (Spearman vs Scan-d10, set fixe 50k) :"
for g in 0 1 2 3 4 5; do echo "    gen$g = $(proxy "$ART/gen$g")"; done
echo "  RAPPEL : 0205b (300k FRAIS/gen, mt30) = PLAT ~0.41 ; eval compétent ~0.64-0.67."
echo "  → proxy MONTE en cumulant = FAMINE confirmée + l'ACCUMULATION/VOLUME est le fix."
echo "  → proxy plat malgré 5M cumulés = la famine n'est pas le mur → Nœud 2ter·B3/B4."
echo "=========================================================="
