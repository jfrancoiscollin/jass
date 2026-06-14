#!/usr/bin/env bash
# id: cpx62-0240-king-brick-test
# description: BRIQUE ROIS — test direct (sans Scan, CPX62). Les rois sont-ils LE morceau
# manquant de notre classe linéaire vs Scan ? On distille le master Scan-d10 (1M, labels
# parfaits) en MEN-ONLY vs KING-AWARE (men|kings, Scan-style) et on compare : val-loss (fit
# de régression à Scan, le critère) + Elo vs hc. Chaque éval est jouée par le binaire de SON
# mode (men-only / -DJASS_KING_PATTERNS=ON) pour rester cohérente. Si king-aware baisse la
# val-loss / monte en Elo → les rois étaient le bug structurel → on l'embarque dans le loop.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0240-king-brick-test/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
MASTER=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
[ -f "$MASTER" ] || { echo "ABORT: master Scan-d10 introuvable"; exit 3; }
NTRAIN=1000000

# --- deux binaires : men-only (défaut) + king-aware (men|kings) ---
echo "=== build men-only ==="
cmake -S . -B build-mo   -DCMAKE_BUILD_TYPE=Release >"$ART/cm-mo.log" 2>&1
cmake --build build-mo   -j"$NCPU" --target jass >"$ART/b-mo.log" 2>&1 || { echo "MO BUILD FAIL"; tail -20 "$ART/b-mo.log"; exit 5; }
echo "=== build king-aware (-DJASS_KING_PATTERNS=ON) ==="
cmake -S . -B build-king -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON >"$ART/cm-king.log" 2>&1
cmake --build build-king -j"$NCPU" --target jass >"$ART/b-king.log" 2>&1 || { echo "KING BUILD FAIL"; tail -20 "$ART/b-king.log"; exit 5; }
grep -q "KING-AWARE patterns ENABLED" "$ART/cm-king.log" || { echo "ABORT: king build n'a pas activé le flag"; exit 5; }
JASS_MO=/root/jass/build-mo/jass; JASS_K=/root/jass/build-king/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- train split 1M + extras (king-INDÉPENDANTS : dump une fois, binaire men-only) ---
MTRAIN="$ART/master1M.jnnw"
python3 - "$MASTER" "$MTRAIN" "$NTRAIN" <<'PYEOF'
import struct,sys
src,dst,n=sys.argv[1],sys.argv[2],int(sys.argv[3])
b=open(src,'rb').read(); tot=struct.unpack('<I',b[4:8])[0]; n=min(n,tot); REC=38
o=open(dst,'wb'); o.write(b'JNNW'); o.write(struct.pack('<I',n)); o.write(b[8:8+n*REC]); o.close()
print(f"train split {n} of {tot}")
PYEOF
echo "=== dump extras (king-indépendants) ==="; $JASS_MO --dump-eval-features "$MTRAIN" "$ART/featM" 2>&1 | tail -1

val_loss(){ grep -oE 'mse=[0-9.]+' "$1" | head -1 | cut -d= -f2; }
elo_hc(){ local BIN="$1" EV="$2" P="$3" lg="$ART/elo-$(basename "$EV" .pjtw).log"
  "$BIN" --benchmark-scan-eval "$EV" hc 9 "$P" "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  local E=$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2)
  echo "${W:-0}-${D:-0}-${L:-0} elo=${E:-NA}"; }

declare -A VL ELO
# arm: nom  binaire  flag-train
arm(){ local name="$1" BIN="$2" FLAG="$3"; local best="" bestout=""
  for L2 in 3e-4 1e-4; do
    local out="$ART/$name-l2$L2.pjtw"
    python3 pattern_jass/tools/train.py --data "$MTRAIN" --scan-eval --eval-features-file "$ART/featM" \
        --loss logistic --l2 "$L2" --max-iter 300 --scale 1000 --prune --full-fold $FLAG --out "$out" \
        >"$ART/train-$name-l2$L2.log" 2>&1
    local v; v=$(val_loss "$ART/train-$name-l2$L2.log")
    echo "  [$name] l2=$L2  val_mse=${v:-FAIL}"
    [ -n "$v" ] && { [ -z "$best" ] && { best="$v"; bestout="$out"; } || awk -v a="$v" -v b="$best" 'BEGIN{exit !(a<b)}' && { best="$v"; bestout="$out"; }; }
  done
  VL[$name]="${best:-NA}"
  [ -n "$bestout" ] && ELO[$name]=$(elo_hc "$BIN" "$bestout" 60) || ELO[$name]="NA"
  echo "  [$name] BEST val_mse=${VL[$name]}  Elo_vs_hc=${ELO[$name]}"
}

echo "=== ARM men-only (binaire men-only) ==="
arm "menonly" "$JASS_MO" ""
echo "=== ARM king-aware (--king-patterns, binaire king-aware) ==="
arm "kingaware" "$JASS_K" "--king-patterns"

echo; echo "=========================================================="
echo "   cpx62-0240 — BRIQUE ROIS sous distillation Scan-d10 (1M)"
printf "   %-12s %-12s %-22s\n" "mode" "val_mse" "Elo_vs_hc(60p)"
printf "   %-12s %-12s %-22s\n" "men-only"   "${VL[menonly]:-NA}"   "${ELO[menonly]:-NA}"
printf "   %-12s %-12s %-22s\n" "king-aware" "${VL[kingaware]:-NA}" "${ELO[kingaware]:-NA}"
echo "   → king-aware val-loss PLUS BASSE / Elo PLUS HAUT : les rois étaient le morceau manquant"
echo "     → embarquer --king-patterns + build king-aware dans le loop self-play scalé."
echo "   → égal/pire : ce n'est pas (que) les rois ; chercher ailleurs (toujours sans pivoter)."
echo "=========================================================="
