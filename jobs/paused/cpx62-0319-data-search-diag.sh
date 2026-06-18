#!/usr/bin/env bash
# id: cpx62-0319-data-search-diag
# description: DIAGNOSTIC données-vs-recherche (0318 a montré : features ≠ levier → c'est données/recherche).
# Garde TOUT le set de features (endg + king_mob + drawish, gated). (A) Courbe d'échelle de DONNÉES :
# train full-feature sur 1M/2M/6.7M du dataset enrichi 0314, Elo vs hc → grimpe = affamé de données ;
# plafonne = pas le volume. (B) Sonde RECHERCHE : l'éval 6.7M vs Scan à mt0.5 vs mt1.5 → s'adoucit =
# recherche/temps ; toujours ~0 = éval-limité. Manifest par artefact. Pré-flight borné.
# expected_duration: ~2h30
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-240}"
source jobs/lib/preflight.sh
source jobs/lib/manifest.sh
ART="/root/jass/jobs/results/cpx62-0319-data-search-diag/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
WLD=/root/egdb_extracted/app; MTC=/root/egdb_mtc/app
DATA=/root/jass/jobs/results/cpx62-0314-endgame-data-aug/artefacts.src/enriched-cumulative.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
ls "$WLD"/db2.idx1 >/dev/null 2>&1 || { echo "ABORT: WLD absente"; exit 4; }
[ -f "$DATA" ] || { echo "ABORT: dataset 0314 absent"; exit 4; }

preflight_build 1
preflight_train 1000000 1; preflight_train 2000000 1; preflight_train 6700000 1
preflight_note "3× Elo hc" 15
preflight_match $((1*9*2)) 0.5 120; preflight_match $((1*9*2)) 1.5 120
preflight_check
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }

# --- full-feature build (TOUTES les features gardées) ---
rm -rf build-ff
cmake -S . -B build-ff -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_DRAWISH_SCALING=ON >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; exit 5; }
cmake --build build-ff -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 6; }
JASS=/root/jass/build-ff/jass
echo "full-feature build : endg + king_mob + drawish-scaling (toutes features actives)"

elo(){ local lg="$1-elo.log"; "$JASS" --benchmark-scan-eval "$1.pjtw" hc 9 60 "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2); local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2; }

# === (A) courbe d'échelle de données ===
declare -A ELO
train_n(){ # <N>
  local N="$1" name="d$1"
  python3 -c "
import struct,sys
src,n,out=sys.argv[1],int(sys.argv[2]),sys.argv[3]
b=open(src,'rb').read(); REC=38; tot=struct.unpack('<I',b[4:8])[0]; n=min(n,tot)
open(out,'wb').write(b'JNNW'+struct.pack('<I',n)+b[8:8+n*REC])
print('subset',n,'/',tot)" "$DATA" "$N" "$ART/$name.jnnw"
  "$JASS" --dump-eval-features "$ART/$name.jnnw" "$ART/$name.feat" >/dev/null 2>&1
  python3 pattern_jass/tools/train.py --data "$ART/$name.jnnw" --scan-eval --eval-features-file "$ART/$name.feat" \
    --loss logistic --l2 3e-4 --max-iter 200 --scale 1000 --prune --lowmem --full-fold \
    --out "$ART/$name.pjtw" >"$ART/$name-train.log" 2>&1
  [ -f "$ART/$name.pjtw" ] || { echo "$name TRAIN FAIL"; tail -6 "$ART/$name-train.log"; return 1; }
  manifest_write "$ART/$name.pjtw" "ENDGAME=ON KMOB=ON DRAWISH=ON N=$N" "$ART/$name.jnnw" >/dev/null
  ELO[$N]=$(elo "$ART/$name")
  echo "  N=$N → Elo_vs_hc=${ELO[$N]}"
}
echo "=== (A) DATA-SCALING (full-feature) ==="
train_n 1000000
train_n 2000000
train_n 6700000

# === (B) sonde recherche : éval 6.7M vs Scan à mt0.5 vs mt1.5 ===
probe(){ # <movetime> <flag>
  local mt="$1" extra="$2" lg="$ART/scan-mt$1.log"
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/d6700000.pjtw" \
      --scan-bb-size 0 --movetime "$mt" --pairs 1 --max-plies 120 $extra >"$lg" 2>&1 || true
  grep -E 'score rate|ELO estimate' "$lg" | tr '\n' ' '; echo
}
echo "=== (B) RECHERCHE vs Scan (éval 6.7M) ==="
[ -x "$SCAN_BIN" ] && { echo "  mt0.5 : $(probe 0.5 '')"; echo "  mt1.5 : $(probe 1.5 --allow-long-movetime)"; } || echo "  (Scan absent — sonde sautée)"

echo; echo "=========================================================="
echo "   cpx62-0319 — DIAGNOSTIC données-vs-recherche (toutes features)"
echo "----------------------------------------------------------"
for N in 1000000 2000000 6700000; do printf "  data N=%-8s Elo_vs_hc=%s\n" "$N" "${ELO[$N]:-NA}"; done
echo "----------------------------------------------------------"
echo "  (A) Elo grimpe 1M→6.7M → AFFAMÉ DE DONNÉES (le flywheel peut monter avec + de données/qualité)."
echo "      Elo plafonne → pas le volume → c'est la QUALITÉ des données ou la recherche."
echo "  (B) score vs Scan mt0.5→mt1.5 monte → RECHERCHE/temps. Reste ~0 → ÉVAL-limité (data quality)."
echo "=========================================================="
