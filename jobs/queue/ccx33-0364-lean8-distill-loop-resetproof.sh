#!/usr/bin/env bash
# id: ccx33-0364-lean8-distill-loop-resetproof
# description: RELANCE RESET-PROOF de la boucle distillation lean-8 (0362 invalidé : le runner a reset l'arbre git en
# cours de job → mon `gen_patterns --emit` réverté de 8→32 entre gen1 et gen2 → trainer flippé en 32 → cascade). Fix
# (bug 0232 documenté) : on copie le patterns.py 8-pat HORS du tree git et on pin `JASS_PATTERNS_DIR` → le trainer lit
# la géométrie 8 quel que soit le reset (le binaire C++, lui, est figé au build). + GARDE-FOU gen0 : on vérifie que le
# binaire charge bien un pjtw 8-pat (sinon le build a été resetté avant compil → ABORT). Reste = 0362 : gen0 distill
# old-scan (8-pat color-fold = capacité Scan 2.1M) ; chaque gen self-play(gen_{k-1})→relabel Scan d9→pool→refit ; juge
# gen_k vs gen0 DIRECT (sensible) + vs Scan. NB 0362 (partie propre gen0→gen1) : gen1 DIRECT=0.333 = PIRE → ajouter du
# jass-self-play dégradait. Ici on veut la trajectoire COMPLÈTE propre pour trancher net (le jass-self-play aide-t-il ?).
# expected_duration: ~3 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-240}"
source jobs/lib/preflight.sh
source jobs/lib/relabel.sh
ART="/root/jass/jobs/results/ccx33-0364-lean8-distill-loop-resetproof/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
GEOM=/root/jass-geom-lean8        # HORS du tree git → survit au reset du runner
NGEN=3; NPER=15000; RELABEL_DEPTH=9; PLAY_DEPTH=6; EVAL_DEPTH=4
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent"; exit 4; }

preflight_build 1; preflight_train 240000 $((NGEN+1)); preflight_note "loop ${NGEN} gens reset-proof : selfplay + relabel Scan d${RELABEL_DEPTH} + DIRECT/vsScan" 150; preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan indispo"; exit 5; }

echo "=== régénère le jeu LEAN 8 + build + PIN géométrie hors-tree (reset-proof) ==="
python3 pattern_jass/tools/gen_patterns.py --emit \
  --drop diag_0,diag_1,diag_2,diag_3,diag_4,diag_5,diag_6,anti_0,anti_1,anti_2,anti_3,anti_4,anti_5,anti_6,anti_7,horiz_0,horiz_1,horiz_2,horiz_3,horiz_4,sq_0,sq_1,sq_2,sq_3 >"$ART/gen8.log" 2>&1
NP8=$(grep -oE "NUM_PATTERNS *= *[0-9]+" pattern_jass/src/pattern.hpp | grep -oE "[0-9]+" | head -1)
[ "$NP8" = "8" ] || { echo "ABORT: réduction patterns ratée (NP8=$NP8)"; tail -20 "$ART/gen8.log"; exit 7; }
# build IMMÉDIATEMENT (le binaire fige 8 ; un reset ultérieur ne le touche plus)
B=build-lean8; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -8 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"
# PIN la géométrie 8-pat HORS du tree git → le trainer la lit même si le runner reset l'arbre vers main (bug 0232).
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
export JASS_PATTERNS_DIR="$GEOM"
python3 -c "import sys; sys.path.insert(0,'$GEOM'); import patterns as P; assert P.NUM_PATTERNS==8, P.NUM_PATTERNS; print('  géométrie pinnée :',P.NUM_PATTERNS,'patterns, TOTAL_BUCKETS',P.TOTAL_BUCKETS)" || { echo "ABORT: pin géométrie raté"; exit 7; }

