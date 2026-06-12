#!/usr/bin/env bash
# id: 0205-wdl-loop-clean-bigbench
# description: NŒUD 1 (re-test PROPRE). 0203 semblait monter (0→0.167→0.25 vs
# v15) mais 0204 est retombé à ~0.06 — confondu par (a) un replay buffer que
# j'avais ajouté (ancre l'eval vers les gens passées en régime montant) et (b)
# des benches de 18 parties (bruit ±0.08, on lit du bruit). On rejoue la boucle
# PROPREMENT pour trancher Nœud 1 :
#   - SANS replay buffer (recette exacte 0203 : chaque gen entraînée sur SES
#     propres parties fraîches uniquement),
#   - benches ÉLARGIS (~54 parties vs v15 au lieu de 18) pour résoudre le signal,
#   - 5 générations de plus depuis gen3 de 0203, mt30 (cheap).
#
#   COURBE gen4→gen8 monte proprement (≥0.25 et ↑, hors bruit) = la boucle
#     COMPOUNDE pour de vrai → Nœud 2 (recuit de profondeur).
#   COURBE plate dans le bruit (~0.1, ±0.07 à 54 parties) = la boucle ne grimpe
#     pas à mt30 → soit profondeur (1bis), soit features (Nœud 3).
#
# expected_duration: ~6.5 h (5 gens × self-play 300k @mt30 + benches 54 parties).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/0205-wdl-loop-clean-bigbench/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
GEN3=/root/jass/jobs/results/0203-scan-recipe-iterated-wdl/artefacts.src/gen3.pjtw
[ -f "$GEN3" ] || { echo "ABORT: gen3.pjtw de 0203 introuvable"; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
SCAN_DIR=/root/jass/.scan; SCAN="$SCAN_DIR/scan_linux"
[ -x "$SCAN" ] || { git clone --depth 1 https://github.com/rhalbersma/scan "$SCAN_DIR" 2>/dev/null && chmod +x "$SCAN_DIR/scan_linux"; SCAN="$SCAN_DIR/scan_linux"; }

rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }
jrate(){ grep -oE 'Jass score rate:\s*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+'|head -1; }
# bench ÉLARGI : 18 pairs → ~54 parties (résout les taux faibles)
v15big(){ ./build-prod/jass --benchmark-scan-eval "$1.pjtw" "$V15" 9 18 1 0 "" 64 >"$1-v15d9.log" 2>&1; }

N=300000; SH=$NCPU; PER=$(( (N + SH - 1) / SH )); MT=30
echo "=== gen3 (0203, référence) re-benché à 54 parties ==="
cp "$GEN3" "$ART/gen3.pjtw"; v15big "$ART/gen3"; echo "  gen3 = $(rate "$ART/gen3-v15d9.log") (54 parties)"

PREV="$ART/gen3.pjtw"
for g in 4 5 6 7 8; do
  echo "=== gen$g : self-play ${N}@mt${MT} avec gen$((g-1)) → WDL → logistic (SANS buffer) ==="
  for s in $(seq 1 "$SH"); do
    $JASS --gen-data-wdl "$PER" "$ART/sp$g-$s.jnnw" 4 64 200 $((g*100+s)) --nnue "$PREV" --movetime $MT >"$ART/sp$g-$s.log" 2>&1 &
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
  python3 pattern_jass/tools/train.py --data "$ART/sp$g.jnnw" --scan-eval --eval-features-file "$ART/feat$g" \
    --loss logistic --l2 3e-4 --max-iter 200 --scale 1000 --out "$ART/gen$g.pjtw" >"$ART/gen$g-train.log" 2>&1
  [ -f "$ART/gen$g.pjtw" ] || { echo "ABORT gen$g train"; tail -10 "$ART/gen$g-train.log"; exit 7; }
  v15big "$ART/gen$g"
  echo "  gen$g vs v15 d9 = $(rate "$ART/gen$g-v15d9.log") (54 parties)"
  rm -f "$ART/sp$g-"*.jnnw
  PREV="$ART/gen$g.pjtw"
done

# gen8 vs Scan d9 (36 parties)
[ -x "$SCAN" ] && python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN" \
  --jass-pattern "$ART/gen8.pjtw" --depth 9 --pairs 12 --jass-threads 1 >"$ART/gen8-scand9.log" 2>&1 || true

echo; echo "=========================================================="
echo "   0205 BOUCLE WDL PROPRE (sans buffer, benches 54 parties) — VERDICT"
echo "  COURBE vs v15 d9 (54 parties, bruit ±0.07) :"
echo "    gen3 (réf) = $(rate "$ART/gen3-v15d9.log")"
for g in 4 5 6 7 8; do echo "    gen$g       = $(rate "$ART/gen$g-v15d9.log")"; done
echo "    gen8 vs Scan d9 (36 parties) = $(jrate "$ART/gen8-scand9.log" 2>/dev/null)"
echo "  → monte proprement (↑, hors bruit) = boucle COMPOUNDE → Nœud 2 (profondeur)."
echo "  → plate dans le bruit = ne grimpe pas à mt30 → profondeur (1bis) ou features (Nœud 3)."
echo "=========================================================="
