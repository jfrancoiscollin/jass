#!/usr/bin/env bash
# id: cpx62-0273-coverage-seeding
# description: DIRECTION A (couverture / famine). Diagnostic finale (acte 3) : le verrou n'est ni
# le bruit ni les labels → reste COUVERTURE ou représentation. Le self-play (0266, endgame-rois
# 3.22) couvre déjà mieux les finales que le master (distill 5.13) → on POUSSE la couverture :
# self-play = config championne 0266 (king-aware, play_depth=8 uniforme) MAIS avec SEEDING de
# finales (--seed-frac 50 : la moitié des parties DÉMARRENT d'une finale du master) → ×beaucoup
# de positions de finale, diverses. Binaire à jour (NMP-off + lmr_base=0 + history=16384).
# Test : l'autopsie endgame-rois passe-t-elle SOUS 3.22 (0266) ? → la couverture répare la finale.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0273-coverage-seeding/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
MASTER=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
[ -f "$MASTER" ] || { echo "ABORT: master introuvable"; exit 3; }

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "KING-AWARE patterns ENABLED" "$ART/cmake.log" || { echo "ABORT: pas king-aware"; exit 5; }
grep -q "eg_pieces  = 40" src/search_params.hpp && grep -q "lmr_base             = 0" src/search_params.hpp && echo "binaire = NMP-off + lmr0 + history16k" || echo "WARNING: défauts search inattendus"
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- extrait les seeds FINALES (popcount<=14) du master ---
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
open(dst,'wb').write(out); print(f"seeds finales : {len(idx)} (popcount<=14)")
PY

EVAL_DEPTH=6; PLAY_DEPTH=8; NPER=600000; NGEN=8; BD=9; EPAIRS=15
SEEDARGS=(--seed-file "$ART/seeds.jnnw" --seed-frac 50)   # moitié des parties depuis une finale
CFOLD="--full-fold --king-patterns"; declare -A ELO EGM
echo "PARAMS: play_depth=$PLAY_DEPTH + SEEDING finale 50% (couverture) ; $NPER/gen ×$NGEN"

fit_wdl(){ python3 pattern_jass/tools/train.py --data "$1" --scan-eval --eval-features-file "$2" --loss logistic --l2 "$4" --max-iter 200 --scale 1000 --prune $CFOLD --out "$3.pjtw" >"$3-train.log" 2>&1; }
val_endgame(){ grep -oE 'val/phase mse : .*' "$1-train.log" | grep -oE 'endgame=[0-9.]+' | head -1 | cut -d= -f2; }
elo_vs_hc(){ local lg="$ART/elo-$(basename "$1" .pjtw).log"; $JASS --benchmark-scan-eval "$1" hc "$BD" "$2" "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2); local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  echo "${W:-0}-${D:-0}-${L:-0} elo=$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2)"; }
gen_and_append(){ local NN=$1; local OUTP=$2; local CUM=$3; shift 3; local PER=$(( (NN + NCPU - 1) / NCPU ))
  for s in $(seq 1 "$NCPU"); do $JASS --gen-data-wdl "$PER" "${OUTP}-$s.jnnw" "$EVAL_DEPTH" "$PLAY_DEPTH" 200 $((RANDOM)) "$@" >"${OUTP}-$s.log" 2>&1 & done; wait
  python3 - "$OUTP" "$CUM" <<'PY'
import struct,glob,sys,re,os
outp,cum=sys.argv[1],sys.argv[2]; REC=38
shards=sorted(glob.glob(outp+"-*.jnnw"),key=lambda p:int(re.search(r"-(\d+)\.jnnw$",p).group(1)))
body=b""; add=0
for s in shards:
    b=open(s,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; add+=n; body+=b[8:8+n*REC]
if os.path.exists(cum):
    raw=open(cum,'rb').read(); old=struct.unpack('<I',raw[4:8])[0]
    o=open(cum,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+add)); o.close(); print("cumulative",old+add)
else:
    o=open(cum,'wb'); o.write(b'JNNW'); o.write(struct.pack('<I',add)); o.write(body); o.close(); print("cumulative",add)
PY
  rm -f "${OUTP}-"*.jnnw; }

