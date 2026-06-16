#!/usr/bin/env bash
# id: ccx33-0276-selfplay-features
# description: DIRECTION B → PRODUCTION. 0275 (distillation) a prouvé que les 4 features de finale
# (centralité + proximité roi) font CHUTER la perte endgame-rois 5.13 (0272 sans) → 3.22 (avec) :
# la REPRÉSENTATION était le verrou (le PST par-case était aveugle à l'activité du roi). On valide
# maintenant dans la BOUCLE DE SELF-PLAY (= production, pas distillation) : réplique EXACTE du
# champion 0266 (king-aware, NMP-off, play depth-8 UNIFORME, EVAL_DEPTH=6, NPER=600k ×8 gen, même
# schedule l2) mais binaire build AVEC -DJASS_ENDGAME_FEATURES (NUM_EXTRAS 106→110). Seule variable
# changée = les features. --lowmem pour tenir sur 16GB (full-batch L-BFGS identique, pure-L2). On
# compare gen-par-gen à 0266 (Elo_vs_hc) ET l'autopsie finale-rois vs Scan à 0266 (~3.x) / 0275
# distill (3.22). Si Elo ≥ 0266 ET endgame-rois < 0266 → on intègre les features en DÉFAUT
# (gated→on) ; c'est le 1er vrai mouvement sur le verrou finale.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0276-selfplay-features/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON -DJASS_ENDGAME_FEATURES=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "KING-AWARE patterns ENABLED" "$ART/cmake.log" || { echo "ABORT: pas king-aware"; exit 5; }
grep -q "ENDGAME FEATURES ENABLED" "$ART/cmake.log" || { echo "ABORT: features pas activées"; exit 5; }
grep -q "eg_pieces  = 40" src/search_params.hpp && echo "binaire = NMP OFF" || echo "WARNING: NMP pas off"
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

EVAL_DEPTH=6; PLAY_DEPTH=8; NPER=600000; NGEN=8; BD=9; EPAIRS=15   # play UNIFORME depth-8, = 0266
CFOLD="--full-fold --king-patterns"
declare -A ELO EGM
echo "PARAMS: play_depth=$PLAY_DEPTH UNIFORME (= 0266) + ENDGAME FEATURES (110) + --lowmem  $NPER/gen ×$NGEN"

fit_wdl(){ python3 pattern_jass/tools/train.py --data "$1" --scan-eval --eval-features-file "$2" \
            --loss logistic --l2 "$4" --max-iter 200 --scale 1000 --prune --lowmem $CFOLD --out "$3.pjtw" >"$3-train.log" 2>&1; }
val_endgame(){ grep -oE 'val/phase mse : .*' "$1-train.log" | grep -oE 'endgame=[0-9.]+' | head -1 | cut -d= -f2; }
elo_vs_hc(){ local lg="$ART/elo-$(basename "$1" .pjtw).log"
  $JASS --benchmark-scan-eval "$1" hc "$BD" "$2" "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  echo "${W:-0}-${D:-0}-${L:-0} elo=$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2)"
}
gen_and_append(){ local NN=$1; local OUTP=$2; local CUM=$3; shift 3; local PER=$(( (NN + NCPU - 1) / NCPU ))
  for s in $(seq 1 "$NCPU"); do
    $JASS --gen-data-wdl "$PER" "${OUTP}-$s.jnnw" "$EVAL_DEPTH" "$PLAY_DEPTH" 200 $((RANDOM)) "$@" >"${OUTP}-$s.log" 2>&1 &
  done; wait
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
  rm -f "${OUTP}-"*.jnnw
}

CUM="$ART/cumulative.jnnw"
echo "=== gen0 : seed (300k, play depth-8, l2=3e-2) ==="
gen_and_append 300000 "$ART/sp0" "$CUM"
$JASS --dump-eval-features "$CUM" "$ART/feat0" 2>&1 | tail -1
fit_wdl "$CUM" "$ART/feat0" "$ART/gen0" 3e-2
[ -f "$ART/gen0.pjtw" ] || { echo ABORT seed; tail -8 "$ART/gen0-train.log"; exit 7; }
grep -q "adapting to the dump width" "$ART/gen0-train.log" && echo "trainer a adapté à 110 features"
EGM[0]=$(val_endgame "$ART/gen0"); ELO[0]=$(elo_vs_hc "$ART/gen0.pjtw" "$EPAIRS"); echo "  gen0 val_endgame=${EGM[0]} Elo=${ELO[0]}"
case "${ELO[0]}" in 0-0-0*) echo "ABORT desync"; exit 8;; esac

