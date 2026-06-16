#!/usr/bin/env bash
# id: cpx62-0274-coverage-augment
# description: DIRECTION A v2 (couverture, FIX du depth). Test rapide : AUGMENTER les données
# globales du champion 0266 (5.1M, play depth-8) avec ~1M de FINALES seedées jouées à DEPTH-16
# (labels CORRECTS — c'est tout le point : les seeds sont 100% finale ≤14 pièces, donc depth-16
# est CHEAP + COHÉRENT, pas l'incohérence intra-partie qui a tué 0263). Puis ré-entraîner
# king-aware sur le mélange et AUTOPSIER la finale. Si endgame-rois < 3.22 (0266) → la couverture
# avec BONS labels répare la finale → Direction A gagnante (on fera le vrai loop deux-passes).
# Sinon → c'est la REPRÉSENTATION (features/bitbases), pas la couverture.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0274-coverage-augment/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
MASTER=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
SRC=/root/jass/jobs/results/cpx62-0266-kingloop-deepplay/artefacts.src
GLOBAL="$SRC/cumulative.jnnw"; CHAMP="$SRC/gen8.pjtw"
[ -f "$MASTER" ] || { echo "ABORT: master introuvable"; exit 3; }
[ -f "$GLOBAL" ] || { echo "ABORT: cumulative 0266 introuvable (box recyclée ?)"; exit 3; }
[ -f "$CHAMP" ]  || { echo "ABORT: champion 0266 gen8 introuvable"; exit 3; }
echo "global 0266 = $(python3 -c "import struct;print(struct.unpack('<I',open('$GLOBAL','rb').read(8)[4:8])[0])") positions"

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "KING-AWARE patterns ENABLED" "$ART/cmake.log" || { echo "ABORT: pas king-aware"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- seeds finales (popcount<=14) du master ---
echo "=== extrait seeds finales (popcount<=14) ==="
python3 - "$MASTER" "$ART/seeds.jnnw" <<'PY'
import sys, struct
import numpy as np
sys.path.insert(0,'pattern_jass/tools'); import master_loader
src,dst=sys.argv[1],sys.argv[2]; ds=master_loader.load(src); REC=38
def pc(a): return np.unpackbits(a.view(np.uint8)).reshape(len(a),64).sum(axis=1)
pieces=pc(ds.white_men)+pc(ds.white_kings)+pc(ds.black_men)+pc(ds.black_kings)
idx=np.flatnonzero(pieces<=14)
raw=open(src,'rb').read(); body=raw[8:]; mv=memoryview(body)
out=bytearray(b'JNNW'); out+=struct.pack('<I',len(idx))
for i in idx: out+=mv[i*REC:(i+1)*REC]
open(dst,'wb').write(out); print(f"seeds finales : {len(idx)}")
PY

# --- génère ~1M de FINALES jouées à DEPTH-16 (champion 0266 ; seed-frac=100) ---
NEG=1000000; PER=$(( (NEG + NCPU - 1) / NCPU ))
echo "=== génère ~${NEG} finales (play_depth=16, seed 100%, champion 0266) ==="
for s in $(seq 1 "$NCPU"); do
  $JASS --gen-data-wdl "$PER" "$ART/eg-$s.jnnw" 6 16 200 $((RANDOM)) --nnue "$CHAMP" \
      --seed-file "$ART/seeds.jnnw" --seed-frac 100 >"$ART/eg-$s.log" 2>&1 &
done; wait

# --- merge global(0266) + finales depth-16 → cumulatif augmenté ---
echo "=== merge global + finales-depth16 ==="
python3 - "$GLOBAL" "$ART" "$ART/merged.jnnw" <<'PY'
import struct, glob, sys, re, shutil
glob_path, art, dst = sys.argv[1], sys.argv[2], sys.argv[3]
REC=38
shutil.copyfile(glob_path, dst)
shards=sorted(glob.glob(art+"/eg-*.jnnw"), key=lambda p:int(re.search(r"eg-(\d+)\.jnnw$",p).group(1)))
body=b""; add=0
for s in shards:
    b=open(s,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; add+=n; body+=b[8:8+n*REC]
raw=open(dst,'rb').read(); old=struct.unpack('<I',raw[4:8])[0]
o=open(dst,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+add)); o.close()
print(f"merged: {old} global + {add} finales-d16 = {old+add}")
PY
rm -f "$ART"/eg-*.jnnw

# --- train king-aware lowmem sur le mélange ---
echo "=== dump features + train king-aware (lowmem) ==="
$JASS --dump-eval-features "$ART/merged.jnnw" "$ART/featM" 2>&1 | tail -1
python3 pattern_jass/tools/train.py --data "$ART/merged.jnnw" --scan-eval --king-patterns \
    --eval-features-file "$ART/featM" --loss logistic --l2 3e-4 --max-iter 200 --scale 1000 \
    --prune --lowmem --full-fold --out "$ART/aug.pjtw" >"$ART/train.log" 2>&1
[ -f "$ART/aug.pjtw" ] || { echo "ABORT train"; tail -8 "$ART/train.log"; exit 7; }
EG=$(grep -oE 'val/phase mse : .*' "$ART/train.log" | grep -oE 'endgame=[0-9.]+' | head -1 | cut -d= -f2)
ELO=$($JASS --benchmark-scan-eval "$ART/aug.pjtw" hc 9 60 "$NCPU" 0 2>/dev/null | { W=""; while read -r l; do case "$l" in *SCAN_EVAL=*) W=$(echo "$l"|grep -oE 'SCAN_EVAL=[0-9]+'|cut -d= -f2); L=$(echo "$l"|grep -oE 'NNUE=[0-9]+'|cut -d= -f2); D=$(echo "$l"|grep -oE 'Draws=[0-9]+'|cut -d= -f2);; esac; done; echo "${W:-0}-${D:-0}-${L:-0}"; })
ELOV=$(python3 tools/sprt_elo.py --wdl $(echo "$ELO"|tr '-' ' ') 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2)

