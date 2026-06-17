#!/usr/bin/env bash
# id: cpx62-0311-king-mobility-ab
# description: LEAD 1+2 (SCAN_EVAL_DIFF) — teste les features rois manquantes vs Scan, TOUTES linéaires.
# Mêmes données (cumulatif 0297), mêmes hyperparams, seules les FEATURES changent : BASE (défaut) /
# KMOB (JASS_KING_MOBILITY : king_mob séparé + roi-piégé, LE candidat conversion) / ENDG (JASS_ENDGAME_
# FEATURES : centralité+proximité) / KINGPAT (JASS_KING_PATTERNS : rois dans patterns, +37 Elo jadis).
# Pour chaque : endgame_mse (val) + Elo vs hc. Puis autopsie vs Scan (endgame-rois) sur BASE + KMOB.
# Cible : KMOB fait baisser endgame-rois sous le 2.91 de BASE sans casser l'Elo → la feature conversion.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0311-king-mobility-ab/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
CUM=/root/jass/jobs/results/cpx62-0297-saturate-loop/artefacts.src/cumulative.jnnw
[ -f "$CUM" ] || { echo "ABORT: cumulatif 0297 absent"; exit 3; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
SCAN_BIN=/root/jass-scan/scan_linux

elo(){ # $1=binary $2=pjtw  → echoes "elo (W-D-L)"
  local lg="$3"; "$1" --benchmark-scan-eval "$2" hc 9 60 "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2); local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  echo "$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2) (${W:-0}-${D:-0}-${L:-0})"; }

# variant <name> <cmake-flags> <extra-fold-flags>  → builds, dumps, trains, reports mse+Elo
declare -A BIN PJT MSE ELO
variant(){
  local name="$1" cflags="$2" fold="$3" B="build-$1"
  rm -rf "$B"
  cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release $cflags >"$ART/$name-cmake.log" 2>&1
  cmake --build "$B" -j"$NCPU" --target jass >"$ART/$name-build.log" 2>&1 || { echo "$name BUILD FAIL"; tail -8 "$ART/$name-build.log"; return 1; }
  local J="$PWD/$B/jass"
  "$J" --dump-eval-features "$CUM" "$ART/$name.feat" >"$ART/$name-dump.log" 2>&1
  python3 pattern_jass/tools/train.py --data "$CUM" --scan-eval --eval-features-file "$ART/$name.feat" \
    --loss logistic --l2 3e-4 --max-iter 200 --scale 1000 --prune --lowmem --full-fold $fold --out "$ART/$name.pjtw" >"$ART/$name-train.log" 2>&1
  [ -f "$ART/$name.pjtw" ] || { echo "$name TRAIN FAIL"; tail -8 "$ART/$name-train.log"; return 1; }
  BIN[$name]="$J"; PJT[$name]="$ART/$name.pjtw"
  MSE[$name]=$(grep -oE 'val/phase mse : .*' "$ART/$name-train.log" | grep -oE 'endgame=[0-9.]+' | head -1 | cut -d= -f2)
  ELO[$name]=$(elo "$J" "$ART/$name.pjtw" "$ART/$name-elo.log")
  echo "  $name : endgame_mse=${MSE[$name]}  Elo_vs_hc=${ELO[$name]}"
}

echo "=== BASE (défaut, men-only, 106 extras) ==="
variant base    ""                                                       ""
echo "=== KMOB (+JASS_KING_MOBILITY : king_mob séparé + roi-piégé) ==="
variant kmob    "-DJASS_KING_MOBILITY=ON"                                ""
echo "=== ENDG (+JASS_ENDGAME_FEATURES : centralité+proximité) ==="
variant endg    "-DJASS_ENDGAME_FEATURES=ON"                             ""
echo "=== KINGPAT (+JASS_KING_PATTERNS : rois dans patterns) ==="
variant kingpat "-DJASS_KING_PATTERNS=ON"                                "--king-patterns"

# --- autopsie vs Scan (endgame-rois) sur BASE + KMOB (le cœur de l'A/B) ---
autopsy(){ # $1=name
  local J="${BIN[$1]:-}" P="${PJT[$1]:-}"; [ -n "$J" ] && [ -x "$SCAN_BIN" ] || { echo "  ($1: autopsie sautée)"; return; }
  local G="$ART/games-$1"; mkdir -p "$G"
  python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$P" \
      --scan-bb-size 0 --movetime 0.5 --pairs 3 --dump-games-dir "$G" >"$ART/scan-$1.log" 2>&1 || true
  python3 tools/game_autopsy.py --games-dir "$G" --jass /bin/true --scan "$SCAN_BIN" \
      --scan-depth 11 --scan-bb-size 0 --worst 4 --out "$ART/autopsy-$1.txt" 2>"$ART/autopsy-$1.err" || echo "  ($1 autopsie skip)"
  echo "  --- $1 vs Scan ---"
  grep -iE 'deep-eg|endgame' "$ART/autopsy-$1.txt" 2>/dev/null | head -4 | sed 's/^/    /'
  grep -E 'score rate|ELO estimate' "$ART/scan-$1.log" | tr '\n' ' '; echo
}
echo "=== autopsie vs Scan : BASE puis KMOB ==="
autopsy base
autopsy kmob

echo; echo "=========================================================="
echo "   cpx62-0311 — features rois manquantes (LEAD 1+2, toutes linéaires)"
echo "----------------------------------------------------------"
printf "  %-8s endgame_mse=%-8s Elo=%s\n" base    "${MSE[base]:-NA}"    "${ELO[base]:-NA}"
printf "  %-8s endgame_mse=%-8s Elo=%s\n" kmob    "${MSE[kmob]:-NA}"    "${ELO[kmob]:-NA}"
printf "  %-8s endgame_mse=%-8s Elo=%s\n" endg    "${MSE[endg]:-NA}"    "${ELO[endg]:-NA}"
printf "  %-8s endgame_mse=%-8s Elo=%s\n" kingpat "${MSE[kingpat]:-NA}" "${ELO[kingpat]:-NA}"
echo "----------------------------------------------------------"
echo "  KMOB endgame_mse < BASE + endgame-rois(KMOB) < 2.91(BASE) + Elo ≈/> → la feature king_mob"
echo "     APPORTE le gradient de conversion (ce que 0306/MTC ratait) → l'intégrer + raffiner (sûreté)."
echo "  KINGPAT/ENDG > BASE → quick wins à activer par défaut. Sinon → piste suivante (densité données)."
echo "=========================================================="
