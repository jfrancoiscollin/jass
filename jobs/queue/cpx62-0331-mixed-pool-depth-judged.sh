#!/usr/bin/env bash
# id: cpx62-0331-mixed-pool-depth-judged
# description: LEVIER ÉVAL sous la bonne méthodo. Pool MIXTE (Scan-self-play DIVERS via --weak-depth = qualité
# décisive + jass-self-play 0314 = diversité), distillé Scan d9, jugé à PROFONDEUR ÉGALE (le nouveau standard,
# pas le temps égal). Question : l'éval passe-t-elle SOUS les ~2 plies de gap mesurés en 0330 ? Baseline 0330
# (même éval, distrib 0314 seule) : C2 depth9=0.056, C3 jass11/scan9=0.333. Si le pool mixte fait MIEUX à
# depth égale → le levier éval bouge enfin (data correcte + méthodo correcte).
# expected_duration: ~3-4 h (gen + relabel ; les matchs depth-fixe sont quasi-gratuits)
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-300}"
source jobs/lib/preflight.sh
source jobs/lib/manifest.sh
source jobs/lib/relabel.sh
ART="/root/jass/jobs/results/cpx62-0331-mixed-pool-depth-judged/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

ENR=/root/jass/jobs/results/cpx62-0314-endgame-data-aug/artefacts.src/enriched-cumulative.jnnw   # jass self-play + coverage (diversité, + seeds)
SCAN_BIN=/root/jass-scan/scan_linux
SCAN_DEPTH=9; GEN_DEPTH=9; WEAK_DEPTH=5; GEN_GAMES=6000; NPOS=500000
[ -f "$ENR" ] || { echo "ABORT: dataset 0314 (diversité+seeds) absent ($ENR)"; exit 4; }

preflight_build 1
preflight_note "Scan self-play DIVERS ${GEN_GAMES} parties (×$NCPU)" 70
preflight_note "relabel Scan ${NPOS} @ d${SCAN_DEPTH} (×$NCPU)" 90
preflight_train "$NPOS" 1
preflight_note "benchmarks depth-fixe (quasi-gratuit)" 20
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan indisponible"; exit 5; }

echo "=== build jass FULL Scan-alignée ==="
B=build-full; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
      >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; tail -8 "$ART/cmake.log"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -12 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"
cnt(){ python3 -c "import struct;print(struct.unpack('<I',open('$1','rb').read(8)[4:8])[0])"; }

# --- (1) Scan self-play DIVERS (--weak-depth : fort d9 vs faible d5, randomisé/partie → parties décisives) ---
echo "=== Scan self-play DIVERS (fort d${GEN_DEPTH} vs faible d${WEAK_DEPTH}, ×${NCPU} shards disjoints) ==="
PERG=$(( (GEN_GAMES + NCPU - 1) / NCPU ))
for s in $(seq 0 $((NCPU-1))); do
  python3 tools/scan_selfplay_gen.py --scan "$SCAN_BIN" --jass "$JASS" \
    --seeds "$ENR" --out "$ART/.sp-$s.jnnw" --games "$PERG" --depth "$GEN_DEPTH" \
    --weak-depth "$WEAK_DEPTH" --depth-jitter 2 --max-plies 160 --min-pieces 40 \
    --sample-every 1 --seed 4242 --nshards "$NCPU" --shard "$s" >"$ART/.sp-$s.log" 2>&1 &
