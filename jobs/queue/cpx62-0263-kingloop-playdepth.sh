#!/usr/bin/env bash
# id: cpx62-0263-kingloop-playdepth
# description: CHEMIN B — densification finale CORRIGÉE. Apprentissages : la boucle s'entraîne
# sur le WDL, donc (0254/0258) --label-depth-by-phase = no-op nocif (pollue la TT) et (0261)
# --phase-weight = MORT (-210 Elo). Le vrai levier : JOUER les finales plus profond pendant le
# self-play (--play-depth-by-phase) → les résultats WDL de finale deviennent FIABLES → la boucle
# +229 apprend la finale toute seule. Sinon = 0241 À L'IDENTIQUE (king-aware full-fold, full-batch,
# 600k/gen ×8, l2 3e-2→3e-4) pour isoler le SEUL effet du play-depth. Verdict = Elo vs hc par gen
# + 60p final + vs Scan mt0.5 ; val_endgame_mse suivi. gen8 conservé pour autopsie (vs 0250 = 3.6).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0263-kingloop-playdepth/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "KING-AWARE patterns ENABLED" "$ART/cmake.log" || { echo "ABORT: pas king-aware"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
echo "geometry: $(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)") patterns ; KING-AWARE"

EVAL_DEPTH=6; PLAY_DEPTH=4; NPER=600000; NGEN=8; BD=9; EPAIRS=15
PLAY_PHASE="endgame=12,deep-eg=14"        # JOUER les finales profond → WDL de finale fiables
CFOLD="--full-fold --king-patterns"
declare -A ELO EGM
echo "PARAMS: play-depth-by-phase=[$PLAY_PHASE]  (PAS de phase-weight, PAS de label-depth)  full-batch  $NPER/gen ×$NGEN"

fit_wdl(){ python3 pattern_jass/tools/train.py --data "$1" --scan-eval --eval-features-file "$2" \
            --loss logistic --l2 "$4" --max-iter 200 --scale 1000 --prune $CFOLD --out "$3.pjtw" >"$3-train.log" 2>&1; }
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
echo "=== gen0 : seed (300k, play profond finale, l2=3e-2) ==="
gen_and_append 300000 "$ART/sp0" "$CUM" --play-depth-by-phase "$PLAY_PHASE"
$JASS --dump-eval-features "$CUM" "$ART/feat0" 2>&1 | tail -1
fit_wdl "$CUM" "$ART/feat0" "$ART/gen0" 3e-2
[ -f "$ART/gen0.pjtw" ] || { echo ABORT seed; tail -8 "$ART/gen0-train.log"; exit 7; }
EGM[0]=$(val_endgame "$ART/gen0"); ELO[0]=$(elo_vs_hc "$ART/gen0.pjtw" "$EPAIRS")
echo "  gen0 val_endgame=${EGM[0]}  Elo_vs_hc=${ELO[0]}"
case "${ELO[0]}" in 0-0-0*) echo "ABORT: gen0 0-0-0 → désync"; exit 8;; esac

PREV="$ART/gen0"
for g in $(seq 1 "$NGEN"); do
  echo "=== gen$g : +${NPER} (play profond finale) avec gen$((g-1)) → cumulé → logistic ==="
  gen_and_append "$NPER" "$ART/sp$g" "$CUM" --nnue "$PREV.pjtw" --play-depth-by-phase "$PLAY_PHASE"
  $JASS --dump-eval-features "$CUM" "$ART/feat$g" 2>&1 | tail -1
  fit_wdl "$CUM" "$ART/feat$g" "$ART/gen$g" 3e-4
  [ -f "$ART/gen$g.pjtw" ] || { echo "ABORT gen$g"; tail -8 "$ART/gen$g-train.log"; exit 7; }
  EGM[$g]=$(val_endgame "$ART/gen$g"); ELO[$g]=$(elo_vs_hc "$ART/gen$g.pjtw" "$EPAIRS")
  echo "  gen$g val_endgame=${EGM[$g]}  Elo_vs_hc=${ELO[$g]}"
  PREV="$ART/gen$g"
done
echo "=== gen${NGEN} vs hc précis (60 paires) ==="; ELOF=$(elo_vs_hc "$ART/gen${NGEN}.pjtw" 60); echo "  $ELOF"

# verdict vs Scan (mt0.5)
SCAN_BIN=/root/jass-scan/scan_linux
if [ ! -x "$SCAN_BIN" ]; then rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1 || echo "(clone Scan échoué)"; chmod +x "$SCAN_BIN" 2>/dev/null || true; fi
SCAN5=""
[ -x "$SCAN_BIN" ] && { python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/gen${NGEN}.pjtw" \
    --scan-bb-size 0 --movetime 0.5 --pairs 3 >"$ART/scan-mt05.log" 2>&1; SCAN5=$(grep -E 'score rate|ELO estimate' "$ART/scan-mt05.log" | tr '\n' ' '); }

echo; echo "=========================================================="
echo "   cpx62-0263 — CHEMIN B : boucle king-aware + PLAY PROFOND FINALE (sans phase-weight/label-depth)"
echo "   play-depth-by-phase=[$PLAY_PHASE]  full-batch  $NPER/gen"
echo "----------------------------------------------------------"
for g in $(seq 0 "$NGEN"); do echo "  gen$g  Elo_vs_hc=${ELO[$g]}   val_endgame_mse=${EGM[$g]}"; done
echo "  gen${NGEN} (60p) vs hc : $ELOF"
[ -n "$SCAN5" ] && echo "  gen${NGEN} vs Scan mt0.5 : $SCAN5"
echo "----------------------------------------------------------"
echo "  CIBLE : Elo >= 0241 (+229.5) ET val_endgame_mse plus bas que la densif ratée (0254 ~3.16)."
echo "  Si oui → jouer les finales profond DENSIFIE bien la finale (lever correct). Autopsie ensuite."
echo "=========================================================="
