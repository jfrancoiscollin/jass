#!/usr/bin/env bash
# id: cpx62-0312-phase-split-ab
# description: FIX (b) de 0310 — le conflit de phase. 0310 : la finale fitte BIEN mieux SEULE (deep-eg
# 3.27) que dans le fit partagé (endgame 5.39), car le blend wmg=pièces/40 fait que CHAQUE position de
# midgame tire le bank eg de 0.25. On RAIDIT la rampe [LO,HI] pour que le bank eg se spécialise sur la
# finale. A/B mêmes données (cumulatif 0297), même feature-dump partagé (le blend s'applique au fit/eval,
# pas au dump) : CONTROL 0/40 (=legacy) vs SHARP1 10/24 vs SHARP2 8/18. Mesure endgame_mse (cible : vers
# le plancher 3.27) + Elo vs hc (cible : ≥ +222, idéalement vers le +268 du NO-ENDGAME). Pré-flight gardé.
# expected_duration: ~75 min
set -uo pipefail
cd /root/jass
source jobs/lib/preflight.sh
CUM=/root/jass/jobs/results/cpx62-0297-saturate-loop/artefacts.src/cumulative.jnnw
[ -f "$CUM" ] || { echo "ABORT: cumulatif 0297 absent"; exit 3; }
ROWS=$(python3 -c "import struct;print(struct.unpack('<I',open('$CUM','rb').read(8)[4:8])[0])")
preflight_build 3
preflight_note "feature dump (partagé)" 5
preflight_train "$ROWS" 3
preflight_note "elo×3" 15
preflight_check

ART="/root/jass/jobs/results/cpx62-0312-phase-split-ab/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
CFOLD="--full-fold"

# --- build CONTROL once, dump features ONCE (raw features are phase-independent) ---
rm -rf build-ctrl
cmake -S . -B build-ctrl -DCMAKE_BUILD_TYPE=Release >"$ART/ctrl-cmake.log" 2>&1
cmake --build build-ctrl -j"$NCPU" --target jass >"$ART/ctrl-build.log" 2>&1 || { echo "CTRL BUILD FAIL"; tail -15 "$ART/ctrl-build.log"; exit 5; }
"$PWD/build-ctrl/jass" --dump-eval-features "$CUM" "$ART/feat" >"$ART/dump.log" 2>&1
echo "cumulatif=$ROWS lignes ; features dumpées (partagées)"

elo(){ local lg="$3"; "$1" --benchmark-scan-eval "$2" hc 9 60 "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2); local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  echo "$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2) (${W:-0}-${D:-0}-${L:-0})"; }

declare -A MSE ELO
variant(){ # <name> <LO> <HI>
  local name="$1" lo="$2" hi="$3" B="build-$1"
  if [ "$name" = "ctrl" ]; then B="build-ctrl"; else
    rm -rf "$B"
    cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_PHASE_LO="$lo" -DJASS_PHASE_HI="$hi" >"$ART/$name-cmake.log" 2>&1
    cmake --build "$B" -j"$NCPU" --target jass >"$ART/$name-build.log" 2>&1 || { echo "$name BUILD FAIL"; tail -10 "$ART/$name-build.log"; return 1; }
  fi
  local J="$PWD/$B/jass"
  python3 pattern_jass/tools/train.py --data "$CUM" --scan-eval --eval-features-file "$ART/feat" \
    --loss logistic --l2 3e-4 --max-iter 200 --scale 1000 --prune --lowmem $CFOLD \
    --phase-lo "$lo" --phase-hi "$hi" --out "$ART/$name.pjtw" >"$ART/$name-train.log" 2>&1
  [ -f "$ART/$name.pjtw" ] || { echo "$name TRAIN FAIL"; tail -8 "$ART/$name-train.log"; return 1; }
  MSE[$name]=$(grep -oE 'val/phase mse : .*' "$ART/$name-train.log" | grep -oE 'endgame=[0-9.]+' | head -1 | cut -d= -f2)
  ELO[$name]=$(elo "$J" "$ART/$name.pjtw" "$ART/$name-elo.log")
  echo "  $name (ramp $lo/$hi) : endgame_mse=${MSE[$name]}  Elo_vs_hc=${ELO[$name]}"
}

echo "=== CONTROL (0/40 = legacy pièces/40) ==="; variant ctrl   0  40
echo "=== SHARP1 (10/24) ===";                    variant sharp1 10 24
echo "=== SHARP2 (8/18) ===";                     variant sharp2 8  18

echo; echo "=========================================================="
echo "   cpx62-0312 — PHASE-SPLIT (fix conflit 0310, linéaire)"
echo "----------------------------------------------------------"
printf "  %-7s endgame_mse=%-8s Elo=%s\n" ctrl   "${MSE[ctrl]:-NA}"   "${ELO[ctrl]:-NA}"
printf "  %-7s endgame_mse=%-8s Elo=%s\n" sharp1 "${MSE[sharp1]:-NA}" "${ELO[sharp1]:-NA}"
printf "  %-7s endgame_mse=%-8s Elo=%s\n" sharp2 "${MSE[sharp2]:-NA}" "${ELO[sharp2]:-NA}"
echo "----------------------------------------------------------"
echo "  SHARP endgame_mse < CONTROL (vers le plancher 3.27 de 0310) + Elo ≈/> +222 → le phase-split"
echo "     résorbe le conflit (le bank eg se spécialise) → baker LO/HI gagnant par défaut + autopsie vs"
echo "     Scan (endgame-rois) sur le gagnant. Si Elo chute → la rampe trop dure coupe le midgame → ajuster."
echo "=========================================================="
