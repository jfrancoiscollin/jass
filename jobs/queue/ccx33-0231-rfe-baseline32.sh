#!/usr/bin/env bash
# id: ccx33-0231-rfe-baseline32
# description: RFE GÉOMÉTRIE — BRAS TÉMOIN (32 patterns, v4 complet). Réplique EXACTE
# de la boucle full-fold de 0227 (8 gens, depth4, 300k/gen, l2 3e-2→3e-4, Elo réel vs hc
# par gen) pour re-mesurer la trajectoire 32-pat et la VITESSE d'eval (knps pattern / knps
# hc, indépendant de la machine). À comparer au bras ÉLAGUÉ cpx62-0232 (drop-8 → 24 pat).
# La géométrie est REGÉNÉRÉE au démarrage (gen_patterns --variant v4 --emit) : pas de
# dépendance au géo sur main. Question : élaguer 8 pat coûte-t-il de l'Elo, gagne-t-on en vitesse ?
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0231-rfe-baseline32/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
REF=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
[ -f "$REF" ] || { echo "ABORT: master de référence introuvable"; exit 3; }

# --- regenerate the BASELINE 32-pattern geometry into the working tree, then build ---
python3 pattern_jass/tools/gen_patterns.py --variant v4 --emit > "$ART/geom.log" 2>&1 || { echo GEOM FAIL; cat "$ART/geom.log"; exit 4; }
echo "geometry: $(grep -oE 'NUM_PATTERNS set to [0-9]+' "$ART/geom.log" || echo '?') ($(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import importlib,patterns;importlib.reload(patterns);print(patterns.NUM_PATTERNS)") patterns)"
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

EVAL_DEPTH=6; PLAY_DEPTH=4; NPER=300000; NGEN=8; BD=9; EPAIRS=15
CFOLD="--full-fold"
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
echo "=== gen${NGEN} vs hc précis (60 paires) ==="; ELOF=$(elo_vs_hc "$ART/gen${NGEN}.pjtw" 60); echo "  $ELOF"

echo "=== VITESSE eval : knps(pattern) vs knps(hc), movetime=1000ms (indépendant machine) ==="
$JASS --depth-at-movetime "$ART/gen${NGEN}.pjtw" hc 1000 64 >"$ART/speed.log" 2>&1
KP=$(grep -oE 'knps~[0-9.]+' "$ART/speed.log" | sed -n '1p' | cut -d~ -f2)
KH=$(grep -oE 'knps~[0-9.]+' "$ART/speed.log" | sed -n '2p' | cut -d~ -f2)
DP=$(grep -oE 'depth avg=[0-9.]+' "$ART/speed.log" | sed -n '1p' | cut -d= -f2)
RATIO=$(python3 -c "print(f'{${KP:-0}/${KH:-1}:.3f}')" 2>/dev/null || echo NA)
echo "  pattern knps=${KP:-NA}  hc knps=${KH:-NA}  ratio=${RATIO}  depth@1s=${DP:-NA}"

echo; echo "=========================================================="
echo "   ccx33-0231 — RFE BRAS TÉMOIN 32-PAT — TRAJECTOIRE Elo + VITESSE"
for g in $(seq 0 "$NGEN"); do echo "  gen$g  Elo_vs_hc=${ELO[$g]}  proxy=${PRX[$g]}"; done
echo "  gen${NGEN} (60p) : $ELOF"
echo "  SPEED 32-pat : pattern/hc knps ratio=${RATIO}  depth@1s=${DP}"
echo "  → comparer à cpx62-0232 (24-pat élagué) : ΔElo = coût du prune, Δratio = gain vitesse"
echo "=========================================================="
