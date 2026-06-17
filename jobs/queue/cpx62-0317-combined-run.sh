#!/usr/bin/env bash
# id: cpx62-0317-combined-run
# description: LE VRAI TEST. Run combiné des deux leviers linéaires sur le dataset FINALE-ENRICHI (0314,
# 6.7M, 28.8% ≤7p), jugé à la FORCE (pas au endgame_mse, démasqué trompeur) : critical-win-preservation
# (--egdb-mtc-regret, baseline 0315 = 43%) + Elo vs hc. 4 bras, 1 variable changée chacun :
#   ctrl  = endg défaut (110), rampe 0/40
#   kmob  = + JASS_KING_MOBILITY (king_mob séparé/confinement)
#   phase = + rampe raidie 8/18 (phase-split)
#   combo = kmob + phase  (le candidat flywheel)
# Manifest par artefact (provenance). Pré-flight borné. SCREEN=mse (info) ; DECISION=critical+Elo.
# expected_duration: ~3 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-240}"
source jobs/lib/preflight.sh
source jobs/lib/manifest.sh
ART="/root/jass/jobs/results/cpx62-0317-combined-run/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
WLD=/root/egdb_extracted/app; MTC=/root/egdb_mtc/app
DATA=/root/jass/jobs/results/cpx62-0314-endgame-data-aug/artefacts.src/enriched-cumulative.jnnw
ls "$WLD"/db2.idx1 >/dev/null 2>&1 || { echo "ABORT: WLD absente"; exit 4; }
ls "$MTC" >/dev/null 2>&1 || { echo "ABORT: MTC absente"; exit 4; }
[ -f "$DATA" ] || { echo "ABORT: dataset enrichi 0314 absent ($DATA)"; exit 4; }
ROWS=$(python3 -c "import struct;print(struct.unpack('<I',open('$DATA','rb').read(8)[4:8])[0])")

preflight_build 4
preflight_train "$ROWS" 4
preflight_note "4× (mtc-regret + Elo)" 40
preflight_check
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
echo "dataset enrichi: $ROWS lignes ; $(python3 pattern_jass/tools/jnnw_stats.py "$DATA" 2>/dev/null | grep -E '<=7p|<=12p' | tr '\n' ' ')"
CFOLD="--full-fold"

elo(){ local lg="$1-elo.log"; "$2" --benchmark-scan-eval "$1.pjtw" hc 9 60 "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2); local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2; }

declare -A MSE CRIT ELO
variant(){ # <name> <kmob_flag> <lo> <hi>
  local name="$1" kmob="$2" lo="$3" hi="$4" B="build-$1"
  local phaseflag=""
  if [ "$lo" != "0" ] || [ "$hi" != "40" ]; then phaseflag="-DJASS_PHASE_LO=$lo -DJASS_PHASE_HI=$hi"; fi
  rm -rf "$B"
  cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
        -DJASS_ENDGAME_FEATURES=ON $kmob $phaseflag >"$ART/$name-cmake.log" 2>&1
  grep -q "EXTERNAL EGDB ENABLED" "$ART/$name-cmake.log" || { echo "$name: egdb off"; return 1; }
  cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/$name-build.log" 2>&1 || { echo "$name BUILD FAIL"; tail -8 "$ART/$name-build.log"; return 1; }
  local J="$PWD/$B/jass"
  "$J" --dump-eval-features "$DATA" "$ART/$name.feat" >"$ART/$name-dump.log" 2>&1
  python3 pattern_jass/tools/train.py --data "$DATA" --scan-eval --eval-features-file "$ART/$name.feat" \
    --loss logistic --l2 3e-4 --max-iter 200 --scale 1000 --prune --lowmem $CFOLD \
    --phase-lo "$lo" --phase-hi "$hi" --out "$ART/$name.pjtw" >"$ART/$name-train.log" 2>&1
  [ -f "$ART/$name.pjtw" ] || { echo "$name TRAIN FAIL"; tail -8 "$ART/$name-train.log"; return 1; }
  manifest_write "$ART/$name.pjtw" "ENDGAME=ON KMOB=${kmob:+ON} PHASE=$lo/$hi" "$DATA" >/dev/null
  MSE[$name]=$(grep -oE 'val/phase mse : .*' "$ART/$name-train.log" | grep -oE 'endgame=[0-9.]+' | head -1 | cut -d= -f2)
  # DECISION metric 1 : critical-win-preservation (conversion exacte)
  "$J" --egdb-mtc-regret "$ART/$name.pjtw" "$WLD" "$MTC" 5000 1024 7 >"$ART/$name-regret.log" 2>&1
  CRIT[$name]=$(grep -oE 'CRITICAL: [0-9]+/[0-9]+ = [0-9.]+%' "$ART/$name-regret.log" | grep -oE '[0-9.]+%' | head -1)
  # DECISION metric 2 : Elo vs hc
  ELO[$name]=$(elo "$ART/$name" "$J")
  echo "  $name : critical-win-preservation=${CRIT[$name]:-NA}  Elo_vs_hc=${ELO[$name]:-NA}  (mse=${MSE[$name]:-NA})"
}

echo "=== ctrl  (endg, rampe 0/40) ==="          ; variant ctrl  ""                        0  40
echo "=== kmob  (+king_mob) ==="                 ; variant kmob  "-DJASS_KING_MOBILITY=ON" 0  40
echo "=== phase (+rampe 8/18) ==="               ; variant phase ""                        8  18
echo "=== combo (+king_mob +rampe 8/18) ==="     ; variant combo "-DJASS_KING_MOBILITY=ON" 8  18

echo; echo "=========================================================="
echo "   cpx62-0317 — RUN COMBINÉ (le vrai test, données enrichies)"
echo "   baseline conversion à battre (0315/endg) : critical-win-preservation = 43%"
echo "----------------------------------------------------------"
printf "  %-6s critical=%-7s Elo=%-12s (mse=%s)\n" ctrl  "${CRIT[ctrl]:-NA}"  "${ELO[ctrl]:-NA}"  "${MSE[ctrl]:-NA}"
printf "  %-6s critical=%-7s Elo=%-12s (mse=%s)\n" kmob  "${CRIT[kmob]:-NA}"  "${ELO[kmob]:-NA}"  "${MSE[kmob]:-NA}"
printf "  %-6s critical=%-7s Elo=%-12s (mse=%s)\n" phase "${CRIT[phase]:-NA}" "${ELO[phase]:-NA}" "${MSE[phase]:-NA}"
printf "  %-6s critical=%-7s Elo=%-12s (mse=%s)\n" combo "${CRIT[combo]:-NA}" "${ELO[combo]:-NA}" "${MSE[combo]:-NA}"
echo "----------------------------------------------------------"
echo "  VERDICT (DECISION = critical + Elo, PAS mse) :"
echo "   combo critical > 43% ET Elo ≈/> ctrl → les leviers CONVERTISSENT mieux → flywheel viable,"
echo "      on monte un loop multi-gen (combo + self-play MTC-in-search) et on cherche gen N+1 > gen N."
echo "   combo ≈ ctrl sur critical → les features/équilibre ne suffisent pas → c'est données/recherche"
echo "      (cf audit features Scan) → pivot diagnostic, pas plus de features."
echo "=========================================================="
