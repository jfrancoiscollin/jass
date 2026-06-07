#!/usr/bin/env bash
# id: 0149-scan-eval-tdleaf-finetune
# description: CYCLE D'APPRENTISSAGE du standalone (branche choisie). Fine-tune
# le prior ANCRÉ (config A de 0152, qui a réparé le matériel : 0.000→0.444 vs
# hc) par TD-leaf(λ) self-play, en GARDANT l'ancrage matériel à chaque cycle
# (sinon le re-fit re-casse le signe du matériel — cf 0151).
#
# Boucle (modèle₀ = config A de 0152) :
#   a. gen-tdleaf modèleₖ (self-play SEARCH-AWARE, shardé NCPU, depth = rapide)
#   b. td_leaf_targets (λ-return)  c. dump-eval-features
#   d. train --scan-eval --material-anchor 1.0  → modèleₖ₊₁
#   e. bench modèleₖ₊₁ vs handcrafted (suit la montée au-dessus de 0.444)
# Final : meilleur modèle vs v15 (depth + movetime court).
#
# Question : le self-play fait-il GRIMPER le prior sain au-dessus du
# handcrafted (>0.5 vs hc) et se rapprocher de v15 ?
#
# expected_duration: ~1.5-3 h.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0149-scan-eval-tdleaf-finetune"
ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

PRIOR=$(ls -t /root/jass/jobs/results/0152-standalone-material-anchor/artefacts.src/A.pjtw 2>/dev/null | head -1)
[ -n "$PRIOR" ] && [ -f "$PRIOR" ] || { echo "ABORT: prior ancré (config A de 0152) manquant"; exit 3; }
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }
echo "prior (ancré) : $PRIOR"; echo "v15 : $V15"

SPEC1B="use_conthist=1"   # search-aware (aligner sur 0148 plus tard)
LAM=0.7; MAXPLY=200; MATANCHOR=1.0
echo "SPEC1B='$SPEC1B'  λ=$LAM  material-anchor=$MATANCHOR"

echo; echo "=== build prod + tests ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || { echo TESTS FAIL; tail -20 "$ART/tests.log"; exit 6; }
python3 -c "import numpy, scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# Sharded self-play (gen-tdleaf est mono-thread) → NCPU shards, fusion.
gen_sharded () {  # $1 in $2 depth $3 mt $4 ntot $5 seedbase $6 out
    local in="$1" depth="$2" mt="$3" ntot="$4" seedbase="$5" out="$6"
    local per=$(( (ntot + NCPU - 1) / NCPU )); local pids=(); local shards=()
    for sh in $(seq 0 $((NCPU-1))); do
        local lv="${out}.shard${sh}.jnnw"; shards+=("$lv")
        ./build-prod/jass --gen-tdleaf "$in" "$per" "$depth" "$lv" "$MAXPLY" \
            "$(( seedbase + sh ))" "$mt" "$SPEC1B" > "${out}.shard${sh}.log" 2>&1 & pids+=($!)
    done
    for p in "${pids[@]}"; do wait "$p" || echo "  (shard $p rc!=0)"; done
    python3 - "$out" "${shards[@]}" <<'PYEOF'
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
    rm -f "${out}".shard*.log
}

anyrate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }

tdleaf_iter () {  # $1 in_model $2 out_model $3 seedbase  → echoes vs-hc rate
    local in="$1" out="$2" seedbase="$3" tag="it-s${3}"
    local lv="$ART/${tag}-leaves.jnnw"
    gen_sharded "$in" 8 0 800 "$seedbase" "$lv"
    python3 tools/td_leaf_targets.py --leaves "$lv" --games "$lv.games" \
        --out "$ART/${tag}-tg.jnnw" --lam "$LAM" > "$ART/${tag}-td.log" 2>&1
    ./build-prod/jass --dump-eval-features "$ART/${tag}-tg.jnnw" "$ART/${tag}-tg.feat" > "$ART/${tag}-dump.log" 2>&1
    python3 pattern_jass/tools/train.py --data "$ART/${tag}-tg.jnnw" --scan-eval \
        --eval-features-file "$ART/${tag}-tg.feat" --target score --score-clip 5000 \
        --l2 1e-5 --max-iter 150 --scale 1000 --material-anchor "$MATANCHOR" \
        --man-pu 1.0 --king-pu 3.0 --out "$out" > "$ART/${tag}-train.log" 2>&1
    rm -f "$lv" "$lv.games" "$ART/${tag}-tg.jnnw" "$ART/${tag}-tg.feat"
    ./build-prod/jass --benchmark-scan-eval "$out" hc 8 3 1 0 "" 64 > "$ART/${tag}-vs-hc.log" 2>&1
    anyrate "$ART/${tag}-vs-hc.log"
}

echo; echo "########## CYCLES TD-LEAF (ancré matériel) ##########"
echo "  prior (config A) vs hc = (rappel 0152) 0.444"
model="$PRIOR"; ITERS=3
for it in $(seq 1 $ITERS); do
    nxt="$ART/tuned-it${it}.pjtw"
    echo "--- itération $it (gen depth 8, 800 parties × $NCPU shards) ---"
    r=$(tdleaf_iter "$model" "$nxt" "$(( 2000 + it*10 ))")
    grep -E "val   :" "$ART/it-s$(( 2000 + it*10 ))-train.log" | sed 's/^/    /'
    echo "    → itération $it vs hc = ${r:-?}"
    [ -f "$nxt" ] || { echo "  (échec it$it)"; break; }
    model="$nxt"
done
FINAL="$model"
echo; echo "final tuné : $FINAL"

echo; echo "=== bench final vs v15 (depth 9 + movetime 300) ==="
./build-prod/jass --benchmark-scan-eval "$FINAL"  "$V15" 9  3 1 0   "$SPEC1B" 64 > "$ART/final-vs-v15-d9.log" 2>&1
./build-prod/jass --benchmark-scan-eval "$FINAL"  "$V15" 64 3 1 300 "$SPEC1B" 64 > "$ART/final-vs-v15-mt.log" 2>&1

echo; echo "=========================================================="
echo "        0149 CYCLE TD-LEAF (standalone ancré) — VERDICT"
echo "=========================================================="
echo "  prior(A) vs hc = 0.444 (0152)"
for it in 1 2 3; do
  f="$ART/it-s$(( 2000 + it*10 ))-vs-hc.log"
  [ -f "$f" ] && echo "  itération $it vs hc = $(anyrate "$f")"
done
echo "  FINAL vs v15 : d9=$(anyrate "$ART/final-vs-v15-d9.log")  mt=$(anyrate "$ART/final-vs-v15-mt.log")"
echo "  → si vs hc grimpe >0.5 : le self-play boost le standalone ; continuer."
echo "  → si plat/baisse : le TD-leaf ne paie pas ici → revoir cible/features."
echo "=========================================================="
