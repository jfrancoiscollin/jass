#!/usr/bin/env bash
# id: cpx62-0320-optimal-run
# description: LE GROS RUN — conditions optimales, un seul test décisif (fini les petits tests). (1) Génère
# ~4M de self-play HAUTE QUALITÉ : joué par notre MEILLEUR éval (0318 ctrl, +253) via --nnue, + egdb-perfect
# (terminate-at-TB, labels finale exacts) + MTC-in-search + depth-ramp. (2) Fusionne avec les 6.7M enrichis
# (0314) → ~10.7M. (3) Entraîne l'éval FULL-FEATURE (endg+king_mob+drawish) en MINIBATCH. (4) Teste DIRECT
# vs Scan à mt1.5 (le vrai juge) + Elo. Tout est gardé sur disque (dataset, pjtw) pour re-match si besoin.
# expected_duration: ~9-11 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-720}"
source jobs/lib/preflight.sh
source jobs/lib/manifest.sh
ART="/root/jass/jobs/results/cpx62-0320-optimal-run/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
WLD=/root/egdb_extracted/app; MTC=/root/egdb_mtc/app
ENR=/root/jass/jobs/results/cpx62-0314-endgame-data-aug/artefacts.src/enriched-cumulative.jnnw
CTRL=/root/jass/jobs/results/cpx62-0318-combined-run/artefacts.src/ctrl.pjtw   # meilleur éval (+253), 110 extras
SCAN_BIN=/root/jass-scan/scan_linux
ls "$WLD"/db2.idx1 >/dev/null 2>&1 || { echo "ABORT: WLD absente"; exit 4; }
ls "$MTC" >/dev/null 2>&1 || { echo "ABORT: MTC absente"; exit 4; }
[ -f "$ENR" ]  || { echo "ABORT: dataset enrichi 0314 absent"; exit 4; }
[ -f "$CTRL" ] || { echo "ABORT: ctrl.pjtw de 0318 absent (meilleur éval)"; exit 4; }

EVAL_DEPTH=6; PLAY_DEPTH=8; RAMP="late-mid=12,endgame=16"; FRESH=4000000; MB=1000000
preflight_build 2
preflight_note "self-play HQ ${FRESH} (--nnue fort + egdb + MTC + ramp, ×$NCPU)" 300
preflight_train 10700000 1
preflight_match $((3*9*2)) 1.5 160
preflight_note "Elo hc" 8
preflight_check
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }

# --- (0) deux builds : GEN (endg-110, match ctrl.pjtw) + FULL (114, train+match) ---
echo "=== builds ==="
rm -rf build-gen build-full
cmake -S . -B build-gen  -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_DRAWISH_SCALING=ON >"$ART/cmake-gen.log" 2>&1
cmake -S . -B build-full -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_DRAWISH_SCALING=ON >"$ART/cmake-full.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake-gen.log" && grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake-full.log" || { echo "ABORT: egdb off"; exit 5; }
cmake --build build-gen  -j"$(mem_safe_jobs)" --target jass >"$ART/build-gen.log"  2>&1 || { echo "GEN BUILD FAIL";  tail -20 "$ART/build-gen.log";  exit 6; }
cmake --build build-full -j"$(mem_safe_jobs)" --target jass >"$ART/build-full.log" 2>&1 || { echo "FULL BUILD FAIL"; tail -20 "$ART/build-full.log"; exit 6; }
GENJ=/root/jass/build-gen/jass; FULLJ=/root/jass/build-full/jass

# --- (1) génération HAUTE QUALITÉ (meilleur éval + egdb-perfect + MTC-in-search + ramp), shardée ---
echo "=== (1) self-play HQ ${FRESH} (joué par ctrl.pjtw +253, egdb+MTC+ramp) ==="
PER=$(( (FRESH + NCPU - 1) / NCPU ))
for s in $(seq 1 "$NCPU"); do
  JASS_EGDB_PATH="$WLD" JASS_EGDB_MTC_PATH="$MTC" JASS_EGDB_CACHE_MB=256 \
    "$GENJ" --gen-data-wdl "$PER" "$ART/hq-$s.jnnw" "$EVAL_DEPTH" "$PLAY_DEPTH" 200 $((70000 + RANDOM*s + s)) \
      --nnue "$CTRL" --play-depth-by-phase "$RAMP" --label-depth-by-phase "$RAMP" >"$ART/hq-$s.log" 2>&1 &
