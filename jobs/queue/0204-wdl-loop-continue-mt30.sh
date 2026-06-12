#!/usr/bin/env bash
# id: 0204-wdl-loop-continue-mt30
# description: NŒUD 2 (sous-étape) — la boucle WDL COMPOUNDE (0203 : 0→0.167→
# 0.25 vs v15, teacher-free). On continue la boucle pour trouver le PLATEAU à
# mt30 (incrément décélérait : +0.167 puis +0.083). On ajoute le **replay
# buffer** (méthodo : train chaque gen sur les 2 dernières gens cumulées →
# +volume effectif + stabilité, sans générer plus). Départ = gen3 de 0203.
#
#   gen4..7 : self-play 300k @ mt30 avec gen{g-1} → WDL → logistic l2=3e-4 sur
#   concat(sp{g-1}, sp{g}) → gen{g} ; bench vs v15 d9. gen7 aussi vs Scan d9.
#
#   COURBE gen3(0.25)→gen7 continue à monter = pas encore le plateau → encore
#     des gens, puis MONTER la profondeur (mt60+) pour relever le point fixe.
#   PLATEAU net = point fixe mt30 atteint → prochain job = recuit de profondeur.
#
# expected_duration: ~5.5 h (4 gens × self-play 300k @mt30 + train/bench).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/0204-wdl-loop-continue-mt30/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
PREV0=/root/jass/jobs/results/0203-scan-recipe-iterated-wdl/artefacts.src/gen3.pjtw
PREVSP0=/root/jass/jobs/results/0203-scan-recipe-iterated-wdl/artefacts.src/sp3.jnnw
[ -f "$PREV0" ] && [ -f "$PREVSP0" ] || { echo "ABORT: gen3.pjtw/sp3.jnnw de 0203 introuvables"; exit 3; }
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
v15d9(){ ./build-prod/jass --benchmark-scan-eval "$1.pjtw" "$V15" 9 6 1 0 "" 64 >"$1-v15d9.log" 2>&1; }
concat(){ python3 - "$3" "$1" "$2" <<'PY'
import struct,sys; out=sys.argv[1]; REC=38; tot=0
o=open(out,'wb'); o.write(b'JNNW'); o.write(struct.pack('<I',0))
for f in sys.argv[2:]:
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; tot+=n; o.write(b[8:8+n*REC])
o.seek(4); o.write(struct.pack('<I',tot)); o.close(); print("buffer",tot)
PY
}

N=300000; SH=$NCPU; PER=$(( (N + SH - 1) / SH )); MT=30
PREV="$PREV0"; PREVSP="$PREVSP0"
echo "=== continuation boucle WDL (replay buffer = 2 dernières gens) depuis gen3 (0.25) ==="
for g in 4 5 6 7; do
  echo "=== gen$g : self-play ${N}@mt${MT} avec gen$((g-1)) → WDL → logistic (buffer) ==="
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
  # replay buffer : gen précédente + gen courante
  concat "$PREVSP" "$ART/sp$g.jnnw" "$ART/buf$g.jnnw"
  $JASS --dump-eval-features "$ART/buf$g.jnnw" "$ART/feat$g" 2>&1 | tail -1
  python3 pattern_jass/tools/train.py --data "$ART/buf$g.jnnw" --scan-eval --eval-features-file "$ART/feat$g" \
    --loss logistic --l2 3e-4 --max-iter 200 --scale 1000 --out "$ART/gen$g.pjtw" >"$ART/gen$g-train.log" 2>&1
  [ -f "$ART/gen$g.pjtw" ] || { echo "ABORT gen$g train"; tail -10 "$ART/gen$g-train.log"; exit 7; }
  v15d9 "$ART/gen$g"
  echo "  gen$g vs v15 d9 = $(rate "$ART/gen$g-v15d9.log")"
  rm -f "$ART/sp$g-"*.jnnw "$ART/buf$((g-1)).jnnw"
  PREV="$ART/gen$g.pjtw"; PREVSP="$ART/sp$g.jnnw"
done

[ -x "$SCAN" ] && python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN" \
  --jass-pattern "$ART/gen7.pjtw" --depth 9 --pairs 8 --jass-threads 1 >"$ART/gen7-scand9.log" 2>&1 || true

echo; echo "=========================================================="
echo "   0204 CONTINUATION BOUCLE WDL mt30 (replay buffer) — VERDICT"
echo "  COURBE vs v15 d9 (rappel gen3=0.25 de 0203) :"
for g in 4 5 6 7; do echo "    gen$g = $(rate "$ART/gen$g-v15d9.log")"; done
echo "    gen7 vs Scan d9 = $(jrate "$ART/gen7-scand9.log" 2>/dev/null)"
echo "  → continue à monter = pas le plateau mt30 → encore des gens puis RECUIT DE PROFONDEUR."
echo "  → plateau net = point fixe mt30 atteint → prochain job = monter la profondeur de jeu."
echo "=========================================================="