PREV="$ART/gen0"
for g in $(seq 1 "$NGEN"); do
  echo "=== gen$g : +${NPER} (play depth-8) avec gen$((g-1)) → cumulé → logistic (features+lowmem) ==="
  gen_and_append "$NPER" "$ART/sp$g" "$CUM" --nnue "$PREV.pjtw"
  $JASS --dump-eval-features "$CUM" "$ART/feat$g" 2>&1 | tail -1
  fit_wdl "$CUM" "$ART/feat$g" "$ART/gen$g" 3e-4
  [ -f "$ART/gen$g.pjtw" ] || { echo "ABORT gen$g"; tail -8 "$ART/gen$g-train.log"; exit 7; }
  EGM[$g]=$(val_endgame "$ART/gen$g"); ELO[$g]=$(elo_vs_hc "$ART/gen$g.pjtw" "$EPAIRS"); echo "  gen$g val_endgame=${EGM[$g]} Elo=${ELO[$g]}"
  PREV="$ART/gen$g"
done
echo "=== gen${NGEN} vs hc précis (60p) ==="; ELOF=$(elo_vs_hc "$ART/gen${NGEN}.pjtw" 60); echo "  $ELOF"

# --- verdict + AUTOPSIE FINALE vs Scan ---
SCAN_BIN=/root/jass-scan/scan_linux
if [ ! -x "$SCAN_BIN" ]; then rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1 || echo "(clone Scan échoué)"; chmod +x "$SCAN_BIN" 2>/dev/null || true; fi
SCAN5=""; AUTOP=""
if [ -x "$SCAN_BIN" ]; then
  GAMES="$ART/games"; mkdir -p "$GAMES"
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/gen${NGEN}.pjtw" \
      --scan-bb-size 0 --movetime 0.5 --pairs 2 --dump-games-dir "$GAMES" >"$ART/scan-mt05.log" 2>&1
  SCAN5=$(grep -E 'score rate|ELO estimate' "$ART/scan-mt05.log" | tr '\n' ' ')
  python3 tools/game_autopsy.py --games-dir "$GAMES" --jass /bin/true --scan "$SCAN_BIN" \
      --scan-depth 11 --scan-bb-size 0 --worst 10 --out "$ART/autopsy.txt" 2>"$ART/autopsy.err" || echo "(autopsie skip)"
  AUTOP=$(sed -n '/PHASE × ROIS/,/par TACTIQUE/p' "$ART/autopsy.txt" 2>/dev/null | head -12)
fi

echo; echo "=========================================================="
echo "   ccx33-0276 — DIRECTION B PRODUCTION : self-play AVEC features de finale (king-aware, NMP-off, depth-8)"
echo "----------------------------------------------------------"
for g in $(seq 0 "$NGEN"); do echo "  gen$g  Elo_vs_hc=${ELO[$g]}   val_endgame_mse=${EGM[$g]}"; done
echo "  gen${NGEN} (60p) vs hc : $ELOF   [0266 SANS features même setup = +201.7]"
[ -n "$SCAN5" ] && echo "  gen${NGEN} vs Scan mt0.5 : $SCAN5"
echo "----------------------------------------------------------"
echo "  AUTOPSIE FINALE (perte par phase × rois vs Scan ; comparer 0266 SANS features ~3.x, 0275 distill+features=3.22) :"
echo "$AUTOP"
echo "----------------------------------------------------------"
echo "  Elo ≥ +201.7 ET endgame-rois < 0266 → les features densifient AUSSI en self-play (production)"
echo "     → INTÉGRER en défaut (JASS_ENDGAME_FEATURES gated→ON) + re-baseline vs Scan."
echo "  Elo ~0266 mais endgame-rois PAS meilleur → l'effet distill (3.22) ne transfère pas au self-play"
echo "     → le verrou self-play reste la COUVERTURE (cf 0274) plus que la représentation."
echo "=========================================================="
