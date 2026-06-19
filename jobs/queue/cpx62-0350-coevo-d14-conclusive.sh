#!/usr/bin/env bash
# id: cpx62-0350-coevo-d14-conclusive
# description: CO-ÉVOLUTION d14, version CONCLUSIVE (cpx62, gros volume). Intuition JFC : jass@d14 ≈ Scan@d9
# → self-play jass à play_depth=14 = data FORTE sans Scan (les vieilles boucles jouaient à d4 = faible). On
# génère ~280k, on ré-entraîne eval1 (target WDL), et on JUGE eval1 vs eval0 EN DIRECT (--benchmark-nnue-vs-nnue
# accepte 2 pjtw, métrique sensible centrée 0.5) + vs Scan. Volume suffisant pour CONCLURE.
# expected_duration: ~4-5 h (self-play d14 dominant)
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-360}"
source jobs/lib/preflight.sh
source jobs/lib/manifest.sh
ART="/root/jass/jobs/results/cpx62-0350-coevo-d14-conclusive/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
PLAY_D=14; EVAL_D=10; NPOS=280000; MAXPLY=200
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent"; exit 4; }

preflight_build 1
preflight_train 240000 1
preflight_note "self-play jass d${PLAY_D} ${NPOS} (×$NCPU, dominant)" 180
preflight_train "$NPOS" 1
preflight_note "juge eval-vs-eval (180p depth9) + vs Scan" 40
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }

echo "=== build + train eval0 (Scan-distillé d9, l'éval courante) ==="
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

echo "=== self-play jass d${PLAY_D} avec eval0 (data forte), ${NPOS} shardé ×${NCPU} ==="
PER=$(( (NPOS + NCPU - 1) / NCPU ))
for s in $(seq 0 $((NCPU-1))); do
  ( "$JASS" --gen-data-wdl "$PER" "$ART/.sp-$s.jnnw" "$EVAL_D" "$PLAY_D" "$MAXPLY" $((7100+s)) --nnue "$ART/eval0.pjtw" \
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
DT=$(python3 -c "import struct;print(struct.unpack('<I',open('$ART/d14.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
echo "  d14 self-play : $DT positions"; [ "$DT" -gt 100000 ] || { echo "ABORT: data maigre ($DT)"; tail -15 "$ART"/.sp-0.log 2>/dev/null; exit 7; }
python3 pattern_jass/tools/jnnw_stats.py "$ART/d14.jnnw" 2>/dev/null | sed -n '1,14p' || true

echo "=== train eval1 sur le self-play d14 (target WDL) ==="
"$JASS" --dump-eval-features "$ART/d14.jnnw" "$ART/e1.feat" >/dev/null 2>&1
python3 pattern_jass/tools/train.py --data "$ART/d14.jnnw" --scan-eval --eval-features-file "$ART/e1.feat" \
  --target wdl --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 --prune --lowmem --full-fold \
  --out "$ART/eval1.pjtw" >"$ART/e1-train.log" 2>&1
[ -f "$ART/eval1.pjtw" ] || { echo "TRAIN1 FAIL"; tail -8 "$ART/e1-train.log"; exit 9; }
manifest_write "$ART/eval1.pjtw" "COEVO d14 (play${PLAY_D}) target=wdl from eval0 N=${DT}" "$ART/d14.jnnw" >/dev/null

rate(){ grep -E 'score rate|A score rate' "$1" | grep -oE '0\.[0-9]+' | head -1; }
echo "=== JUGE 1 (sensible) : eval1 vs eval0 EN DIRECT (depth 9, 180 parties) ==="
"$JASS" --benchmark-nnue-vs-nnue "$ART/eval1.pjtw" "$ART/eval0.pjtw" 9 10 1 0 >"$ART/e1-vs-e0.log" 2>&1 || true
echo "=== JUGE 2 (absolu) : eval0 et eval1 vs Scan (depth-égale d9) ==="
vsscan(){ python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$2" \
   --scan-bb-size 0 --jass-depth 9 --scan-depth 9 --pairs 6 --max-plies 160 >"$ART/vs-$1.log" 2>&1 || true; }
[ -x "$SCAN_BIN" ] && { vsscan e0 "$ART/eval0.pjtw"; vsscan e1 "$ART/eval1.pjtw"; }

echo; echo "=========================================================="
echo "   cpx62-0350 — CO-ÉVOLUTION d14 CONCLUSIVE (${DT} positions)"
echo "----------------------------------------------------------"
echo "   eval1 vs eval0 EN DIRECT (depth9, 180p) : A-rate=$(rate "$ART/e1-vs-e0.log")   <-- métrique sensible"
echo "   eval0 vs Scan d9 : $(rate "$ART/vs-e0.log")    eval1 vs Scan d9 : $(rate "$ART/vs-e1.log")"
echo "----------------------------------------------------------"
echo "   A-rate(eval1 vs eval0) > 0.55 → la co-évolution d14 MONTE → itérer (boucle 2)."
echo "   ≈0.5 / < → le jeu fort seul ne suffit pas → capacité (diag 0349) ou target score-d14."
echo "=========================================================="