done
wait
echo "shards HQ: $(ls "$ART"/hq-*.jnnw 2>/dev/null | wc -l)/$NCPU"

# --- (2) fusion HQ + enrichi 0314 → big.jnnw ---
python3 - "$ART" "$ENR" <<'PY'
import sys,glob,struct
art,enr=sys.argv[1],sys.argv[2]; REC=38
files=sorted(glob.glob(art+'/hq-*.jnnw'))+[enr]
out=open(art+'/big.jnnw','wb'); tot=0; out.write(b'JNNW'+struct.pack('<I',0))
for f in files:
    try: b=open(f,'rb').read()
    except FileNotFoundError: print("manquant",f); continue
    n=struct.unpack('<I',b[4:8])[0]; out.write(b[8:8+n*REC]); tot+=n
out.seek(4); out.write(struct.pack('<I',tot)); out.close()
print("BIG",tot,"records →",art+'/big.jnnw')
PY
echo "=== stats du gros dataset ==="
python3 pattern_jass/tools/jnnw_stats.py "$ART/big.jnnw" 2>/dev/null | sed -n '1,18p'
rm -f "$ART"/hq-*.jnnw   # libère l'espace (shards fusionnés)

# --- (3) MINIBATCH train, éval FULL-FEATURE ---
echo "=== (3) minibatch train (full-feature, mb=${MB}) ==="
"$FULLJ" --dump-eval-features "$ART/big.jnnw" "$ART/big.feat" >"$ART/dump.log" 2>&1
python3 pattern_jass/tools/train.py --data "$ART/big.jnnw" --scan-eval --eval-features-file "$ART/big.feat" \
  --loss logistic --l2 3e-4 --max-iter 200 --scale 1000 --prune --minibatch "$MB" --full-fold \
  --out "$ART/big.pjtw" >"$ART/big-train.log" 2>&1
[ -f "$ART/big.pjtw" ] || { echo "TRAIN FAIL"; tail -12 "$ART/big-train.log"; exit 7; }
manifest_write "$ART/big.pjtw" "ENDGAME=ON KMOB=ON DRAWISH=ON DATA=HQ4M+enr6.7M MB=$MB" "$ART/big.jnnw" >/dev/null
echo "  trained: $(ls -la "$ART/big.pjtw" | awk '{print $5}') octets"

# --- (4) LE TEST : vs Scan à mt1.5 (+ Elo hc) ---
echo "=== (4) vs SCAN @ mt1.5 (le juge) ==="
EL=$("$FULLJ" --benchmark-scan-eval "$ART/big.pjtw" hc 9 60 "$NCPU" 0 2>"$ART/elo.log"; grep -oE 'SCAN_EVAL=[0-9]+' "$ART/elo.log"|tail -1)
W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$ART/elo.log"|tail -1|cut -d= -f2); L=$(grep -oE 'NNUE=[0-9]+' "$ART/elo.log"|tail -1|cut -d= -f2); D=$(grep -oE 'Draws=[0-9]+' "$ART/elo.log"|tail -1|cut -d= -f2)
ELO_HC=$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2)
if [ -x "$SCAN_BIN" ]; then
  python3 tools/calibrate_vs_scan.py --jass "$FULLJ" --scan "$SCAN_BIN" --jass-pattern "$ART/big.pjtw" \
      --scan-bb-size 0 --movetime 1.5 --pairs 3 --max-plies 160 --allow-long-movetime >"$ART/scan-mt15.log" 2>&1 || true
fi

echo; echo "=========================================================="
echo "   cpx62-0320 — GROS RUN OPTIMAL (HQ data + minibatch + mt1.5)"
echo "----------------------------------------------------------"
echo "  dataset   : $(python3 pattern_jass/tools/jnnw_stats.py "$ART/big.jnnw" 2>/dev/null | grep -E 'file records|<=7p' | tr '\n' ' ')"
echo "  Elo vs hc : ${ELO_HC:-NA}"
echo "  vs SCAN @ mt1.5 : $(grep -E 'score rate|ELO estimate' "$ART/scan-mt15.log" 2>/dev/null | tr '\n' ' ')"
echo "----------------------------------------------------------"
echo "  Réf : à mt0.5 on était à 0/54 (−800). Si mt1.5 + HQ data ferme l'écart → recherche/données"
echo "     payaient ; sinon (toujours ~0) → on a bordé features+données+recherche, le linéaire plafonne."
echo "=========================================================="
