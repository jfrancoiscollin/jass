#!/usr/bin/env bash
# id: cpx62-0219-colorfold-loop
# description: PHASE 1 symmetry-sharing — A/B (bras COLOR-FOLD). Boucle WDL cumulée,
# depth4, train --prune --color-fold (antisym couleur : 17M→8.5M, ×2 data/poids), Elo
# RÉEL vs handcrafted par gen. Le bras témoin men-only = ccx33-0220 (mêmes réglages SANS
# --color-fold). Question : le partage de poids par couleur monte-t-il plus HAUT en Elo ?
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0219-colorfold-loop/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
REF=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
[ -f "$REF" ] || { echo "ABORT: master de référence introuvable"; exit 3; }

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

EVAL_DEPTH=6; PLAY_DEPTH=4; NPER=300000; NGEN=8; BD=9; EPAIRS=15
CFOLD="--color-fold"     # le bras COLOR-FOLD ; ccx33-0220 met CFOLD=""
declare -A ELO PRX
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
echo "=== gen0 : seed (200k self-play embarqué depth4, l2=3e-2) $CFOLD ==="
gen_and_append 200000 "$ART/sp0" "$CUM"
$JASS --dump-eval-features "$CUM" "$ART/feat0" 2>&1 | tail -1
fit_wdl "$CUM" "$ART/feat0" "$ART/gen0" 3e-2
[ -f "$ART/gen0.pjtw" ] || { echo ABORT seed; tail -5 "$ART/gen0-train.log"; exit 7; }
PRX[0]=$(proxy "$ART/gen0"); ELO[0]=$(elo_vs_hc "$ART/gen0.pjtw" "$EPAIRS")
echo "  gen0 proxy=${PRX[0]}  Elo_vs_hc=${ELO[0]}"

PREV="$ART/gen0"
for g in $(seq 1 "$NGEN"); do
  echo "=== gen$g : +${NPER} self-play depth4 avec gen$((g-1)) → cumulé → logistic(--prune $CFOLD) ==="
  gen_and_append "$NPER" "$ART/sp$g" "$CUM" --nnue "$PREV.pjtw"
  $JASS --dump-eval-features "$CUM" "$ART/feat$g" 2>&1 | tail -1
  fit_wdl "$CUM" "$ART/feat$g" "$ART/gen$g" 3e-4
  [ -f "$ART/gen$g.pjtw" ] || { echo "ABORT gen$g"; tail -5 "$ART/gen$g-train.log"; exit 7; }
  PRX[$g]=$(proxy "$ART/gen$g"); ELO[$g]=$(elo_vs_hc "$ART/gen$g.pjtw" "$EPAIRS")
  echo "  gen$g proxy=${PRX[$g]}  Elo_vs_hc=${ELO[$g]}"
  PREV="$ART/gen$g"
done
echo "=== gen${NGEN} vs hc précis (60 paires) ==="; echo "  $(elo_vs_hc "$ART/gen${NGEN}.pjtw" 60)"

echo; echo "=========================================================="
echo "   cpx62-0219 — PHASE 1 COLOR-FOLD — TRAJECTOIRE Elo"
echo "  gen :  Elo_vs_hc  |  proxy"
for g in $(seq 0 "$NGEN"); do echo "   $g : ${ELO[$g]}   |  ${PRX[$g]}"; done
echo "  → compare ccx33-0220 (men-only) : COLOR-FOLD monte-t-il PLUS HAUT en Elo ?"
echo "    si oui → la 1re brique de symétrie aide → Phase 2 (rotation 180°)."
echo "=========================================================="
