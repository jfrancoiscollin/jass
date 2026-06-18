#!/usr/bin/env bash
# id: ccx33-0328-scan-selfplay-corpus
# description: Construit un CORPUS réutilisable de positions FORTES (Scan joue les deux côtés) — GÉNÉRATION
# SEULE, aucun jugement (donc ni « trop long » ni « sur de mauvaises positions »). Sert de pool de seeds /
# d'entraînement à la prochaine run décisive une fois 0327 confirmé. Shards DISJOINTS (Scan @ depth fixe est
# déterministe → seeds partagés = parties identiques) via --nshards/--shard. Sortie committée (≤95MB).
# expected_duration: ~3-4 h (génération Scan self-play depth 8, 8 cœurs)
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-360}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0328-scan-selfplay-corpus/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

SEEDS=/root/jass/jobs/results/ccx33-0313-endgame-data-gen/artefacts.src/endgame-cumulative.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
GEN_DEPTH=8; GAMES=8000; MAXPLIES=160; MINPIECES=40
[ -f "$SEEDS" ] || { echo "ABORT: dataset 0313 (seeds) absent ($SEEDS)"; exit 4; }

preflight_build 1
preflight_note "Scan self-play ${GAMES} parties @ d${GEN_DEPTH} (×$NCPU)" 240
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan indisponible"; exit 5; }

# jass FULL Scan-alignée sert juste de referee neutre pour le self-play.
echo "=== build jass (referee egdb) ==="
B=build-full; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
      >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; tail -8 "$ART/cmake.log"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -12 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"

echo "=== Scan self-play (depth ${GEN_DEPTH}, ${GAMES} parties, ×${NCPU} shards DISJOINTS) ==="
PERG=$(( (GAMES + NCPU - 1) / NCPU ))
for s in $(seq 0 $((NCPU-1))); do
  python3 tools/scan_selfplay_gen.py --scan "$SCAN_BIN" --jass "$JASS" \
    --seeds "$SEEDS" --out "$ART/.sp-$s.jnnw" --games "$PERG" --depth "$GEN_DEPTH" \
    --max-plies "$MAXPLIES" --min-pieces "$MINPIECES" --sample-every 1 \
    --seed 777 --nshards "$NCPU" --shard "$s" >"$ART/.sp-$s.log" 2>&1 &
done
wait
python3 - "$ART/scan-selfplay-corpus.jnnw" "$ART" "$NCPU" <<'PY'
import sys,struct,os
out,d,nc=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
o=open(out,'wb'); tot=0; o.write(b'JNNW'+struct.pack('<I',0))
for s in range(nc):
    f=os.path.join(d,f'.sp-{s}.jnnw')
    if not os.path.exists(f):
        print('  [selfplay] shard',s,'manquant (voir .sp-%d.log)'%s); continue
    b=open(f,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; o.write(b[8:8+n*REC]); tot+=n
o.seek(4); o.write(struct.pack('<I',tot)); o.close()
print(f'  [selfplay] CORPUS {tot} positions -> {out} ({tot*38/1e6:.1f} MB)')
PY
for s in $(seq 0 $((NCPU-1))); do rm -f "$ART/.sp-$s.jnnw"; done
OUT="$ART/scan-selfplay-corpus.jnnw"
[ -f "$OUT" ] || { echo "ABORT: corpus vide"; tail -20 "$ART"/.sp-0.log 2>/dev/null; exit 7; }
TOT=$(python3 -c "import struct;print(struct.unpack('<I',open('$OUT','rb').read(8)[4:8])[0])")
echo "  corpus : $TOT positions ($(python3 -c "print(round($TOT*38/1e6,1))") MB)"
[ "$TOT" -gt 50000 ] || { echo "ABORT: corpus trop maigre ($TOT)"; tail -20 "$ART"/.sp-0.log 2>/dev/null; exit 7; }
python3 pattern_jass/tools/jnnw_stats.py "$OUT" 2>/dev/null | sed -n '1,18p' || true

echo; echo "=========================================================="
echo "   ccx33-0328 — CORPUS Scan self-play (distribution forte, réutilisable)"
echo "   $TOT positions committées → seeds/train de la prochaine run décisive."
echo "=========================================================="
