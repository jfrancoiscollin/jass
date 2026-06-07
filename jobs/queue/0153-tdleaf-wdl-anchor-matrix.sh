#!/usr/bin/env bash
# id: 0153-tdleaf-wdl-anchor-matrix
# description: DIAGNOSTIC de l'effondrement 0149. Le fine-tuning self-play a
# fait chuter le standalone ancré de 0.444 → 0.056 vs hc. Cause suspectée :
# bootstrap cold-start (TD-leaf sur les estimations d'une éval sous-handcrafted)
# + perte de l'anti-oubli. On isole en une matrice 2×2, MÊME génération
# self-play (depuis config A) réutilisée pour les 4 cellules :
#
#            | sans ancre vers A      | ancré vers A (anti-oubli L2)
#   TD-leaf  | = 0149 (réf effondrée) | l'anti-oubli sauve-t-il ?
#   λ=0.7    |                        |
#   WDL      | la vérité-terrain      | WDL + anti-oubli
#   λ=1.0    | (résultat Z) suffit ?  |
#
# (λ=1 ⇒ G_t télescope vers Z = résultat ±5000 → cible = WDL pur.)
# Ancrage MATÉRIEL gardé partout (garder le matériel sain). Bench vs hc.
# Lecture : une cellule qui TIENT ≥0.444 (voire monte) = recette du cycle.
#           Aucune ne tient → limiteur = features → basculer patterns riches.
#
# expected_duration: ~40-60 min.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0153-tdleaf-wdl-anchor-matrix"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

A=$(ls -t /root/jass/jobs/results/0152-standalone-material-anchor/artefacts.src/A.pjtw 2>/dev/null | head -1)
[ -n "$A" ] && [ -f "$A" ] || { echo "ABORT: config A (0152) manquante"; exit 3; }
echo "prior/ancre = config A : $A"

SPEC1B="use_conthist=1"; MAXPLY=200; ANCHOR_L2=0.2; MATANCHOR=1.0
echo "SPEC1B='$SPEC1B'  anchor_l2(anti-oubli)=$ANCHOR_L2  material-anchor=$MATANCHOR"

echo; echo "=== build prod + tests ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || { echo TESTS FAIL; tail -20 "$ART/tests.log"; exit 6; }
python3 -c "import numpy, scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- une seule génération self-play depuis config A, shardée ---
LV="$ART/leaves.jnnw"; per=$(( (800 + NCPU - 1) / NCPU )); pids=(); shards=()
echo; echo "=== gen self-play (config A, depth 8, ~800 parties × $NCPU shards) ==="
for sh in $(seq 0 $((NCPU-1))); do
    lv="$LV.shard${sh}.jnnw"; shards+=("$lv")
    ./build-prod/jass --gen-tdleaf "$A" "$per" 8 "$lv" "$MAXPLY" "$(( 3000 + sh ))" 0 "$SPEC1B" > "$LV.s${sh}.log" 2>&1 & pids+=($!)
done
for p in "${pids[@]}"; do wait "$p" || echo "  (shard $p rc!=0)"; done
python3 - "$LV" "${shards[@]}" <<'PYEOF'
import struct, sys
from pathlib import Path
out=sys.argv[1]; shards=sys.argv[2:]; total=0
with open(out,'wb') as o, open(out+'.games','w') as g:
    o.write(b'JNNW'); o.write(struct.pack('<I',0))
    for s in shards:
        r=Path(s).read_bytes(); n=struct.unpack_from('<I',r,4)[0]
        o.write(r[8:8+n*38]); total+=n
        gp=Path(s+'.games')
        if gp.exists(): g.write(gp.read_text())
        Path(s).unlink(missing_ok=True); gp.unlink(missing_ok=True)
    o.seek(4); o.write(struct.pack('<I',total))
print(f'merged {total} leaf records → {out}')
PYEOF
rm -f "$LV".s*.log

# --- cibles : TD-leaf (λ0.7) et WDL (λ1.0) ; mêmes positions → 1 dump features ---
python3 tools/td_leaf_targets.py --leaves "$LV" --games "$LV.games" --out "$ART/tg-td.jnnw"  --lam 0.7 > "$ART/td07.log" 2>&1
python3 tools/td_leaf_targets.py --leaves "$LV" --games "$LV.games" --out "$ART/tg-wdl.jnnw" --lam 1.0 > "$ART/td10.log" 2>&1
./build-prod/jass --dump-eval-features "$ART/tg-td.jnnw" "$ART/feat" > "$ART/dump.log" 2>&1
echo "cibles TD-leaf + WDL prêtes ; features dumpées une fois."

anyrate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }

train_cell () {  # $1 tag  $2 target.jnnw  $3 anchorA(0|1)
    local tag="$1" data="$2" useA="$3" out="$ART/$1.pjtw" aargs=""
    [ "$useA" = "1" ] && aargs="--anchor-weights $A --anchor-l2 $ANCHOR_L2"
    python3 pattern_jass/tools/train.py --data "$data" --scan-eval \
        --eval-features-file "$ART/feat" --target score --score-clip 5000 \
        --l2 1e-5 --max-iter 150 --scale 1000 --material-anchor "$MATANCHOR" \
        --man-pu 1.0 --king-pu 3.0 $aargs --out "$out" > "$ART/$tag-train.log" 2>&1
    ./build-prod/jass --benchmark-scan-eval "$out" hc 8 3 1 0 "" 64 > "$ART/$tag-vs-hc.log" 2>&1
    local v; v=$(grep -E "val   :" "$ART/$tag-train.log" | head -1 | grep -oE 'mse=[0-9.]+')
    printf "  %-14s vs hc = %-9s (%s)\n" "$tag" "$(anyrate "$ART/$tag-vs-hc.log")" "$v"
}

echo; echo "########## MATRICE 2×2 (vs hc, gen commune config A) ##########"
echo "  rappel : config A (prior) vs hc = 0.444"
train_cell td-noA   "$ART/tg-td.jnnw"  0
train_cell td-A     "$ART/tg-td.jnnw"  1
train_cell wdl-noA  "$ART/tg-wdl.jnnw" 0
train_cell wdl-A    "$ART/tg-wdl.jnnw" 1
rm -f "$LV" "$LV.games" "$ART/tg-td.jnnw" "$ART/tg-wdl.jnnw" "$ART/feat"

echo; echo "=========================================================="
echo "        0153 MATRICE TD-leaf/WDL × anti-oubli — VERDICT"
echo "=========================================================="
echo "  config A (réf)   vs hc = 0.444"
for t in td-noA td-A wdl-noA wdl-A; do
  echo "  $t  vs hc = $(anyrate "$ART/$t-vs-hc.log")"
done
echo "  → cellule ≥0.444 = recette du cycle d'apprentissage."
echo "  → toutes <0.444 = méthode non en cause → patterns plus riches (Levier 3)."
echo "=========================================================="
