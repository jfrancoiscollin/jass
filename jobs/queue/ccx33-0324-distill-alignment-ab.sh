#!/usr/bin/env bash
# id: ccx33-0324-distill-alignment-ab
# description: CONTRÔLE de l'alignement Scan (en parallèle de cpx62-0323). A/B CHIRURGICAL : mêmes positions
# (~500k échantillonnées du 2.5M de ccx33), MÊME relabel Scan (depth-10, fait UNE fois), on entraîne deux
# évals et on les juge vs Scan mt1.5 : ALIGNÉ (king_mob + scan-parity + tempo-stage) vs BASE (king_mob seul,
# phase pièces). Seule l'archi change → isole « l'alignement Scan a-t-il aidé la distillation ? ».
# expected_duration: ~9-11 h (relabel Scan domine, 8 cœurs)
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-720}"
source jobs/lib/preflight.sh
source jobs/lib/manifest.sh
ART="/root/jass/jobs/results/ccx33-0324-distill-alignment-ab/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
WLD=/root/egdb_extracted/app
DS=/root/jass/jobs/results/ccx33-0313-endgame-data-gen/artefacts.src/endgame-cumulative.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
SCAN_DEPTH=10; NPOS=500000
[ -f "$DS" ] || { echo "ABORT: dataset 0313 ccx33 absent"; exit 4; }

preflight_build 2
preflight_note "relabel Scan ${NPOS} @ d${SCAN_DEPTH} (×$NCPU, dominant)" 360
preflight_train "$NPOS" 2
preflight_match $((2*9*2)) 1.5 160; preflight_match $((2*9*2)) 1.5 160
preflight_check
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan indisponible"; exit 5; }

# --- échantillon (stride) + relabel Scan UNE fois (partagé par les deux archis) ---
echo "=== échantillon ${NPOS} + relabel Scan (depth ${SCAN_DEPTH}) ==="
python3 - "$DS" "$ART/sub.jnnw" "$NPOS" <<'PY'
import sys,struct
src,out,npos=sys.argv[1],sys.argv[2],int(sys.argv[3])
b=open(src,'rb').read(); REC=38; tot=struct.unpack('<I',b[4:8])[0]; body=b[8:]
stride=max(1,tot//npos); recs=bytearray(); n=0
for i in range(0,tot,stride):
    recs+=body[i*REC:(i+1)*REC]; n+=1
    if n>=npos: break
open(out,'wb').write(b'JNNW'+struct.pack('<I',n)+bytes(recs)); print('sub',n,'/',tot)
PY
python3 tools/relabel_with_scan.py --in "$ART/sub.jnnw" --out "$ART/scan.jnnw" \
    --scan "$SCAN_BIN" --depth "$SCAN_DEPTH" --threads "$NCPU" --progress-every 20000 >"$ART/relabel.log" 2>&1
[ -f "$ART/scan.jnnw" ] || { echo "RELABEL FAIL"; tail -15 "$ART/relabel.log"; exit 7; }
echo "  relabelisé: $(python3 -c "import struct;print(struct.unpack('<I',open('$ART/scan.jnnw','rb').read(8)[4:8])[0])") positions"

elo(){ local lg="$1-elo.log"; "$2" --benchmark-scan-eval "$1.pjtw" hc 9 60 "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2); local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2; }

declare -A ELOHC SCAN
arm(){ # <name> <extra-cmake> <extra-train>
  local name="$1" xc="$2" xt="$3" B="build-$1"
  rm -rf "$B"
  cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
        -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON $xc >"$ART/$name-cmake.log" 2>&1
  grep -q "EXTERNAL EGDB ENABLED" "$ART/$name-cmake.log" || { echo "$name: egdb off"; return 1; }
  cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/$name-build.log" 2>&1 || { echo "$name BUILD FAIL"; tail -8 "$ART/$name-build.log"; return 1; }
  local J="$PWD/$B/jass"
  "$J" --dump-eval-features "$ART/scan.jnnw" "$ART/$name.feat" >/dev/null 2>&1
  python3 pattern_jass/tools/train.py --data "$ART/scan.jnnw" --scan-eval --eval-features-file "$ART/$name.feat" \
    --target score --score-drop 3000 $xt --l2 1e-4 --max-iter 300 --scale 1000 --prune --lowmem --full-fold \
    --out "$ART/$name.pjtw" >"$ART/$name-train.log" 2>&1
  [ -f "$ART/$name.pjtw" ] || { echo "$name TRAIN FAIL"; tail -8 "$ART/$name-train.log"; return 1; }
  manifest_write "$ART/$name.pjtw" "DISTILL=Scan-d${SCAN_DEPTH} $xc $xt" "$ART/scan.jnnw" >/dev/null
  ELOHC[$name]=$(elo "$ART/$name" "$J")
  python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$ART/$name.pjtw" \
      --scan-bb-size 0 --movetime 1.5 --pairs 2 --max-plies 160 --allow-long-movetime >"$ART/$name-scan.log" 2>&1 || true
  SCAN[$name]=$(grep -E 'score rate' "$ART/$name-scan.log" | grep -oE '[0-9.]+ \([0-9./]+\)' | head -1)
  echo "  $name : Elo_hc=${ELOHC[$name]:-NA}  vs_Scan_mt1.5=${SCAN[$name]:-NA}"
}

echo "=== ALIGNÉ (king_mob + scan-parity + tempo-stage) ==="
arm aligned "-DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON" "--tempo-stage"
echo "=== BASE (king_mob seul, phase pièces) ==="
arm base "" ""

echo; echo "=========================================================="
echo "   ccx33-0324 — CONTRÔLE alignement Scan (distillation A/B chirurgical)"
echo "----------------------------------------------------------"
printf "  %-8s Elo_hc=%-9s vs_Scan_mt1.5=%s\n" aligned "${ELOHC[aligned]:-NA}" "${SCAN[aligned]:-NA}"
printf "  %-8s Elo_hc=%-9s vs_Scan_mt1.5=%s\n" base    "${ELOHC[base]:-NA}"    "${SCAN[base]:-NA}"
echo "----------------------------------------------------------"
echo "  aligned vs_Scan > base → l'alignement Scan (tempo-stage + skew + king-mat) AIDE la distillation."
echo "  ≈ égal → l'alignement n'a pas aidé ; le gain de distillation vient d'ailleurs (king_mob/patterns)."
echo "=========================================================="
