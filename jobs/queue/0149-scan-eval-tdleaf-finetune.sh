#!/usr/bin/env bash
# id: 0149-scan-eval-tdleaf-finetune
# description: FINE-TUNING de la v3 Scan-eval par TD-leaf(λ) self-play, APRÈS
# le prior de distillation (0147). Décision utilisateur :
#   - cible : LES DEUX comparées → 2 bras, PUR vs ANCRÉ-Scan (L2 vers le prior)
#   - budget : MIXTE → itérations courtes (depth) puis profondes (movetime)
#
# Boucle par bras (modèle₀ = prior 0147) :
#   a. gen-tdleaf  modèleₖ  (self-play SEARCH-AWARE : briques 1b activées)
#   b. td_leaf_targets.py  (λ-return forward-view)
#   c. dump-eval-features  (les 106 extras des positions FEUILLES)
#   d. train.py --scan-eval [--anchor-weights prior --anchor-l2]  → modèleₖ₊₁
# Puis bench de chaque bras final vs v15 (depth+movetime) et vs le prior.
#
# NB : SPEC1B = briques 1b à activer en génération. À régler sur les
# gagnantes de 0148 ; défaut conservateur conthist+iid en attendant.
#
# expected_duration: ~4-7 h (2 bras × 5 itérations × self-play+fit).
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0149-scan-eval-tdleaf-finetune"
ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

PRIOR=$(ls -t /root/jass/jobs/results/0147-scan-eval-full/artefacts.src/scan_eval_v3.pjtw 2>/dev/null | head -1)
[ -n "$PRIOR" ] && [ -f "$PRIOR" ] || { echo "ABORT: prior v3 (0147) manquant — lancer 0147 d'abord"; exit 3; }
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }
echo "prior : $PRIOR"; echo "v15 : $V15"

# Briques 1b activées en génération (search-aware). À aligner sur 0148.
SPEC1B="use_conthist=1,iid_min_depth=4"
LAM=0.7; ANCHOR_L2=0.05; MAXPLY=200
echo "SPEC1B='$SPEC1B'  λ=$LAM  anchor_l2=$ANCHOR_L2"

echo; echo "=== build prod + tests ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || {
    echo "TESTS FAIL"; tail -20 "$ART/tests.log"; exit 6; }

python3 -c "import numpy, scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# One TD-leaf iteration : $1 in_model $2 out_model $3 arm $4 depth $5 movetime
#                         $6 n_games $7 seed
tdleaf_iter () {
    local in="$1" out="$2" arm="$3" depth="$4" mt="$5" ngames="$6" seed="$7"
    local tag="${arm}-s${seed}"
    local lv="$ART/${tag}-leaves.jnnw"
    echo "  [$tag] gen-tdleaf depth=$depth mt=$mt games=$ngames"
    ./build-prod/jass --gen-tdleaf "$in" "$ngames" "$depth" "$lv" "$MAXPLY" "$seed" "$mt" "$SPEC1B" \
        > "$ART/${tag}-gen.log" 2>&1
    python3 tools/td_leaf_targets.py --leaves "$lv" --games "$lv.games" \
        --out "$ART/${tag}-targets.jnnw" --lam "$LAM" > "$ART/${tag}-td.log" 2>&1
    ./build-prod/jass --dump-eval-features "$ART/${tag}-targets.jnnw" \
        "$ART/${tag}-targets.feat" > "$ART/${tag}-dump.log" 2>&1
    local anchor_args=""
    [ "$arm" = "anchored" ] && anchor_args="--anchor-weights $PRIOR --anchor-l2 $ANCHOR_L2"
    python3 pattern_jass/tools/train.py --data "$ART/${tag}-targets.jnnw" --scan-eval \
        --eval-features-file "$ART/${tag}-targets.feat" --target score --score-clip 5000 \
        --l2 1e-5 --max-iter 150 --scale 1000 $anchor_args --out "$out" \
        > "$ART/${tag}-train.log" 2>&1
    # cleanup the big intermediate leaf/target files to save disk
    rm -f "$lv" "$lv.games" "$ART/${tag}-targets.jnnw" "$ART/${tag}-targets.feat"
    grep -E "val   :|wrote" "$ART/${tag}-train.log" | sed 's/^/    /'
}

