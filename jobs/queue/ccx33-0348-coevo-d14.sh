#!/usr/bin/env bash
# id: ccx33-0348-coevo-d14
# description: PHASE 3 — 1re boucle de CO-ÉVOLUTION à d14 (intuition JFC). jass@d14 ≈ Scan@d9 (0345) → du
# self-play jass à play_depth=14 produit de la data FORTE (≈ Scan-d9) SANS Scan. Les anciennes boucles
# (0181/0297) jouaient à d4 (faible = covariate-shift) ; ici on joue à d14. On génère, on ré-entraîne l'éval
# sur ces parties fortes (target WDL), et on juge eval1 vs eval0 (self-play) ET vs Scan (depth-égale).
# eval1 > eval0 → la co-évolution monte ; on itère. ≈ → la data forte ne suffit pas (→ capacité, cf 0347).
# expected_duration: ~4 h (self-play d14 dominant)
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-300}"
source jobs/lib/preflight.sh
source jobs/lib/manifest.sh
ART="/root/jass/jobs/results/ccx33-0348-coevo-d14/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
PLAY_D=14; EVAL_D=14; NPOS=120000; MAXPLY=200
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent"; exit 4; }

preflight_build 1
preflight_train 240000 1
preflight_note "self-play jass d${PLAY_D} ${NPOS} (×$NCPU, dominant)" 170
preflight_train "$NPOS" 1
preflight_note "matchs depth-égale (rapide)" 25
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }

echo "=== build + train eval0 (l'éval courante, Scan-distillée d9) ==="
B=build-full; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -8 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"
"$JASS" --dump-eval-features "$DATA" "$ART/e0.feat" >/dev/null 2>&1
python3 pattern_jass/tools/train.py --data "$DATA" --scan-eval --eval-features-file "$ART/e0.feat" \
  --target score --score-drop 3000 --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 --prune --lowmem --full-fold \
  --out "$ART/eval0.pjtw" >"$ART/e0-train.log" 2>&1
[ -f "$ART/eval0.pjtw" ] || { echo "TRAIN0 FAIL"; tail -8 "$ART/e0-train.log"; exit 9; }

echo "=== self-play jass à play_depth=${PLAY_D} avec eval0 (data FORTE), shardé ×${NCPU} ==="
PER=$(( (NPOS + NCPU - 1) / NCPU ))
for s in $(seq 0 $((NCPU-1))); do
  ( "$JASS" --gen-data-wdl "$PER" "$ART/.sp-$s.jnnw" "$EVAL_D" "$PLAY_D" "$MAXPLY" $((7000+s)) --nnue "$ART/eval0.pjtw" \
       >"$ART/.sp-$s.log" 2>&1 ) &
done
wait
python3 - "$ART/d14.jnnw" "$ART" "$NCPU" <<'PY'
import sys,struct,os
out,d,nc=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
o=open(out,'wb'); tot=0; o.write(b'JNNW'+struct.pack('<I',0))
for s in range(nc):
    f=os.path.join(d,f'.sp-{s}.jnnw')
    if not os.path.exists(f): print('shard',s,'manquant'); continue
    b=open(f,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; o.write(b[8:8+n*REC]); tot+=n
o.seek(4); o.write(struct.pack('<I',tot)); o.close(); print('d14 self-play',tot,'positions')
PY
for s in $(seq 0 $((NCPU-1))); do rm -f "$ART/.sp-$s.jnnw"; done
[ -f "$ART/d14.jnnw" ] || { echo "ABORT: gen vide"; tail -15 "$ART"/.sp-0.log 2>/dev/null; exit 7; }
DT=$(python3 -c "import struct;print(struct.unpack('<I',open('$ART/d14.jnnw','rb').read(8)[4:8])[0])")
echo "  d14 self-play : $DT positions"; [ "$DT" -gt 30000 ] || { echo "ABORT: data maigre ($DT)"; exit 7; }
python3 pattern_jass/tools/jnnw_stats.py "$ART/d14.jnnw" 2>/dev/null | sed -n '1,14p' || true

echo "=== train eval1 sur le self-play d14 (target WDL = jeu fort) ==="
"$JASS" --dump-eval-features "$ART/d14.jnnw" "$ART/e1.feat" >/dev/null 2>&1
python3 pattern_jass/tools/train.py --data "$ART/d14.jnnw" --scan-eval --eval-features-file "$ART/e1.feat" \
  --target wdl --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 --prune --lowmem --full-fold \
  --out "$ART/eval1.pjtw" >"$ART/e1-train.log" 2>&1
[ -f "$ART/eval1.pjtw" ] || { echo "TRAIN1 FAIL"; tail -8 "$ART/e1-train.log"; exit 9; }
manifest_write "$ART/eval1.pjtw" "COEVO d14 self-play target=wdl from eval0" "$ART/d14.jnnw" >/dev/null

rate(){ grep -E 'score rate' "$1" | grep -oE '0\.[0-9]+' | head -1; }
vsscan(){ python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$2" \
   --scan-bb-size 0 --jass-depth 9 --scan-depth 9 --pairs 6 --max-plies 160 >"$ART/vs-$1.log" 2>&1 || true; }
echo "=== juge eval1 vs eval0 (self-play) + vs Scan (depth-égale) ==="
"$JASS" --benchmark-search-params "$ART/eval1.pjtw" "" "" 9 5 1 0 >"$ART/e1-vs-e0.log" 2>&1 || true
# NB: benchmark-search-params compare params, pas évals → on compare via vs-Scan à la place.
[ -x "$SCAN_BIN" ] && { vsscan e0 "$ART/eval0.pjtw"; vsscan e1 "$ART/eval1.pjtw"; }

echo; echo "=========================================================="
echo "   ccx33-0348 — CO-ÉVOLUTION boucle 1 (self-play jass d${PLAY_D})"
echo "----------------------------------------------------------"
echo "   eval0 (Scan-distillé d9) vs Scan d9 : $(rate "$ART/vs-e0.log")"
echo "   eval1 (self-play d14, WDL) vs Scan d9 : $(rate "$ART/vs-e1.log")"
echo "----------------------------------------------------------"
echo "   eval1 > eval0 → la co-évolution d14 monte → itérer (boucle 2…)."
echo "   ≈/< → la data forte seule ne suffit pas (capacité, cf 0347) ou WDL trop bruité → essayer target score-d14."
echo "=========================================================="