done
wait
python3 - "$ART/diverse-scan.jnnw" "$ART" "$NCPU" <<'PY'
import sys,struct,os
out,d,nc=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
o=open(out,'wb'); tot=0; o.write(b'JNNW'+struct.pack('<I',0))
for s in range(nc):
    f=os.path.join(d,f'.sp-{s}.jnnw')
    if not os.path.exists(f): print('  shard',s,'manquant'); continue
    b=open(f,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; o.write(b[8:8+n*REC]); tot+=n
o.seek(4); o.write(struct.pack('<I',tot)); o.close(); print('  diverse-scan',tot,'positions')
PY
for s in $(seq 0 $((NCPU-1))); do rm -f "$ART/.sp-$s.jnnw"; done
[ -f "$ART/diverse-scan.jnnw" ] || { echo "ABORT: gen vide"; tail -20 "$ART"/.sp-0.log 2>/dev/null; exit 7; }
DS_N=$(cnt "$ART/diverse-scan.jnnw"); echo "  diverse-scan : $DS_N positions"
[ "$DS_N" -gt 50000 ] || { echo "ABORT: diverse-scan maigre ($DS_N)"; tail -20 "$ART"/.sp-0.log; exit 7; }

# --- (2) POOL MIXTE : 60% Scan-divers (qualité décisive) + 40% 0314 (diversité jass) ---
echo "=== pool mixte (60% Scan-divers + 40% jass-0314) → ${NPOS} ==="
python3 tools/jnnw_mix.py --out "$ART/pool.jnnw" --total "$NPOS" \
    --src "$ART/diverse-scan.jnnw:0.60" --src "$ENR:0.40" 2>&1 | sed 's/^/  /'
[ -f "$ART/pool.jnnw" ] || { echo "ABORT: mix vide"; exit 7; }

# --- (3) relabel Scan d9 (distillation) ---
echo "=== relabel Scan d${SCAN_DEPTH} (×$NCPU) ==="
relabel_scan_sharded "$ART/pool.jnnw" "$ART/scan.jnnw" "$SCAN_BIN" "$SCAN_DEPTH" "$NCPU"
[ -f "$ART/scan.jnnw" ] || { echo "RELABEL FAIL"; exit 8; }
echo "  relabelisé: $(cnt "$ART/scan.jnnw") positions"

# --- (4) train FULL-alignée + tempo-stage ---
echo "=== train (FULL-aligned, --target score, --tempo-stage) ==="
"$JASS" --dump-eval-features "$ART/scan.jnnw" "$ART/m.feat" >"$ART/dump.log" 2>&1
python3 pattern_jass/tools/train.py --data "$ART/scan.jnnw" --scan-eval --eval-features-file "$ART/m.feat" \
  --target score --score-drop 3000 --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 \
  --prune --lowmem --full-fold --out "$ART/mixed.pjtw" >"$ART/train.log" 2>&1
[ -f "$ART/mixed.pjtw" ] || { echo "TRAIN FAIL"; tail -10 "$ART/train.log"; exit 9; }
manifest_write "$ART/mixed.pjtw" "DISTILL=Scan-d${SCAN_DEPTH} POOL=60scan-divers+40jass FULL-aligned" "$ART/scan.jnnw" >/dev/null

# --- (5) JUGEMENT au STANDARD : profondeur égale + asym (méthodo permanente, PAS temps égal) ---
declare -A RATE ELO
judge(){ local name="$1"; shift
  local lg="$ART/j-$name.log"
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/mixed.pjtw" \
      --scan-bb-size 0 --pairs 2 --max-plies 160 "$@" >"$lg" 2>&1 || true
  RATE[$name]=$(grep -E 'score rate' "$lg" | grep -oE '0\.[0-9]+' | head -1)
  ELO[$name]=$(grep -E 'ELO estimate' "$lg" | grep -oE '\-?[0-9]+' | head -1)
  echo "  $name : rate=${RATE[$name]:-NA}  Elo=${ELO[$name]:-NA}"
}
echo "=== C2 depth=9 égale ===";              judge depth9     --depth 9
echo "=== C3 jass11 vs scan9 (+2) ===";       judge jass11sc9  --jass-depth 11 --scan-depth 9
echo "=== C3b jass13 vs scan9 (+4) ===";      judge jass13sc9  --jass-depth 13 --scan-depth 9

echo; echo "=========================================================="
echo "   cpx62-0331 — POOL MIXTE jugé à PROFONDEUR ÉGALE (levier éval, méthodo permanente)"
echo "----------------------------------------------------------"
printf "  %-14s rate=%-7s Elo=%s\n" "C2 depth9"     "${RATE[depth9]:-NA}"    "${ELO[depth9]:-NA}"
printf "  %-14s rate=%-7s Elo=%s\n" "C3 jass11/sc9" "${RATE[jass11sc9]:-NA}" "${ELO[jass11sc9]:-NA}"
printf "  %-14s rate=%-7s Elo=%s\n" "C3b jass13/sc9" "${RATE[jass13sc9]:-NA}" "${ELO[jass13sc9]:-NA}"
echo "----------------------------------------------------------"
echo "   BASELINE 0330 (distrib 0314 seule) : C2=0.056  C3(jass11)=0.333"
echo "   C2/C3 mixte > baseline → le pool mixte rapproche l'éval (gap < ~2 plies). Sinon : éval stagne."
echo "=========================================================="
