#!/usr/bin/env bash
# id: ccx33-0346-deeper-teacher
# description: PHASE 2 (sonde éval) — un TEACHER plus profond aide-t-il ? On distille Scan à d12 vs d9 sur les
# MÊMES positions, et on juge les deux évals à PROFONDEUR ÉGALE vs Scan (comparaison d'éval pure). d12 > d9 →
# le label depth-9 sous-estimait Scan, monter la depth du teacher rapproche l'éval. ≈ → plafond de distillation
# atteint, le teacher n'est pas le levier.
# expected_duration: ~3 h (relabel Scan d12 dominant)
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-240}"
source jobs/lib/preflight.sh
source jobs/lib/manifest.sh
source jobs/lib/relabel.sh
ART="/root/jass/jobs/results/ccx33-0346-deeper-teacher/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw  # déjà d9
SCAN_BIN=/root/jass-scan/scan_linux
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent"; exit 4; }
NPOS=150000; DEEP=12

preflight_build 1
preflight_note "relabel Scan d${DEEP} ${NPOS} (×$NCPU, dominant)" 130
preflight_train "$NPOS" 2
preflight_note "matchs depth-égale vs Scan (rapide)" 30
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan indisponible"; exit 5; }

echo "=== build jass FULL Scan-alignée (combo baké) ==="
B=build-full; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
      >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; tail -8 "$ART/cmake.log"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -12 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"
cnt(){ python3 -c "import struct;print(struct.unpack('<I',open('$1','rb').read(8)[4:8])[0])"; }

echo "=== sous-échantillon ${NPOS} (déjà d9) ==="
python3 - "$DATA" "$ART/sub.jnnw" "$NPOS" <<'PY'
import sys,struct
src,out,n=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
b=open(src,'rb').read(); tot=struct.unpack('<I',b[4:8])[0]; body=b[8:]
n=min(n,tot); st=max(1,tot//n); r=bytearray(); k=0
for i in range(0,tot,st):
    r+=body[i*REC:(i+1)*REC]; k+=1
    if k>=n: break
open(out,'wb').write(b'JNNW'+struct.pack('<I',k)+bytes(r)); print('sub',k,'/',tot)
PY

echo "=== relabel Scan d${DEEP} (teacher plus profond) ==="
relabel_scan_sharded "$ART/sub.jnnw" "$ART/sub-d12.jnnw" "$SCAN_BIN" "$DEEP" "$NCPU"
[ -f "$ART/sub-d12.jnnw" ] || { echo "RELABEL FAIL"; exit 8; }

train_one(){ local name="$1" data="$2"
  "$JASS" --dump-eval-features "$data" "$ART/$name.feat" >/dev/null 2>&1
  python3 pattern_jass/tools/train.py --data "$data" --scan-eval --eval-features-file "$ART/$name.feat" \
    --target score --score-drop 3000 --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 \
    --prune --lowmem --full-fold --out "$ART/$name.pjtw" >"$ART/$name-train.log" 2>&1
  [ -f "$ART/$name.pjtw" ] || { echo "$name TRAIN FAIL"; tail -8 "$ART/$name-train.log"; return 1; }; }
echo "=== train éval d9 (baseline) + d12 (teacher profond), mêmes positions ==="
train_one d9  "$ART/sub.jnnw"
train_one d12 "$ART/sub-d12.jnnw"

rate(){ grep -E 'score rate' "$1" | grep -oE '0\.[0-9]+' | head -1; }
judge(){ local name="$1"; python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" \
    --jass-pattern "$ART/$name.pjtw" --scan-bb-size 0 --jass-depth 9 --scan-depth 9 --pairs 6 --max-plies 160 \
    >"$ART/vs-$name.log" 2>&1 || true; echo "  $name : depth9 vs Scan = $(rate "$ART/vs-$name.log")"; }
echo "=== juge à profondeur égale (éval pure) vs Scan d9 ==="
judge d9
judge d12

echo; echo "=========================================================="
echo "   ccx33-0346 — teacher d12 vs d9 (éval pure, depth9 vs Scan, 108 parties)"
echo "----------------------------------------------------------"
echo "   éval d9  (teacher d9 ) : $(rate "$ART/vs-d9.log")"
echo "   éval d12 (teacher d12) : $(rate "$ART/vs-d12.log")"
echo "----------------------------------------------------------"
echo "   d12 > d9 → teacher plus profond rapproche l'éval. ≈ → plafond de distillation."
echo "=========================================================="
