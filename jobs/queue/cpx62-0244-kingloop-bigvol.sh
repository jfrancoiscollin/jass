#!/usr/bin/env bash
# id: cpx62-0244-kingloop-bigvol
# description: LE PUSH ×2 — loop full-fold KING-AWARE GROS VOLUME (1.5M/gen → ~12M cumulé,
# 2.4× le 0241 à 5M). Pousse la couverture de ~95% (0241) vers la DENSITÉ (plus de visites/
# poids → moins de bruit), là où la famine (0242) dit qu'il reste de l'Elo. NB : 32 Go
# plafonnent le full-batch ~12M (le pic = extras denses n×212 float32, ~2 Go/M) ; au-delà
# (15-40M, cible « dense ≥8 ») il faudra un train minibatch. Si un gen OOM → abort propre,
# on garde la trajectoire jusque-là. Elo réel vs hc/gen ; à comparer à 0241 +229.5 (60p).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0244-kingloop-bigvol/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
REF=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
[ -f "$REF" ] || { echo "ABORT: master de référence introuvable"; exit 3; }

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "KING-AWARE patterns ENABLED" "$ART/cmake.log" || { echo "ABORT: build pas king-aware"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
echo "geometry: $(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)") patterns ; KING-AWARE ; GROS VOLUME"

EVAL_DEPTH=6; PLAY_DEPTH=4; NPER=1500000; NGEN=8; BD=9; EPAIRS=15
CFOLD="--full-fold --king-patterns"
declare -A ELO
proxy(){ python3 tools/eval_proxy.py --jass "$JASS" --eval "$1.pjtw" --testset "$REF" \
           --offset 1300000 --max 50000 --score-drop 4900 2>/dev/null | grep -oE 'spearman=[-0-9.]+' | head -1 | cut -d= -f2; }
fit_wdl(){ python3 pattern_jass/tools/train.py --data "$1" --scan-eval --eval-features-file "$2" \
            --loss logistic --l2 "$4" --max-iter 200 --scale 1000 --prune $CFOLD --out "$3.pjtw" >"$3-train.log" 2>&1; }
elo_vs_hc(){ local lg="$ART/elo-$(basename "$1" .pjtw).log"
  $JASS --benchmark-scan-eval "$1" hc "$BD" "$2" "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  local L=$(grep -oE 'NNUE=[0-9]+'      "$lg"|tail -1|cut -d= -f2)
  local D=$(grep -oE 'Draws=[0-9]+'     "$lg"|tail -1|cut -d= -f2)
  local E=$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2)
  echo "${W:-0}-${D:-0}-${L:-0} elo=${E:-NA}"
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
echo "=== gen0 : seed (400k self-play embarqué depth4, l2=3e-2) KING-AWARE ==="
gen_and_append 400000 "$ART/sp0" "$CUM"
$JASS --dump-eval-features "$CUM" "$ART/feat0" 2>&1 | tail -1
fit_wdl "$CUM" "$ART/feat0" "$ART/gen0" 3e-2
[ -f "$ART/gen0.pjtw" ] || { echo ABORT seed; tail -5 "$ART/gen0-train.log"; exit 7; }
ELO[0]=$(elo_vs_hc "$ART/gen0.pjtw" "$EPAIRS")
echo "  gen0 proxy=$(proxy "$ART/gen0")  Elo_vs_hc=${ELO[0]}"
case "${ELO[0]}" in 0-0-0*) echo "ABORT: gen0 0-0-0 → désync"; exit 8;; esac

PREV="$ART/gen0"
for g in $(seq 1 "$NGEN"); do
  echo "=== gen$g : +${NPER} self-play depth4 (king-aware) avec gen$((g-1)) → cumulé → logistic($CFOLD) ==="
  gen_and_append "$NPER" "$ART/sp$g" "$CUM" --nnue "$PREV.pjtw"
  $JASS --dump-eval-features "$CUM" "$ART/feat$g" 2>&1 | tail -1
  fit_wdl "$CUM" "$ART/feat$g" "$ART/gen$g" 3e-4
  if [ ! -f "$ART/gen$g.pjtw" ]; then
    echo "  gen$g train ÉCHEC (OOM probable à ce volume) — on s'arrête, trajectoire gardée jusqu'à gen$((g-1))"; tail -4 "$ART/gen$g-train.log"; NGEN=$((g-1)); break
  fi
  ELO[$g]=$(elo_vs_hc "$ART/gen$g.pjtw" "$EPAIRS")
  echo "  gen$g proxy=$(proxy "$ART/gen$g")  Elo_vs_hc=${ELO[$g]}"
  PREV="$ART/gen$g"
done
echo "=== gen${NGEN} vs hc précis (60 paires) ==="; ELOF=$(elo_vs_hc "$ART/gen${NGEN}.pjtw" 60); echo "  $ELOF"

echo; echo "=========================================================="
echo "   cpx62-0244 — LOOP KING-AWARE GROS VOLUME (1.5M/gen, ~12M) — TRAJECTOIRE Elo"
for g in $(seq 0 "$NGEN"); do echo "  gen$g  Elo_vs_hc=${ELO[$g]}"; done
echo "  gen${NGEN} (60p) : $ELOF"
echo "  → comparer à 0241 (king-aware 5M) +229.5 : densifier (5M→12M) monte-t-il encore ?"
echo "=========================================================="
