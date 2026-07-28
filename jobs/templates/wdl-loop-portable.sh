#!/usr/bin/env bash
# id: __ID__
# description: Boucle WDL ITÉRÉE, AUTO-CONTENUE (seed généré sur place → portable
# sur n'importe quel box, y compris CPX62 vierge), mesurée au PROXY déterministe.
# Profondeur de jeu = __MT__ ms. Question : la courbe proxy monte-t-elle quand on
# joue plus profond (vs mt30 plat de 0205b) ?
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/__ID__/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
REF=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw   # committé → présent partout
[ -f "$REF" ] || { echo "ABORT: master de référence (committé) introuvable"; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)  # optionnel

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
./build-prod/jass_tests >"$ART/tests.log" 2>&1 && echo "tests OK" || { echo TESTS FAIL; exit 6; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

proxy(){ python3 tools/eval_proxy.py --jass "$JASS" --eval "$1.pjtw" --testset "$REF" \
           --offset 1300000 --max 50000 --score-drop 4900 2>/dev/null | grep -oE 'spearman=[-0-9.]+' | head -1 | cut -d= -f2; }
rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }
fit_wdl(){ python3 pattern_jass/tools/train.py --data "$1" --scan-eval --eval-features-file "$2" \
            --loss logistic --l2 "$4" --max-iter 200 --scale 1000 --out "$3.pjtw" >"$3-train.log" 2>&1; }
shard_selfplay(){ # <N> <out-prefix> <gen-flag...>  → merged $2.jnnw
  local NN=$1; local OUT=$2; shift 2; local PER=$(( (NN + NCPU - 1) / NCPU ))
  for s in $(seq 1 "$NCPU"); do
    $JASS --gen-data-wdl "$PER" "${OUT}-$s.jnnw" 4 64 200 $((RANDOM)) "$@" --movetime __MT__ >"${OUT}-$s.log" 2>&1 &
  done; wait
  python3 - "$OUT" <<'PY'
import struct,glob,sys,re,os
out=sys.argv[1]; REC=38
shards=sorted(glob.glob(out+"-*.jnnw"),key=lambda p:int(re.search(r"-(\d+)\.jnnw$",p).group(1)))
tot=0; o=open(out+".jnnw",'wb'); o.write(b'JNNW'); o.write(struct.pack('<I',0))
for s in shards:
    b=open(s,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; tot+=n; o.write(b[8:8+n*REC])
o.seek(4); o.write(struct.pack('<I',tot)); o.close(); print("merged",tot)
PY
  # Canari WDL (propagation 2026-07-28) — cf jobs/tools/assert_corpus_wdl.py.
  # Porte sur le corpus FUSIONNÉ que cette fonction vient d'écrire.
  python3 jobs/tools/assert_corpus_wdl.py --data "$OUT.jnnw" ||
    { echo "ABORT: corpus WDL aberrant dans $OUT.jnnw"; return 6; }
  rm -f "${OUT}-"*.jnnw
}

# --- gen0 : SEED auto-contenu (self-play du réseau EMBARQUÉ → logistic très régularisé ≈ matériel) ---
echo "=== gen0 : seed auto-contenu (80k self-play réseau embarqué, l2=3e-2) ==="
shard_selfplay 80000 "$ART/seed"          # pas de --nnue = réseau embarqué
$JASS --dump-eval-features "$ART/seed.jnnw" "$ART/seedfeat" 2>&1 | tail -1
fit_wdl "$ART/seed.jnnw" "$ART/seedfeat" "$ART/gen0" 3e-2
[ -f "$ART/gen0.pjtw" ] || { echo ABORT seed; exit 7; }
echo "  gen0 proxy = $(proxy "$ART/gen0")"

# --- boucle ---
PREV="$ART/gen0"
for g in 1 2 3 4 5; do
  echo "=== gen$g : self-play 300k @mt__MT__ avec gen$((g-1)) → WDL → logistic ==="
  shard_selfplay 300000 "$ART/sp$g" --nnue "$PREV.pjtw"
  $JASS --dump-eval-features "$ART/sp$g.jnnw" "$ART/feat$g" 2>&1 | tail -1
  fit_wdl "$ART/sp$g.jnnw" "$ART/feat$g" "$ART/gen$g" 3e-4
  [ -f "$ART/gen$g.pjtw" ] || { echo "ABORT gen$g"; exit 7; }
  echo "  gen$g proxy = $(proxy "$ART/gen$g")"
  PREV="$ART/gen$g"
done
[ -n "$V15" ] && ./build-prod/jass --benchmark-scan-eval "$ART/gen5.pjtw" "$V15" 9 18 1 0 "" 64 >"$ART/gen5-v15d9.log" 2>&1 || true

echo; echo "=========================================================="
echo "   __ID__ — BOUCLE WDL @mt__MT__ PROXY-MESURÉE — VERDICT"
echo "  COURBE proxy (Spearman vs Scan-d10, set fixe 50k) :"
for g in 0 1 2 3 4 5; do echo "    gen$g = $(proxy "$ART/gen$g")"; done
echo "  gen5 v15 d9 = $(rate "$ART/gen5-v15d9.log" 2>/dev/null)"
echo "  RAPPEL : mt30 (0205b) = PLAT ~0.41 ; eval compétent ~0.64-0.67"
echo "  → proxy MONTE au-dessus de 0.41 = la PROFONDEUR débloque → continuer/scaler."
echo "  → proxy plat ~0.41 = même profond, ça n'apprend pas → features/classe (pivot Nœud 3)."
echo "=========================================================="
