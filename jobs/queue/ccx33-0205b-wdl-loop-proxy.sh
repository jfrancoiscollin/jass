#!/usr/bin/env bash
# id: ccx33-0205b-wdl-loop-proxy
# description: NUIT (CCX33) — boucle WDL ITÉRÉE propre (mt30, SANS replay buffer),
# mesurée au PROXY DÉTERMINISTE (eval_proxy : accord Spearman avec Scan-d10 sur
# set fixe) en plus du bench v15 final. Remplace 0205 (tué par la course) avec
# la bonne mesure. Question Nœud 1 : la courbe proxy gen0→gen6 MONTE-t-elle ?
# (Le proxy n'a pas le bruit binomial des parties → on lit enfin le signal.)
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0205b-wdl-loop-proxy/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
SPALL=/root/jass/jobs/results/0196-selfplay-wdl-1M/artefacts.src/sp-all.jnnw
SPFEAT=/root/jass/jobs/results/0196-selfplay-wdl-1M/artefacts.src/sp.feat
REF=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$SPALL" ] && [ -f "$SPFEAT" ] && [ -f "$REF" ] || { echo "ABORT: data 0196/0141 introuvable"; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
./build-prod/jass_tests >"$ART/tests.log" 2>&1 && echo "tests OK" || { echo TESTS FAIL; exit 6; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# PROXY déterministe : accord Spearman des scores eval vs Scan-d10 sur 50k positions tenues à l'écart
proxy(){ python3 tools/eval_proxy.py --jass "$JASS" --eval "$1.pjtw" --testset "$REF" \
           --offset 1300000 --max 50000 --score-drop 4900 2>/dev/null | grep -oE 'spearman=[-0-9.]+' | head -1 | cut -d= -f2; }
rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }
v15d9(){ [ -n "$V15" ] && ./build-prod/jass --benchmark-scan-eval "$1.pjtw" "$V15" 9 18 1 0 "" 64 >"$1-v15d9.log" 2>&1 || true; }
fit_wdl(){ python3 pattern_jass/tools/train.py --data "$1" --scan-eval --eval-features-file "$2" \
            --loss logistic --l2 "$4" --max-iter 200 --scale 1000 --out "$3.pjtw" >"$3-train.log" 2>&1; }

echo "=== gen0 : seed matériel (logistic l2=3e-2 sur sp-all) ==="
fit_wdl "$SPALL" "$SPFEAT" "$ART/gen0" 3e-2
[ -f "$ART/gen0.pjtw" ] || { echo ABORT seed; exit 7; }
echo "  gen0 proxy(spearman vs Scan-d10) = $(proxy "$ART/gen0")"

N=300000; SH=$NCPU; PER=$(( (N + SH - 1) / SH )); MT=30; PREV="$ART/gen0"
for g in 1 2 3 4 5 6; do
  echo "=== gen$g : self-play ${N}@mt${MT} avec gen$((g-1)) → WDL → logistic ==="
  for s in $(seq 1 "$SH"); do
    $JASS --gen-data-wdl "$PER" "$ART/sp$g-$s.jnnw" 4 64 200 $((g*100+s)) --nnue "$PREV.pjtw" --movetime $MT >"$ART/sp$g-$s.log" 2>&1 &
  done
  wait
  python3 - "$ART" "$g" <<'PY'
import struct,glob,os,sys,re
art=sys.argv[1]; g=sys.argv[2]; REC=38; outp=os.path.join(art,f"sp{g}.jnnw")
shards=sorted(glob.glob(os.path.join(art,f"sp{g}-*.jnnw")),key=lambda p:int(re.search(rf"sp{g}-(\d+)\.jnnw",p).group(1)))
tot=0; out=open(outp,'wb'); out.write(b'JNNW'); out.write(struct.pack('<I',0))
for s in shards:
    b=open(s,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; tot+=n; out.write(b[8:8+n*REC])
out.seek(4); out.write(struct.pack('<I',tot)); out.close(); print("gen",g,"merged",tot)
PY
  $JASS --dump-eval-features "$ART/sp$g.jnnw" "$ART/feat$g" 2>&1 | tail -1
  fit_wdl "$ART/sp$g.jnnw" "$ART/feat$g" "$ART/gen$g" 3e-4
  [ -f "$ART/gen$g.pjtw" ] || { echo "ABORT gen$g"; exit 7; }
  echo "  gen$g proxy = $(proxy "$ART/gen$g")"
  rm -f "$ART/sp$g-"*.jnnw
  PREV="$ART/gen$g"
done
v15d9 "$ART/gen6"

echo; echo "=========================================================="
echo "   ccx33-0205b BOUCLE WDL PROXY-MESURÉE — VERDICT"
echo "  COURBE proxy (Spearman des scores eval vs Scan-d10, set fixe 50k) :"
for g in 0 1 2 3 4 5 6; do echo "    gen$g = $(proxy "$ART/gen$g")"; done
echo "  gen6 v15 d9 (54 parties, continuité) = $(rate "$ART/gen6-v15d9.log")"
echo "  → proxy MONTE proprement gen0→gen6 = la boucle WDL COMPOUNDE (Nœud 1 = OUI)."
echo "  → proxy plat = ne grimpe pas à mt30 → profondeur (0206/0207) ou features."
echo "=========================================================="
