#!/usr/bin/env bash
# id: ccx33-0297-saturate-loop
# description: SATURER LA CLASSE LINÉAIRE sur la finale (stratégie Scan). 0287/0293 : la classe n'est
# PAS saturée, les leviers DONNÉES marchent encore. Boucle self-play combinant les briques VALIDÉES :
# (a) king-aware + ENDGAME-FEATURES (110), (b) egdb-perfect (finales ≤7 jouées par la TB → labels WDL
# exacts), (c) DEPTH-RAMP late-mid=12/endgame=16 (0293 : −29% endgame-rois, +74 Elo — la recherche mord
# dans la TB sur l'entre-deux 8-21), (d) COVERAGE exacte (--gen-egdb-wld, densité finale ≤7 gratuite).
# Multi-gen. egdb ON en génération, OFF aux benchmarks (éval pure). Cible : endgame-rois ≪ 2.04 (0293-B,
# 1-gen) + re-baseline vs Scan. PAS de FM (prématuré : Scan est linéaire, on rattrape DANS la classe).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0297-saturate-loop/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
APP=/root/egdb_extracted/app
ls "$APP"/db2.idx1 >/dev/null 2>&1 || { echo "ABORT: base egdb absente"; exit 4; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1

rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON -DJASS_ENDGAME_FEATURES=ON \
      -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "KING-AWARE patterns ENABLED" "$ART/cmake.log" || { echo "ABORT: pas king-aware"; exit 5; }
grep -q "ENDGAME FEATURES ENABLED"   "$ART/cmake.log" || { echo "ABORT: features off"; exit 5; }
grep -q "EXTERNAL EGDB ENABLED"      "$ART/cmake.log" || { echo "ABORT: egdb off"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
"$JASS" --egdb-selfcheck "$APP" 1 >/dev/null 2>&1 || { echo "ABORT: egdb ne s'ouvre pas"; exit 6; }

EVAL_DEPTH=6; PLAY_DEPTH=8; NPER=500000; NGEN=6; BD=9; EPAIRS=15
RAMP="late-mid=12,endgame=16"
CFOLD="--full-fold --king-patterns"
declare -A ELO EGM
CUM="$ART/cumulative.jnnw"
echo "PARAMS: egdb-perfect + DEPTH-RAMP($RAMP) + coverage + ENDGAME-FEATURES, $NPER/gen ×$NGEN"

fit_wdl(){ python3 pattern_jass/tools/train.py --data "$1" --scan-eval --eval-features-file "$2" \
            --loss logistic --l2 "$4" --max-iter 200 --scale 1000 --prune --lowmem $CFOLD --out "$3.pjtw" >"$3-train.log" 2>&1; }
val_endgame(){ grep -oE 'val/phase mse : .*' "$1-train.log" | grep -oE 'endgame=[0-9.]+' | head -1 | cut -d= -f2; }
elo_vs_hc(){ local lg="$ART/elo-$(basename "$1" .pjtw).log"   # egdb OFF = éval pure
  $JASS --benchmark-scan-eval "$1" hc "$BD" "$2" "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2); local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  echo "${W:-0}-${D:-0}-${L:-0} elo=$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2)"; }
# génération : egdb ON (inline) + depth-ramp sur play ET label
gen_and_append(){ local NN=$1; local OUTP=$2; local CUM=$3; shift 3; local PER=$(( (NN + NCPU - 1) / NCPU ))
  for s in $(seq 1 "$NCPU"); do
    JASS_EGDB_PATH="$APP" JASS_EGDB_CACHE_MB=256 \
      $JASS --gen-data-wdl "$PER" "${OUTP}-$s.jnnw" "$EVAL_DEPTH" "$PLAY_DEPTH" 200 $((RANDOM)) \
        --play-depth-by-phase "$RAMP" --label-depth-by-phase "$RAMP" "$@" >"${OUTP}-$s.log" 2>&1 &
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

echo "=== coverage exacte ≤7 (densité finale gratuite) → seed du cumulatif ==="
$JASS --gen-egdb-wld 400000 "$CUM" "$APP" 7 256 12345 2>&1 | tail -1

echo "=== gen0 : seed self-play (300k, egdb-perfect + ramp) sur coverage → l2=3e-2 ==="
gen_and_append 300000 "$ART/sp0" "$CUM"
$JASS --dump-eval-features "$CUM" "$ART/feat0" 2>&1 | tail -1
fit_wdl "$CUM" "$ART/feat0" "$ART/gen0" 3e-2
[ -f "$ART/gen0.pjtw" ] || { echo ABORT seed; tail -8 "$ART/gen0-train.log"; exit 7; }
EGM[0]=$(val_endgame "$ART/gen0"); ELO[0]=$(elo_vs_hc "$ART/gen0.pjtw" "$EPAIRS"); echo "  gen0 endgame_mse=${EGM[0]} Elo=${ELO[0]}"
case "${ELO[0]}" in *elo=0-0-0*|*0-0-0*) echo "ABORT desync"; exit 8;; esac

PREV="$ART/gen0"
for g in $(seq 1 "$NGEN"); do
  echo "=== gen$g : +${NPER} (egdb-perfect + ramp) avec gen$((g-1)) → cumulé → logistic ==="
  gen_and_append "$NPER" "$ART/sp$g" "$CUM" --nnue "$PREV.pjtw"
  $JASS --dump-eval-features "$CUM" "$ART/feat$g" 2>&1 | tail -1
  fit_wdl "$CUM" "$ART/feat$g" "$ART/gen$g" 3e-4
  [ -f "$ART/gen$g.pjtw" ] || { echo "ABORT gen$g"; tail -8 "$ART/gen$g-train.log"; exit 7; }
  EGM[$g]=$(val_endgame "$ART/gen$g"); ELO[$g]=$(elo_vs_hc "$ART/gen$g.pjtw" "$EPAIRS"); echo "  gen$g endgame_mse=${EGM[$g]} Elo=${ELO[$g]}"
  PREV="$ART/gen$g"
done
echo "=== gen${NGEN} vs hc précis (60p) ==="; ELOF=$(elo_vs_hc "$ART/gen${NGEN}.pjtw" 60); echo "  $ELOF"

# --- re-baseline + autopsie vs Scan (egdb OFF = éval pure) ---
SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1 || true; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
SCAN5=""; AUTOP=""
if [ -x "$SCAN_BIN" ]; then
  GAMES="$ART/games"; mkdir -p "$GAMES"
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/gen${NGEN}.pjtw" \
      --scan-bb-size 0 --movetime 0.5 --pairs 3 --dump-games-dir "$GAMES" >"$ART/scan-mt05.log" 2>&1
  SCAN5=$(grep -E 'score rate|ELO estimate' "$ART/scan-mt05.log" | tr '\n' ' ')
  python3 tools/game_autopsy.py --games-dir "$GAMES" --jass /bin/true --scan "$SCAN_BIN" \
      --scan-depth 11 --scan-bb-size 0 --worst 8 --out "$ART/autopsy.txt" 2>"$ART/autopsy.err" || echo "(autopsie skip)"
  AUTOP=$(sed -n '/PHASE × ROIS/,/par TACTIQUE/p' "$ART/autopsy.txt" 2>/dev/null | head -12)
fi

echo; echo "=========================================================="
echo "   cpx62-0297 — SATURER LE LINÉAIRE (egdb-perfect + depth-ramp + coverage + features)"
echo "----------------------------------------------------------"
for g in $(seq 0 "$NGEN"); do echo "  gen$g  Elo_vs_hc=${ELO[$g]}   endgame_mse=${EGM[$g]}"; done
echo "  gen${NGEN} (60p) vs hc : $ELOF   [0287 uniforme-8 = +233.9 ; 0276 = +230]"
[ -n "$SCAN5" ] && echo "  gen${NGEN} vs Scan mt0.5 : $SCAN5   [0287 = −741]"
echo "----------------------------------------------------------"
echo "  AUTOPSIE FINALE (perte phase×rois vs Scan ; cibles : 0287=3.22, 0293-B-1gen=2.04) :"
echo "$AUTOP"
echo "----------------------------------------------------------"
echo "  endgame-rois ≪ 2.04 + Elo ≫ +234 + vs Scan ≫ −741 → la classe linéaire MONTE encore"
echo "     (saturation pas atteinte) → continuer à scaler données/cycles."
echo "  plateau (≈ 0293/0287) → la classe linéaire SATURE en finale → ALORS capacité (FM/MLP/MTC)."
echo "=========================================================="
