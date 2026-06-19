#!/usr/bin/env bash
# id: cpx62-0357-logistic-wdl-strong
# description: B-PROPRE — la méthode de Scan sur de la VRAIE data forte. evalB = WDL LOGISTIQUE (objectif exact
# de Scan) sur le corpus 0328 (1.19M, parties FORTES Scan-self-play, WDL) ≈ le régime d'entraînement de Scan
# (il tune sur ses propres parties en logistique WDL). vs eval0 (notre distillation de score). Juge : evalB vs
# eval0 EN DIRECT (sensible) + vs Scan. evalB > eval0 → la méthode/recette de Scan bat notre distillation.
# expected_duration: ~2 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-180}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0357-logistic-wdl-strong/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
OLDSCAN=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw   # pour eval0 (notre champion)
CORPUS=/root/jass/jobs/results/ccx33-0328-scan-selfplay-corpus/artefacts/scan-selfplay-corpus.jnnw  # data forte WDL
SCAN_BIN=/root/jass-scan/scan_linux
NPOS=400000
[ -f "$OLDSCAN" ] && [ -f "$CORPUS" ] || { echo "ABORT: data manquante"; exit 4; }

preflight_build 1; preflight_train 240000 1; preflight_train "$NPOS" 1; preflight_note "evalB vs eval0 + vs Scan" 60; preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }

echo "=== build ==="
B=build-full; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -8 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"

echo "=== eval0 : notre champion (distill score sur old-scan) ==="
"$JASS" --dump-eval-features "$OLDSCAN" "$ART/f0" >/dev/null 2>&1
python3 pattern_jass/tools/train.py --data "$OLDSCAN" --scan-eval --eval-features-file "$ART/f0" \
  --target score --score-drop 3000 --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 --prune --lowmem --full-fold \
  --out "$ART/eval0.pjtw" >"$ART/e0.log" 2>&1
[ -f "$ART/eval0.pjtw" ] || { echo "TRAIN0 FAIL"; tail -8 "$ART/e0.log"; exit 9; }

echo "=== sous-échantillon corpus 0328 → ${NPOS} (data forte WDL) ==="
python3 - "$CORPUS" "$ART/strong.jnnw" "$NPOS" <<'PY'
import sys,struct
src,out,n=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
b=open(src,'rb').read(); tot=struct.unpack('<I',b[4:8])[0]; body=b[8:]
n=min(n,tot); st=max(1,tot//n); r=bytearray(); k=0
for i in range(0,tot,st):
    r+=body[i*REC:(i+1)*REC]; k+=1
    if k>=n: break
open(out,'wb').write(b'JNNW'+struct.pack('<I',k)+bytes(r)); print('strong',k,'/',tot)
PY
echo "=== evalB : WDL LOGISTIQUE (méthode Scan) sur la data forte ==="
"$JASS" --dump-eval-features "$ART/strong.jnnw" "$ART/fB" >/dev/null 2>&1
python3 pattern_jass/tools/train.py --data "$ART/strong.jnnw" --scan-eval --eval-features-file "$ART/fB" \
  --target wdl --loss logistic --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 --prune --lowmem --full-fold \
  --out "$ART/evalB.pjtw" >"$ART/eB.log" 2>&1
[ -f "$ART/evalB.pjtw" ] || { echo "TRAINB FAIL"; tail -8 "$ART/eB.log"; exit 9; }

rate(){ grep -E 'score rate|A score rate' "$1" | grep -oE '0?\.[0-9]+|[01]\.[0-9]+' | head -1; }
echo "=== evalB vs eval0 EN DIRECT (depth9, 144 parties) ==="
"$JASS" --benchmark-nnue-vs-nnue "$ART/evalB.pjtw" "$ART/eval0.pjtw" 9 8 1 0 >"$ART/direct.log" 2>&1 || true
DIR=$(grep -E 'A score rate' "$ART/direct.log" | grep -oE '[0-9.]+' | head -1)
echo "=== vs Scan depth-égale d9 (8 pairs) ==="
[ -x "$SCAN_BIN" ] && {
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/eval0.pjtw" --scan-bb-size 0 --jass-depth 9 --scan-depth 9 --pairs 8 --max-plies 160 >"$ART/vs0.log" 2>&1 || true
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/evalB.pjtw" --scan-bb-size 0 --jass-depth 9 --scan-depth 9 --pairs 8 --max-plies 160 >"$ART/vsB.log" 2>&1 || true; }
echo; echo "=========================================================="
echo "   cpx62-0357 — B-PROPRE : WDL logistique sur data forte (méthode Scan)"
echo "   evalB vs eval0 DIRECT : ${DIR:-NA}   (>0.55 = la méthode Scan gagne)"
echo "   vs Scan d9 : eval0=$(rate "$ART/vs0.log")  evalB=$(rate "$ART/vsB.log")"
echo "=========================================================="
