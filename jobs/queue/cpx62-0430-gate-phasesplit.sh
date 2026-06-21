#!/usr/bin/env bash
# id: cpx62-0430-gate-phasesplit
# description: GATE phase-split au scale — la SPECIALISATION FINALE (banc eg) fut CONDAMNEE a <=2M (0310 "conflit de
# phase", 0355/0358) => CONFONDUE par le fit-volume, JAMAIS retestee a gros volume. A 44M+ chaque banc (mg/eg) a de quoi
# se specialiser sans s'affamer. LO/HI de la rampe + TEMPO_STAGE = constantes BUILD (scan_eval.hpp), la def de phase doit
# matcher train+eval => 3 builds, chaque .pjtw joue avec SON binaire :
#   A = tempo-stage (BASELINE prod)        train --tempo-stage
#   B = piece-ramp defaut LO=0,HI=40       train --phase-lo 0  --phase-hi 40   (driver piece-count, lisse)
#   C = piece-ramp AIGUE LO=10,HI=24       train --phase-lo 10 --phase-hi 24   (banc eg SPECIALISE)
# 2 juges cross vs baseline A. color-fold men-only partout (archi verrouillee 0401/0408/0409). Hors-tree, gzip. Aucun Scan.
# >>> NON DEPLOYE tant que la boucle d'iteration tourne (a tirer apres, dans la file de-confondage). expected_duration: ~7 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-540}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0430-gate-phasesplit/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"
W=/root/cw-gate-phase; rm -rf "$W"; mkdir -p "$W"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
GEOM=/root/jass-geom32-phase; MAXIT=25; CHUNK=1000000
say(){ echo "$@" | tee -a "$RES"; }

preflight_build 3; preflight_train 45000000 1; preflight_note "3 builds (phase) + assemble + dump feat + 3 fits + 2 juges" 200; preflight_check

cmake_jass(){ # $1=builddir $2=flags de phase (variable)
  cmake -S . -B "$1" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON $2 >"$W/cmake-$(basename "$1").log" 2>&1
  grep -q "EXTERNAL EGDB ENABLED" "$W/cmake-$(basename "$1").log" || { echo "ABORT egdb $1"; exit 6; }
  cmake --build "$1" -j"$(mem_safe_jobs)" --target jass >"$W/bd-$(basename "$1").log" 2>&1 || { echo "BUILD FAIL $1"; tail -8 "$W/bd-$(basename "$1").log"; exit 6; }; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1

echo "=== 3 builds (def de phase differente) ==="
cmake_jass "$W/build-A" "-DJASS_TEMPO_STAGE=ON"
cmake_jass "$W/build-B" ""
cmake_jass "$W/build-C" "-DJASS_PHASE_LO=10 -DJASS_PHASE_HI=24"
JA="$W/build-A/jass"; JB="$W/build-B/jass"; JC="$W/build-C/jass"
[ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { echo "ABORT: attendait 32 patterns, a $NP"; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
say "# builds OK : A=tempo ($JA) · B=piece-defaut ($JB) · C=piece-aigue LO10/HI24 ($JC)"

echo "=== assemble corpus + dump FEAT (extras independants de la phase, dump via build A) ==="
tools/corpus_manifest.sh assemble "$W/big.jnnw" 2>"$W/assemble.log" || { echo "ABORT assemble"; tail "$W/assemble.log"; exit 8; }
NBIG=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/big.jnnw','rb').read(8)[4:8])[0])")
say "# corpus assemble : ${NBIG} positions"
[ "$NBIG" -ge 25000000 ] || { echo "ABORT: corpus ${NBIG} < 25M"; exit 8; }
"$JA" --dump-eval-features "$W/big.jnnw" "$W/feat.full" >"$W/feat.log" 2>&1 || { echo "ABORT dump feat"; tail "$W/feat.log"; exit 8; }

fit(){ # $1=phase-flags-train $2=out $3=tag
  echo "  [fit $3] train_stream color-fold $1 maxit=$MAXIT"
  env JASS_PATTERNS_DIR="$GEOM" python3 pattern_jass/tools/train_stream.py --data "$W/big.jnnw" --feat "$W/feat.full" \
      --color-fold $1 --loss logistic --l2 1e-4 --max-iter "$MAXIT" --chunk "$CHUNK" --out "$2" \
      >"${2%.pjtw}.log" 2>&1 || { echo "TRAIN FAIL $3"; tail -12 "${2%.pjtw}.log"; exit 9; }
  grep -iE "train_loss|wrote" "${2%.pjtw}.log" | tail -1 | sed 's/^/    /'; }

say "# --- FITS (def de phase = celle du build correspondant) ---"
fit "--tempo-stage"            "$W/A.pjtw" "A tempo"
fit "--phase-lo 0 --phase-hi 40"  "$W/B.pjtw" "B piece-defaut"
fit "--phase-lo 10 --phase-hi 24" "$W/C.pjtw" "C piece-aigue"
gzip -c "$W/C.pjtw" > "$ART/w32-phase-aigue.pjtw.gz" 2>/dev/null || true
say "# fits OK"

judge(){ # $1=JA $2=PA $3=JB $4=PB
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py \
     --jass-a "$1" --pattern-a "$2" --jass-b "$3" --pattern-b "$4" \
     --depth 9 --pairs 14 --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet >"$W/j.$s" 2>"$W/je.$s" & done; wait
  python3 - "$W"/j.* <<'PY'
import sys; a=d=b=0
for f in sys.argv[1:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x); d+=int(y); b+=int(z)
  except: pass
g=a+d+b; print(f"{(a+0.5*d)/g:.4f} (N={g})" if g else "NA")
PY
  rm -f "$W"/j.* "$W"/je.* ; }

say "# --- JUGES (score vs baseline A=tempo-stage, >0.5 => bat la prod) ---"
say "B  piece-defaut(LO0/HI40)  vs A tempo = $(judge "$JB" "$W/B.pjtw" "$JA" "$W/A.pjtw")   [effet DRIVER : piece-count vs tempo]"
say "C  piece-AIGUE(LO10/HI24)   vs A tempo = $(judge "$JC" "$W/C.pjtw" "$JA" "$W/A.pjtw")   [SPECIALISATION finale paie au scale ?]"

say ""
say "================= LECTURE ================="
say "  C > 0.55 => la specialisation eg (rampe aigue) PAIE au scale (etait CONFONDUE par le fit <=2M) -> adopter."
say "  C ~ 0.5  => tempo-stage suffit a ${NBIG} (banc eg ~ok, pas decisif ; retester au doublement)."
say "  C < 0.45 => tempo-stage confirme meilleur ; le conflit de phase 0310 tenait au scale (lisse > specialise)."
say "  B isole le DRIVER (piece vs tempo) : si B~A mais C>A => c'est la SHARPNESS qui compte, pas le driver."
say "==========================================="
