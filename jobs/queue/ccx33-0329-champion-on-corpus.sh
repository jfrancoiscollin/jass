#!/usr/bin/env bash
# id: ccx33-0329-champion-on-corpus
# description: TENTATIVE CHAMPION sur la BONNE distribution (le corpus Scan-self-play 0328, 1.19M). C'est la
# run vers laquelle tout le programme converge si le covariate-shift est le verrou : distiller Scan-score sur
# des positions que Scan TRAVERSE vraiment (pas le self-play faible de jass), archi FULL Scan-alignée, jugé
# vs Scan mt1.5 sur 36 parties — directement comparable au plafond historique 0/54. Tourne EN PARALLÈLE de
# cpx62-0327 (la preuve contrôlée) : 0327 prouve le MÉCANISME, 0329 vise le SCALP à l'échelle.
# expected_duration: ~11-13 h (relabel Scan d9 dominant, 8 cœurs)
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-840}"
source jobs/lib/preflight.sh
source jobs/lib/manifest.sh
source jobs/lib/relabel.sh
ART="/root/jass/jobs/results/ccx33-0329-champion-on-corpus/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

CORPUS=/root/jass/jobs/results/ccx33-0328-scan-selfplay-corpus/artefacts/scan-selfplay-corpus.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
SCAN_DEPTH=9; NPOS=500000
[ -f "$CORPUS" ] || { echo "ABORT: corpus 0328 absent ($CORPUS)"; exit 4; }

preflight_build 1
preflight_note "relabel Scan ${NPOS} @ d${SCAN_DEPTH} (×$NCPU, dominant)" 540
preflight_train "$NPOS" 1
preflight_match $((2*9*2)) 1.5 160
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan indisponible"; exit 5; }

echo "=== build jass FULL Scan-alignée (referee + éval), drawish OFF ==="
B=build-full; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
      >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; tail -8 "$ART/cmake.log"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -12 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"

# --- sous-échantillonne le corpus à NPOS (stride = garde toutes les phases proportionnellement) ---
echo "=== sous-échantillon corpus → ${NPOS} ==="
python3 - "$CORPUS" "$ART/sub.jnnw" "$NPOS" <<'PY'
import sys,struct
src,out,npos=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
b=open(src,'rb').read(); tot=struct.unpack('<I',b[4:8])[0]; body=b[8:]
npos=min(npos,tot); stride=max(1,tot//npos); recs=bytearray(); n=0
for i in range(0,tot,stride):
    recs+=body[i*REC:(i+1)*REC]; n+=1
    if n>=npos: break
open(out,'wb').write(b'JNNW'+struct.pack('<I',n)+bytes(recs)); print('  sub',n,'/',tot)
PY

# --- relabel Scan depth 9 (distillation = cible Scan-score), shardé ×NCPU ---
echo "=== relabel Scan depth ${SCAN_DEPTH} (×$NCPU) ==="
relabel_scan_sharded "$ART/sub.jnnw" "$ART/scan.jnnw" "$SCAN_BIN" "$SCAN_DEPTH" "$NCPU"
[ -f "$ART/scan.jnnw" ] || { echo "RELABEL FAIL"; exit 8; }
echo "  relabelisé: $(python3 -c "import struct;print(struct.unpack('<I',open('$ART/scan.jnnw','rb').read(8)[4:8])[0])") positions"

# --- train FULL Scan-alignée + tempo-stage (distillation Scan-score) ---
echo "=== train champion (FULL-aligned, --target score, --tempo-stage) ==="
"$JASS" --dump-eval-features "$ART/scan.jnnw" "$ART/champ.feat" >"$ART/dump.log" 2>&1
python3 pattern_jass/tools/train.py --data "$ART/scan.jnnw" --scan-eval --eval-features-file "$ART/champ.feat" \
  --target score --score-drop 3000 --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 \
  --prune --lowmem --full-fold --out "$ART/champ.pjtw" >"$ART/train.log" 2>&1
[ -f "$ART/champ.pjtw" ] || { echo "TRAIN FAIL"; tail -10 "$ART/train.log"; exit 9; }
manifest_write "$ART/champ.pjtw" "DISTILL=Scan-d${SCAN_DEPTH} FULL-aligned SRC=corpus0328-selfplay N=${NPOS}" "$ART/scan.jnnw" >/dev/null

# --- jugement : Elo vs hc + vs Scan mt1.5 (36 parties, comparable au 0/54 historique) ---
echo "=== Elo vs hc ==="
"$JASS" --benchmark-scan-eval "$ART/champ.pjtw" hc 9 60 "$NCPU" 0 >"$ART/elo.log" 2>&1
W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$ART/elo.log"|tail -1|cut -d= -f2); L=$(grep -oE 'NNUE=[0-9]+' "$ART/elo.log"|tail -1|cut -d= -f2); D=$(grep -oE 'Draws=[0-9]+' "$ART/elo.log"|tail -1|cut -d= -f2)
ELOHC=$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2)
echo "=== vs Scan mt1.5 (36 parties) ==="
python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/champ.pjtw" \
    --scan-bb-size 0 --movetime 1.5 --pairs 2 --max-plies 160 --allow-long-movetime >"$ART/vs-scan.log" 2>&1 || true
RATE=$(grep -E 'score rate' "$ART/vs-scan.log" | grep -oE '[0-9.]+ \([0-9./]+\)' | head -1)

echo; echo "=========================================================="
echo "   ccx33-0329 — CHAMPION sur corpus Scan-self-play (BONNE distribution)"
echo "----------------------------------------------------------"
echo "   ${NPOS} positions (sous-éch. du 1.19M 0328) · relabel Scan d${SCAN_DEPTH} · archi FULL Scan-alignée"
echo "   Elo_vs_hc      = ${ELOHC:-NA}"
echo "   vs_Scan_mt1.5  = ${RATE:-NA}    (plafond historique = 0/54)"
echo "----------------------------------------------------------"
echo "   RATE nettement > 0 → la BONNE distribution décolle (covariate-shift = le verrou)."
echo "=========================================================="
