#!/usr/bin/env bash
# id: cpx62-0217-elo-loop-mt30
# description: RÉORIENTATION POST-B4 — la boucle WDL COMPOUNDE en Elo RÉEL (le proxy
# sous-lit, cf 0216). On reprend le SCALING mesuré au BON gauge : Elo réel vs handcrafted
# (commun, pas cher) à CHAQUE génération, sur ~10 gens, train --prune. Question : l'Elo
# réel CONTINUE-t-il de monter ou plafonne-t-il ? On garde le proxy en parallèle (doit
# stagner ~0.43 pendant que l'Elo grimpe → revalide B4 sur la durée). Jeu @mt30. À la fin :
# vs Scan (écart absolu). Pendant : ccx33-0218 joue en depth4 → compare la PROFONDEUR en Elo.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0217-elo-loop-mt30/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
REF=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
[ -f "$REF" ] || { echo "ABORT: master de référence introuvable"; exit 3; }

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

MT=30; EVAL_DEPTH=8; PLAY_CAP=8; NPER=300000; NGEN=10; BD=9; EPAIRS=15
declare -A ELO PRX
proxy(){ python3 tools/eval_proxy.py --jass "$JASS" --eval "$1.pjtw" --testset "$REF" \
           --offset 1300000 --max 50000 --score-drop 4900 2>/dev/null | grep -oE 'spearman=[-0-9.]+' | head -1 | cut -d= -f2; }
fit_wdl(){ python3 pattern_jass/tools/train.py --data "$1" --scan-eval --eval-features-file "$2" \
            --loss logistic --l2 "$4" --max-iter 200 --scale 1000 --prune --out "$3.pjtw" >"$3-train.log" 2>&1; }
elo_vs_hc(){ # <eval.pjtw> <pairs> → echoes "W D L | elo=...": real-game Elo vs handcrafted
  local lg="$ART/elo-$(basename "$1" .pjtw).log"
  $JASS --benchmark-scan-eval "$1" hc "$BD" "$2" "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  local L=$(grep -oE 'NNUE=[0-9]+'      "$lg"|tail -1|cut -d= -f2)
  local D=$(grep -oE 'Draws=[0-9]+'     "$lg"|tail -1|cut -d= -f2)
  local E=$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2)
  echo "${W:-0}-${D:-0}-${L:-0} elo=${E:-NA}"
}
gen_and_append(){ local NN=$1; local OUTP=$2; local CUM=$3; shift 3; local PER=$(( (NN + NCPU - 1) / NCPU ))
  for s in $(seq 1 "$NCPU"); do
    $JASS --gen-data-wdl "$PER" "${OUTP}-$s.jnnw" "$EVAL_DEPTH" "$PLAY_CAP" 200 $((RANDOM)) "$@" --movetime "$MT" >"${OUTP}-$s.log" 2>&1 &
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
echo "=== gen0 : seed (200k self-play embarqué @mt${MT}, l2=3e-2) ==="
gen_and_append 200000 "$ART/sp0" "$CUM"
$JASS --dump-eval-features "$CUM" "$ART/feat0" 2>&1 | tail -1
fit_wdl "$CUM" "$ART/feat0" "$ART/gen0" 3e-2
[ -f "$ART/gen0.pjtw" ] || { echo ABORT seed; exit 7; }
PRX[0]=$(proxy "$ART/gen0"); ELO[0]=$(elo_vs_hc "$ART/gen0.pjtw" "$EPAIRS")
echo "  gen0 proxy=${PRX[0]}  Elo_vs_hc=${ELO[0]}"

PREV="$ART/gen0"
for g in $(seq 1 "$NGEN"); do
  echo "=== gen$g : +${NPER} self-play @mt${MT} avec gen$((g-1)) → cumulé → logistic(--prune) ==="
  gen_and_append "$NPER" "$ART/sp$g" "$CUM" --nnue "$PREV.pjtw"
  $JASS --dump-eval-features "$CUM" "$ART/feat$g" 2>&1 | tail -1
  fit_wdl "$CUM" "$ART/feat$g" "$ART/gen$g" 3e-4
  [ -f "$ART/gen$g.pjtw" ] || { echo "ABORT gen$g"; exit 7; }
  PRX[$g]=$(proxy "$ART/gen$g"); ELO[$g]=$(elo_vs_hc "$ART/gen$g.pjtw" "$EPAIRS")
  echo "  gen$g proxy=${PRX[$g]}  Elo_vs_hc=${ELO[$g]}"
  PREV="$ART/gen$g"
done

# précise au dernier gen + vs Scan
echo "=== mesure précise gen${NGEN} vs hc (60 paires) ==="
FINE=$(elo_vs_hc "$ART/gen${NGEN}.pjtw" 60); echo "  gen${NGEN} vs hc (précis) = $FINE"
echo "=== gen${NGEN} vs Scan (best-effort, d${BD}) ==="
SCAN_DIR=/root/jass/.scan
if [ ! -x "$SCAN_DIR/scan_linux" ]; then rm -rf "$SCAN_DIR"; git clone --depth 1 https://github.com/rhalbersma/scan "$SCAN_DIR" 2>/dev/null && chmod +x "$SCAN_DIR/scan_linux" 2>/dev/null || echo "  (scan clone KO)"; fi
if [ -x "$SCAN_DIR/scan_linux" ]; then
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_DIR/scan_linux" \
    --jass-pattern "$ART/gen${NGEN}.pjtw" --depth "$BD" --pairs 40 --scan-book off --scan-bb-size 0 >"$ART/vs-scan.log" 2>&1 || true
  grep -E "Jass=|ELO estimate" "$ART/vs-scan.log" | tail -2 | sed 's/^/  /'
fi

echo; echo "=========================================================="
echo "   cpx62-0217 — BOUCLE Elo-INSTRUMENTÉE @mt${MT} — TRAJECTOIRE"
echo "  gen :  Elo_vs_hc  |  proxy"
for g in $(seq 0 "$NGEN"); do echo "   $g : ${ELO[$g]}   |  ${PRX[$g]}"; done
echo "  → Elo MONTE régulièrement = la recette scale vers Scan → continuer/scaler."
echo "  → Elo plafonne (alors que proxy plat aussi) = vrai plafond → Nœud 3 (géom/FM/non-lin)."
echo "  → compare depth4 (ccx33-0218) : la PROFONDEUR aide-t-elle EN ELO ?"
echo "=========================================================="
