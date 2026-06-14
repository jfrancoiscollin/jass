#!/usr/bin/env bash
# id: cpx62-0239-geometry-distill-sweep
# description: CLASS-LIMITED pré-test (sans Scan, sur CPX62 idle). Découple la CAPACITÉ
# géométrique de la qualité des labels : on entraîne le full-fold DIRECTEMENT sur les labels
# Scan-d10 parfaits (1.0M) pour CHAQUE géométrie déjà codée — v4(32), v5(40), v6(diag-dense),
# v7(régions), lr-close(54) — et on compare la VAL-LOSS (fit de régression à Scan, déterministe,
# = le critère qu'on a adopté). Avec le prof parfait, une géométrie plus riche fitte-t-elle mieux ?
#   val-loss BAISSE nettement avec la richesse → la classe PEUT être relevée par la géométrie.
#   val-loss PLATE → richesse géométrique morte ; il faudra de la non-linéarité.
# Astuce : les 106 extras sont géométrie-indépendants (dump 1×) ; la val-loss vient de train.py
# (lit patterns.py, pas le binaire) → 1 seul build, géométrie pointée par JASS_PATTERNS_DIR (reset-proof).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0239-geometry-distill-sweep/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
MASTER=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
[ -f "$MASTER" ] || { echo "ABORT: master Scan-d10 introuvable"; exit 3; }
NTRAIN=1000000

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- train split 1M + extras (géométrie-INDÉPENDANTS : dump une seule fois) ---
MTRAIN="$ART/master1M.jnnw"
python3 - "$MASTER" "$MTRAIN" "$NTRAIN" <<'PYEOF'
import struct,sys
src,dst,n=sys.argv[1],sys.argv[2],int(sys.argv[3])
b=open(src,'rb').read(); tot=struct.unpack('<I',b[4:8])[0]; n=min(n,tot); REC=38
o=open(dst,'wb'); o.write(b'JNNW'); o.write(struct.pack('<I',n)); o.write(b[8:8+n*REC]); o.close()
print(f"train split {n} of {tot}")
PYEOF
echo "=== dump extras (106, géométrie-indépendants) ==="; $JASS --dump-eval-features "$MTRAIN" "$ART/featM" 2>&1 | tail -1

val_loss(){ grep -oE 'mse=[0-9.]+' "$1" | head -1 | cut -d= -f2; }   # ligne "val : mse=..."
declare -A NUM VL

# géométries : nom -> args gen_patterns
sweep() { # nom  args...
  local name="$1"; shift
  python3 pattern_jass/tools/gen_patterns.py "$@" --emit >"$ART/geom-$name.log" 2>&1 || { echo "  $name GEOM FAIL"; return; }
  local GD="/root/active_geom_$name"; mkdir -p "$GD"; cp pattern_jass/tools/patterns.py "$GD/patterns.py"
  local np; np=$(JASS_PATTERNS_DIR="$GD" python3 -c "import sys,os;sys.path.insert(0,os.environ['JASS_PATTERNS_DIR']);import patterns;print(patterns.NUM_PATTERNS)")
  NUM[$name]=$np
  local best="";
  for L2 in 3e-4 1e-4; do
    local out="$ART/d-$name-l2$L2.pjtw"
    JASS_PATTERNS_DIR="$GD" python3 pattern_jass/tools/train.py --data "$MTRAIN" --scan-eval \
        --eval-features-file "$ART/featM" --loss logistic --l2 "$L2" --max-iter 300 --scale 1000 \
        --prune --full-fold --out "$out" >"$ART/train-$name-l2$L2.log" 2>&1
    local v; v=$(val_loss "$ART/train-$name-l2$L2.log")
    echo "  $name (np=$np) l2=$L2  val_mse=${v:-FAIL}"
    [ -n "$v" ] && { [ -z "$best" ] && best="$v" || awk -v a="$v" -v b="$best" 'BEGIN{exit !(a<b)}' && best="$v"; }
    rm -f "$out"   # on ne garde pas les .pjtw (on compare la val-loss)
  done
  VL[$name]="${best:-NA}"
}

echo "=== SWEEP géométrie sous distillation Scan-d10 (val-loss, plus bas = mieux) ==="
sweep v4      --variant v4
sweep v5      --variant v5
sweep v7      --variant v7
sweep v6      --variant v6
sweep lrclose --variant v4 --lr-close

echo; echo "=========================================================="
echo "   cpx62-0239 — GÉOMÉTRIE SOUS DISTILLATION (val-loss vs Scan-truth)"
printf "   %-10s %-8s %-10s\n" "geometrie" "n_pat" "val_mse"
for g in v4 v5 v7 v6 lrclose; do printf "   %-10s %-8s %-10s\n" "$g" "${NUM[$g]:-?}" "${VL[$g]:-NA}"; done
echo "   → val-loss BAISSE avec la richesse  : la classe PEUT être relevée (géométrie actionnable)"
echo "   → val-loss PLATE / remonte          : richesse géométrique morte → non-linéarité requise"
echo "=========================================================="
