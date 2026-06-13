#!/usr/bin/env bash
# id: cpx62-0209-volume-sweep
# description: DEBUG Nœud 2ter·B2 — FAMINE DE DONNÉES. Hypothèse : la boucle WDL est
# plate (0205b ~0.41) parce que la table de 17 006 112 buckets (32×3¹²) est ~97 %
# non-estimée à 300k positions/gen (mesuré local : 1 % de buckets touchés à 30k,
# 62 % des touchés ≤2 visites). Test à UN FACTEUR = VOLUME : on génère UN gros
# corpus self-play (gen0 matériel fixe), puis on entraîne gen1 sur des PRÉFIXES
# emboîtés {0.3M,1M,3M,6M} (même distribution, seul le volume change) et on lit le
# proxy. Si proxy(gen1) MONTE avec le volume → famine confirmée → le fix est le
# VOLUME/cumul (reste linéaire, reste Scan), PAS un pivot non-linéaire.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0209-volume-sweep/artefacts.src"; mkdir -p "$ART"
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

# slice the first K records of a JNNW file into a new JNNW
slice_jnnw(){ python3 - "$1" "$2" "$3" <<'PY'
import struct,sys
src,dst,k=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
b=open(src,'rb').read(); assert b[:4]==b'JNNW'; n=struct.unpack('<I',b[4:8])[0]
k=min(k,n); o=open(dst,'wb'); o.write(b'JNNW'); o.write(struct.pack('<I',k)); o.write(b[8:8+k*REC]); o.close()
print("sliced",k,"of",n)
PY
}
# self-play N positions, sharded, merged into $2.jnnw (extra args after $2 → gen flags)
shard_selfplay(){ local NN=$1; local OUT=$2; shift 2; local PER=$(( (NN + NCPU - 1) / NCPU ))
  for s in $(seq 1 "$NCPU"); do
    $JASS --gen-data-wdl "$PER" "${OUT}-$s.jnnw" 6 4 200 $((s*131+7)) "$@" >"${OUT}-$s.log" 2>&1 &
  done; wait
  python3 - "$OUT" "$NCPU" <<'PY'
import struct,glob,sys,re
out=sys.argv[1]; REC=38
shards=sorted(glob.glob(out+"-*.jnnw"),key=lambda p:int(re.search(r"-(\d+)\.jnnw$",p).group(1)))
tot=0; o=open(out+".jnnw",'wb'); o.write(b'JNNW'); o.write(struct.pack('<I',0))
for s in shards:
    b=open(s,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; tot+=n; o.write(b[8:8+n*REC])
o.seek(4); o.write(struct.pack('<I',tot)); o.close(); print("merged",tot)
PY
  rm -f "${OUT}-"*.jnnw
}

# --- gen0 : seed matériel auto-contenu (réseau embarqué, l2=3e-2) ---
echo "=== gen0 : seed matériel (80k self-play embarqué, l2=3e-2) ==="
shard_selfplay 80000 "$ART/seed"
$JASS --dump-eval-features "$ART/seed.jnnw" "$ART/seedfeat" 2>&1 | tail -1
fit_wdl "$ART/seed.jnnw" "$ART/seedfeat" "$ART/gen0" 3e-2
[ -f "$ART/gen0.pjtw" ] || { echo ABORT seed; exit 7; }
echo "  gen0 proxy = $(proxy "$ART/gen0")"

# --- gros corpus gen1 (joué par gen0, profondeur FIXE), généré UNE fois ---
TOTAL=6000000
echo "=== corpus gen1 : $TOTAL positions @ depth4 jouées par gen0 (généré une fois) ==="
shard_selfplay "$TOTAL" "$ART/corpus" --nnue "$ART/gen0.pjtw"
ACTUAL=$(python3 -c "import struct;print(struct.unpack('<I',open('$ART/corpus.jnnw','rb').read(8)[4:8])[0])")
echo "  corpus réel = $ACTUAL positions"

# --- sweep volume : préfixes emboîtés, fit + proxy après CHAQUE point (résultats partiels utiles) ---
declare -A PROX
for V in 300000 1000000 3000000 6000000; do
  [ "$V" -gt "$ACTUAL" ] && { echo "  (skip V=$V > corpus)"; continue; }
  echo "=== V=$V : slice → features → logistic(l2=3e-4) → proxy ==="
  slice_jnnw "$ART/corpus.jnnw" "$ART/sub-$V.jnnw" "$V"
  $JASS --dump-eval-features "$ART/sub-$V.jnnw" "$ART/feat-$V" 2>&1 | tail -1
  fit_wdl "$ART/sub-$V.jnnw" "$ART/feat-$V" "$ART/gen1-$V" 3e-4
  if [ -f "$ART/gen1-$V.pjtw" ]; then
    P=$(proxy "$ART/gen1-$V"); PROX[$V]=$P; echo "  V=$V proxy = $P"
    # coverage : buckets touchés sur ce volume (diagnostic direct de la famine)
    python3 - "$ART/sub-$V.jnnw" <<'PY'
import numpy as np,struct,sys
sys.path.insert(0,'pattern_jass/tools'); import patterns as P
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38
a=np.frombuffer(b[8:8+n*REC],dtype=np.uint8).reshape(n,REC)
bb=a[:,0:32].copy().view('<u8').reshape(n,4)
cols=P.flat_feature_columns(P.extract_indices(bb[:,2],bb[:,0])).ravel()
c=np.bincount(cols,minlength=P.TOTAL_BUCKETS); d=int((c>0).sum())
print(f"  coverage : {d} buckets touchés ({100*d/P.TOTAL_BUCKETS:.3f}%) ; ≤2 visites = {int((c[c>0]<=2).sum())} ({100*(c[c>0]<=2).mean():.0f}% des touchés)")
PY
  else echo "  V=$V TRAIN FAIL"; tail -5 "$ART/gen1-$V-train.log"; fi
  rm -f "$ART/sub-$V.jnnw"
done

echo; echo "=========================================================="
echo "   cpx62-0209 — SWEEP VOLUME (Nœud 2ter·B2) — VERDICT"
echo "  gen0 (matériel) proxy = $(proxy "$ART/gen0")"
echo "  COURBE proxy(gen1) vs VOLUME (set proxy fixe 50k) :"
for V in 300000 1000000 3000000 6000000; do echo "    V=$V → ${PROX[$V]:-NA}"; done
echo "  RAPPEL : 0205b (300k/gen, mt30) = PLAT ~0.41 ; eval compétent ~0.64-0.67."
echo "  → proxy MONTE avec le volume = FAMINE confirmée → fix = VOLUME/cumul (linéaire, Scan)."
echo "  → proxy plat malgré le volume = la famine n'est pas le mur → Nœud 2ter·B3/B4."
echo "=========================================================="