rate_se () { grep -oE 'SCAN_EVAL score rate vs NNUE: [0-9.]+' "$1" | grep -oE '[0-9.]+$' | head -1; }
rate_sp () { grep -oE 'A score rate: [0-9.]+' "$1" | grep -oE '[0-9.]+$' | head -1; }

# Budget schedule per iteration : 1-2 = depth (vite), 3-5 = movetime (profond).
ITERS=5
budget_for () { # $1=iter → echoes "depth movetime ngames"
    if [ "$1" -le 2 ]; then echo "8 0 4000"; else echo "64 250 2000"; fi
}

run_arm () {  # $1 = arm name (pure|anchored)
    local arm="$1"; local model="$PRIOR"
    echo; echo "########## BRAS $arm ##########"
    for it in $(seq 1 $ITERS); do
        read -r d mt ng <<<"$(budget_for "$it")"
        local nxt="$ART/${arm}-v3-it${it}.pjtw"
        echo "--- $arm itération $it (depth=$d movetime=$mt) ---"
        tdleaf_iter "$model" "$nxt" "$arm" "$d" "$mt" "$ng" "$((100 + it))"
        [ -f "$nxt" ] || { echo "  (échec it$it, on garde le précédent)"; break; }
        model="$nxt"
    done
    echo "$model"  # final model path (last stdout line)
}

PURE_FINAL=$(run_arm pure     | tail -1)
ANCH_FINAL=$(run_arm anchored | tail -1)
echo; echo "pure final : $PURE_FINAL"; echo "anchored final : $ANCH_FINAL"

echo; echo "=== bench final vs v15 (depth 9 + movetime 0.3s) ==="
bench_vs_v15 () { # $1 model $2 label
    ./build-prod/jass --benchmark-scan-eval "$1" "$V15" 9  5 1 0   "$SPEC1B" > "$ART/$2-vs-v15-d9.log"  2>&1
    ./build-prod/jass --benchmark-scan-eval "$1" "$V15" 64 5 1 300 "$SPEC1B" > "$ART/$2-vs-v15-mt.log" 2>&1
    echo "  $2 : d9=$(rate_se "$ART/$2-vs-v15-d9.log")  mt=$(rate_se "$ART/$2-vs-v15-mt.log")"
}
bench_vs_v15 "$PRIOR"      prior
bench_vs_v15 "$PURE_FINAL" pure
bench_vs_v15 "$ANCH_FINAL" anchored

echo; echo "=========================================================="
echo "        0149 TD-LEAF FINE-TUNE — VERDICT (pur vs ancré)"
echo "=========================================================="
python3 - "$ART" <<'EOF'
import sys, math, re, glob, os
art=sys.argv[1]
def rate(p):
    try:
        t=open(p).read(); m=re.search(r'SCAN_EVAL score rate vs NNUE: ([0-9.]+)',t)
        return float(m.group(1)) if m else None
    except: return None
def elo(r): return 'n/a' if not r or not(0<r<1) else f'{-400*math.log10(1/r-1):+.0f}'
for lab in ('prior','pure','anchored'):
    d=rate(f'{art}/{lab}-vs-v15-d9.log'); m=rate(f'{art}/{lab}-vs-v15-mt.log')
    print(f'  {lab:9s} vs v15 : depth9={d}  (ELO {elo(d)})   movetime={m}  (ELO {elo(m)})')
print()
print('  → garder le bras qui bat le prior vs v15 en movetime (le régime réel).')
print('  → si aucun ne bat le prior : le fine-tuning self-play ne paie pas sur')
print('    cette archi → s’en tenir au prior distillé.')
EOF
echo "=========================================================="