CUM="$ART/cumulative.jnnw"
echo "=== gen0 : seed 300k (play depth-8 + seeding finale, l2=3e-2) ==="
gen_and_append 300000 "$ART/sp0" "$CUM" "${SEEDARGS[@]}"
$JASS --dump-eval-features "$CUM" "$ART/feat0" 2>&1 | tail -1
fit_wdl "$CUM" "$ART/feat0" "$ART/gen0" 3e-2
[ -f "$ART/gen0.pjtw" ] || { echo ABORT seed; tail -8 "$ART/gen0-train.log"; exit 7; }
EGM[0]=$(val_endgame "$ART/gen0"); ELO[0]=$(elo_vs_hc "$ART/gen0.pjtw" "$EPAIRS"); echo "  gen0 val_endgame=${EGM[0]} Elo=${ELO[0]}"
PREV="$ART/gen0"
for g in $(seq 1 "$NGEN"); do
  echo "=== gen$g : +${NPER} (play depth-8 + seeding finale) ==="
  gen_and_append "$NPER" "$ART/sp$g" "$CUM" --nnue "$PREV.pjtw" "${SEEDARGS[@]}"
  $JASS --dump-eval-features "$CUM" "$ART/feat$g" 2>&1 | tail -1
  fit_wdl "$CUM" "$ART/feat$g" "$ART/gen$g" 3e-4
  [ -f "$ART/gen$g.pjtw" ] || { echo "ABORT gen$g"; tail -8 "$ART/gen$g-train.log"; exit 7; }
  EGM[$g]=$(val_endgame "$ART/gen$g"); ELO[$g]=$(elo_vs_hc "$ART/gen$g.pjtw" "$EPAIRS"); echo "  gen$g val_endgame=${EGM[$g]} Elo=${ELO[$g]}"
  PREV="$ART/gen$g"
done
ELOF=$(elo_vs_hc "$ART/gen${NGEN}.pjtw" 60)

# verdict + autopsie
SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1 || echo "(clone Scan échoué)"; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
SCAN5=""
if [ -x "$SCAN_BIN" ]; then
  GAMES="$ART/games"; mkdir -p "$GAMES"
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/gen${NGEN}.pjtw" --scan-bb-size 0 --movetime 0.5 --pairs 2 --dump-games-dir "$GAMES" >"$ART/scan-mt05.log" 2>&1
  SCAN5=$(grep -E 'score rate|ELO estimate' "$ART/scan-mt05.log" | tr '\n' ' ')
  python3 tools/game_autopsy.py --games-dir "$GAMES" --jass /bin/true --scan "$SCAN_BIN" --scan-depth 11 --scan-bb-size 0 --worst 10 --out "$ART/autopsy.txt" 2>"$ART/autopsy.err" || echo "(autopsie skip)"
fi

echo; echo "=========================================================="
echo "   cpx62-0273 — DIRECTION A : COUVERTURE (seeding finale 50% + play depth-8)"
echo "----------------------------------------------------------"
for g in $(seq 0 "$NGEN"); do echo "  gen$g  Elo_vs_hc=${ELO[$g]}   val_endgame_mse=${EGM[$g]}"; done
echo "  gen${NGEN} (60p) vs hc : $ELOF   [0266 sans seeding = +201.7]"
[ -n "$SCAN5" ] && echo "  gen${NGEN} vs Scan mt0.5 : $SCAN5"
echo "  AUTOPSIE (endgame-rois ; comparer 0266=3.22) :"
sed -n '/PHASE × ROIS/,/par TACTIQUE/p' "$ART/autopsy.txt" 2>/dev/null | head -12
echo "----------------------------------------------------------"
echo "  endgame-rois < 3.22 → la COUVERTURE (seeding) répare la finale = Direction A gagnante → scaler."
echo "  endgame-rois ~3.22 → la couverture ne suffit pas → c'est la REPRÉSENTATION (features/bitbases)."
echo "=========================================================="
