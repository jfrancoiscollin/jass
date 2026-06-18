#!/usr/bin/env bash
# id: cpx62-0322-scan-distill
# description: PIVOT FALLBACK (documenté) — le teacher-free plafonne à 0/54 vs Scan, donc on DISTILLE Scan
# directement (ton idée : utiliser l'éval de Scan). (1) Échantillonne ~1.2M positions diverses du dataset
# enrichi 0314. (2) relabel_with_scan : Scan SCORE chaque position (depth-10, hub) → labels-maître. (3)
# Entraîne l'éval FULL-FEATURE sur le score de Scan (--target score = distillation). (4) Teste DIRECT vs
# Scan à mt1.5. Objectif réaliste : REJOINDRE Scan (la distillation plafonne à lui ; notre champion histo
# en venait). Si on s'en approche → ensuite fine-tune teacher-free par-dessus pour le dépasser.
# expected_duration: ~7-10 h (le relabel Scan domine)
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-720}"
source jobs/lib/preflight.sh
source jobs/lib/manifest.sh
ART="/root/jass/jobs/results/cpx62-0322-scan-distill/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
WLD=/root/egdb_extracted/app
ENR=/root/jass/jobs/results/cpx62-0314-endgame-data-aug/artefacts.src/enriched-cumulative.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
SCAN_DEPTH=10; NPOS=1200000
[ -f "$ENR" ] || { echo "ABORT: dataset enrichi 0314 absent"; exit 4; }

preflight_build 1
preflight_note "relabel Scan ${NPOS} @ depth${SCAN_DEPTH} (×$NCPU, dominant)" 360
preflight_train "$NPOS" 1
preflight_match $((3*9*2)) 1.5 160
preflight_check
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan binaire indisponible"; exit 5; }

# full-feature build (egdb pour le match ; endg+king_mob (drawish OFF : Scan score inclut déjà son drawish) gardés)
rm -rf build-ff
cmake -S . -B build-ff -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; exit 5; }
cmake --build build-ff -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 6; }
JASS=/root/jass/build-ff/jass

# --- (1) sous-échantillon DIVERS (stride) du dataset enrichi → ~NPOS positions ---
echo "=== (1) échantillon ${NPOS} positions diverses (stride) ==="
python3 - "$ENR" "$ART/sub.jnnw" "$NPOS" <<'PY'
import sys,struct
src,out,npos=sys.argv[1],sys.argv[2],int(sys.argv[3])
b=open(src,'rb').read(); REC=38; tot=struct.unpack('<I',b[4:8])[0]; body=b[8:]
stride=max(1,tot//npos)
recs=bytearray(); n=0
for i in range(0,tot,stride):
    recs+=body[i*REC:(i+1)*REC]; n+=1
    if n>=npos: break
open(out,'wb').write(b'JNNW'+struct.pack('<I',n)+bytes(recs))
print('sub',n,'/',tot,'(stride',stride,')')
PY

# --- (2) relabel Scan : Scan SCORE chaque position (distillation) ---
echo "=== (2) relabel par Scan (depth ${SCAN_DEPTH}, ×$NCPU threads) — phase dominante ==="
python3 tools/relabel_with_scan.py --in "$ART/sub.jnnw" --out "$ART/scan-labeled.jnnw" \
    --scan "$SCAN_BIN" --depth "$SCAN_DEPTH" --threads "$NCPU" --progress-every 20000 >"$ART/relabel.log" 2>&1
[ -f "$ART/scan-labeled.jnnw" ] || { echo "RELABEL FAIL"; tail -15 "$ART/relabel.log"; exit 7; }
tail -3 "$ART/relabel.log"
echo "  labelisé: $(python3 -c "import struct;print(struct.unpack('<I',open('$ART/scan-labeled.jnnw','rb').read(8)[4:8])[0])") positions (score=Scan)"

# --- (3) train full-feature sur le SCORE de Scan (distillation) ---
echo "=== (3) train distillation (--target score) ==="
"$JASS" --dump-eval-features "$ART/scan-labeled.jnnw" "$ART/feat" >"$ART/dump.log" 2>&1
python3 pattern_jass/tools/train.py --data "$ART/scan-labeled.jnnw" --scan-eval --eval-features-file "$ART/feat" \
  --target score --score-drop 3000 --l2 1e-4 --max-iter 300 --scale 1000 --prune --lowmem --full-fold \
  --out "$ART/distill.pjtw" >"$ART/distill-train.log" 2>&1
[ -f "$ART/distill.pjtw" ] || { echo "TRAIN FAIL"; tail -12 "$ART/distill-train.log"; exit 8; }
manifest_write "$ART/distill.pjtw" "ENDGAME=ON KMOB=ON DRAWISH=ON DISTILL=Scan-d${SCAN_DEPTH} N=${NPOS}" "$ART/scan-labeled.jnnw" >/dev/null

# --- (4) LE TEST : vs Scan mt1.5 + Elo hc ---
echo "=== (4) vs SCAN @ mt1.5 (le juge) ==="
"$JASS" --benchmark-scan-eval "$ART/distill.pjtw" hc 9 60 "$NCPU" 0 >"$ART/elo.log" 2>&1
W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$ART/elo.log"|tail -1|cut -d= -f2); L=$(grep -oE 'NNUE=[0-9]+' "$ART/elo.log"|tail -1|cut -d= -f2); D=$(grep -oE 'Draws=[0-9]+' "$ART/elo.log"|tail -1|cut -d= -f2)
ELO_HC=$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2)
python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/distill.pjtw" \
    --scan-bb-size 0 --movetime 1.5 --pairs 3 --max-plies 160 --allow-long-movetime >"$ART/scan-mt15.log" 2>&1 || true

echo; echo "=========================================================="
echo "   cpx62-0322 — DISTILLATION SCAN (full-feature, vs Scan mt1.5)"
echo "----------------------------------------------------------"
echo "  positions distillées : ${NPOS} @ Scan depth ${SCAN_DEPTH}"
echo "  Elo vs hc        : ${ELO_HC:-NA}"
echo "  vs SCAN @ mt1.5  : $(grep -E 'score rate|ELO estimate' "$ART/scan-mt15.log" 2>/dev/null | tr '\n' ' ')"
echo "----------------------------------------------------------"
echo "  Réf teacher-free : 0/54 (−800) à mt0.5. Distillation s'APPROCHE de Scan (score rate ≫ 0) →"
echo "     on a REJOINT le maître → ensuite fine-tune teacher-free par-dessus pour le dépasser."
echo "  Toujours ~0 → même en copiant Scan on n'y arrive pas → limite de classe/search → repenser."
echo "=========================================================="