fit(){ # <pool.jnnw> <out-prefix> — trainer lit JASS_PATTERNS_DIR (8-pat) ; color-fold = capacité Scan 2.1M
  "$JASS" --dump-eval-features "$1" "$2.feat" >/dev/null 2>&1
  JASS_PATTERNS_DIR="$GEOM" python3 pattern_jass/tools/train.py --data "$1" --scan-eval --eval-features-file "$2.feat" \
    --target score --score-drop 3000 --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 --prune --lowmem --color-fold \
    --out "$2.pjtw" >"$2-train.log" 2>&1
  [ -f "$2.pjtw" ] || { echo "TRAIN FAIL $2"; tail -8 "$2-train.log"; exit 9; }
  # reset-proof check : le trainer DOIT rester en 8 patterns (2 125 768), jamais 32 (8 503 072).
  grep -qE "17M -> *8,503,072|17M -> *8503072" "$2-train.log" && { echo "ABORT: trainer flippé en 32 patterns (reset non contré) sur $2"; tail -4 "$2-train.log"; exit 8; }
  grep -E "color-fold|distinct|17M ->" "$2-train.log" | head -2 | sed 's/^/    [fit] /'
}
selfplay(){ local pilot="$1" out="$2" nn="$3"; local per=$(( (nn + NCPU - 1) / NCPU ))
  for s in $(seq 1 "$NCPU"); do
    "$JASS" --gen-data-wdl "$per" "$out.$s.jnnw" "$EVAL_DEPTH" "$PLAY_DEPTH" 200 "$((RANDOM*RANDOM+s))" --nnue "$pilot" >"$out.$s.log" 2>&1 &
  done; wait
  python3 - "$out" <<'PY'
import struct,glob,sys,re
out=sys.argv[1]; REC=38
shards=sorted(glob.glob(out+".*.jnnw"),key=lambda p:int(re.search(r"\.(\d+)\.jnnw$",p).group(1)))
body=b""; tot=0
for s in shards:
    b=open(s,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; tot+=n; body+=b[8:8+n*REC]
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body); print('selfplay merged',tot)
PY
  rm -f "$out".*.jnnw
}
append(){ python3 - "$1" "$2" <<'PY'
import struct,sys
src,pool=sys.argv[1],sys.argv[2]; REC=38
b=open(src,'rb').read(); n=(len(b)-8)//REC; body=b[8:8+n*REC]
raw=open(pool,'rb').read(); old=struct.unpack('<I',raw[4:8])[0]
o=open(pool,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+n)); o.close()
print('pool',old+n)
PY
}
rate(){ grep -E 'score rate' "$1" | grep -oE '0?\.[0-9]+|[01]\.[0-9]+' | head -1; }
direct(){ "$JASS" --benchmark-nnue-vs-nnue "$1.pjtw" "$ART/gen0.pjtw" 9 6 1 0 >"$1-direct.log" 2>&1 || true
  grep -E 'score rate' "$1-direct.log" | grep -oE '[0-9.]+' | head -1; }
vs_scan(){ python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$1.pjtw" \
    --scan-bb-size 0 --jass-depth 9 --scan-depth 9 --pairs 8 --max-plies 160 >"$1-vs.log" 2>&1 || true; rate "$1-vs.log"; }

POOL="$ART/pool.jnnw"; cp "$DATA" "$POOL"
declare -A DIR VS
echo "=== gen0 : distill old-scan (8-pat color-fold) = baseline ==="
fit "$POOL" "$ART/gen0"
# GARDE-FOU : le binaire DOIT charger un pjtw 8-pat (sinon build resetté avant compil) — gen0 vs lui-même d4.
"$JASS" --benchmark-nnue-vs-nnue "$ART/gen0.pjtw" "$ART/gen0.pjtw" 4 1 1 0 >"$ART/loadcheck.log" 2>&1 \
  && grep -qE 'score rate' "$ART/loadcheck.log" \
  || { echo "ABORT: le binaire ne charge pas le pjtw 8-pat (build resetté ?) — voir loadcheck.log"; tail -5 "$ART/loadcheck.log"; exit 8; }
echo "  [garde-fou] binaire ↔ pjtw 8-pat OK"
DIR[0]="0.500"; VS[0]=$(vs_scan "$ART/gen0")
echo "  gen0 vsScan=${VS[0]}"

PREV="$ART/gen0"
for g in $(seq 1 "$NGEN"); do
  echo "=== gen$g : self-play(gen$((g-1))) +${NPER} → relabel Scan d${RELABEL_DEPTH} → pool → refit ==="
  selfplay "$PREV.pjtw" "$ART/sp$g.jnnw" "$NPER" >>"$ART/loop.log" 2>&1
  relabel_scan_sharded "$ART/sp$g.jnnw" "$ART/sp$g.scan.jnnw" "$SCAN_BIN" "$RELABEL_DEPTH" "$NCPU"
  append "$ART/sp$g.scan.jnnw" "$POOL"
  fit "$POOL" "$ART/gen$g"
  DIR[$g]=$(direct "$ART/gen$g")
  if [ "$g" = "$NGEN" ]; then VS[$g]=$(vs_scan "$ART/gen$g"); else VS[$g]="-"; fi
  echo "  gen$g : DIRECT(vs gen0)=${DIR[$g]}  vsScan=${VS[$g]}"
  PREV="$ART/gen$g"
done

echo; echo "=========================================================="
echo "   ccx33-0364 — BOUCLE distillation lean-8 RESET-PROOF (color-fold, capacité Scan)"
echo "   gen :  DIRECT(vs gen0)   vsScan-d9"
for g in $(seq 0 "$NGEN"); do echo "    $g :   ${DIR[$g]:-NA}            ${VS[$g]:-NA}"; done
echo "----------------------------------------------------------"
echo "   DIRECT croît > 0.55 → itérer (jass-self-play Scan-relabel) améliore le fit → SCALER."
echo "   DIRECT ≤0.5 (comme 0362 gen1=0.333) → le jass-self-play dégrade → covariate-via-jass-self-play réfuté proprement."
echo "=========================================================="