# --- autopsie finale vs Scan ---
SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1 || echo "(clone échoué)"; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
SCAN5=""
if [ -x "$SCAN_BIN" ]; then
  GAMES="$ART/games"; mkdir -p "$GAMES"
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/aug.pjtw" --scan-bb-size 0 --movetime 0.5 --pairs 2 --dump-games-dir "$GAMES" >"$ART/scan-mt05.log" 2>&1
  SCAN5=$(grep -E 'score rate|ELO estimate' "$ART/scan-mt05.log" | tr '\n' ' ')
  python3 tools/game_autopsy.py --games-dir "$GAMES" --jass /bin/true --scan "$SCAN_BIN" --scan-depth 11 --scan-bb-size 0 --worst 10 --out "$ART/autopsy.txt" 2>"$ART/autopsy.err" || echo "(autopsie skip)"
fi

echo; echo "=========================================================="
echo "   cpx62-0274 — DIRECTION A v2 : 0266-global + ~1M FINALES depth-16 (labels corrects)"
echo "----------------------------------------------------------"
echo "  éval augmentée : Elo_vs_hc(60p)=$ELO elo=$ELOV   val_endgame_mse=$EG   [0266 = +201.7]"
[ -n "$SCAN5" ] && echo "  vs Scan mt0.5 : $SCAN5"
echo "  AUTOPSIE (endgame-rois ; comparer 0266=3.22) :"
sed -n '/PHASE × ROIS/,/par TACTIQUE/p' "$ART/autopsy.txt" 2>/dev/null | head -12
echo "----------------------------------------------------------"
echo "  endgame-rois < 3.22 → couverture+labels-corrects RÉPARE la finale → vrai loop deux-passes."
echo "  endgame-rois ~3.22 → ni couverture ni labels → REPRÉSENTATION (features de finale / bitbases)."
echo "=========================================================="
