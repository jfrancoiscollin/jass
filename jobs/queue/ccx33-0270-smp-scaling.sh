#!/usr/bin/env bash
# id: ccx33-0270-smp-scaling
# description: MESURE du scaling lazy-SMP (pas de changement de code éval/search). À budget temps
# FIXE, combien de profondeur gagne-t-on avec 2/4/N threads vs 1 ? La PROFONDEUR atteinte est la
# bonne métrique (le total-nodes est trouble en lazy-SMP, les threads partagent la TT). Si le gain
# de profondeur est faible (<~+1 pli à 2 threads ≈ scaling <1.7×), on a de la force GRATUITE à
# récupérer sur multi-cœur. `--depth-at-movetime ... [threads]` (nouveau dernier arg). Éval 0227.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0270-smp-scaling/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
EVAL=""
for cand in /root/jass/jobs/results/ccx33-0227-fullfold-loop/artefacts.src/gen8.pjtw \
            /root/jass/jobs/results/ccx33-0231-rfe-baseline32/artefacts.src/gen8.pjtw; do
  [ -f "$cand" ] && { EVAL="$cand"; break; }
done
[ -n "$EVAL" ] || { echo "ABORT: éval 0227 introuvable"; exit 6; }
echo "nproc=$NCPU  EVAL=$EVAL"

# profondeur atteinte à budget fixe (1s), TT généreuse (256MB), à 1/2/4/NCPU threads
measure(){ local TH=$1 MT=$2
  # netA=EVAL netB=hc (on ne lit que la ligne A) ; spec vide ; threads=TH
  $JASS --depth-at-movetime "$EVAL" hc "$MT" 256 "" "$TH" 2>"$ART/err-$TH-$MT.log" | tee "$ART/dm-$TH-$MT.log" >/dev/null
  local d=$(grep -E 'depth avg' "$ART/dm-$TH-$MT.log" | head -1 | grep -oE 'depth avg=[0-9.]+' | cut -d= -f2)
  local k=$(grep -E 'knps~' "$ART/dm-$TH-$MT.log" | head -1 | grep -oE 'knps~[0-9.]+' | cut -d~ -f2)
  echo "$d|$k"
}
echo "=========================================================="
echo "   ccx33-0270 — SCALING LAZY-SMP (profondeur à budget fixe, éval=$(basename "$EVAL"))"
echo "----------------------------------------------------------"
for MT in 1000; do
  echo "  --- movetime=${MT}ms ---"
  BASE=""; for TH in 1 2 4 "$NCPU"; do
    R=$(measure "$TH" "$MT"); D=${R%%|*}; K=$(echo "$R"|cut -d'|' -f2)
    [ -z "$BASE" ] && BASE="$D"
    GAIN=$(awk -v d="$D" -v b="$BASE" 'BEGIN{printf "%+.2f", d-b}')
    echo "    threads=$TH  depth=$D  (Δ vs 1thr=$GAIN plies)  knps~$K"
  done
done
echo "----------------------------------------------------------"
echo "  Δprofondeur 2 threads ≳ +0.8-1 pli → scaling correct. ≲ +0.3 → scaling FAIBLE :"
echo "    force gratuite à récupérer (le lazy-SMP partage mal / contention TT). NB knps total"
echo "    est indicatif seulement (lazy-SMP : nodes du searcher principal, pas la somme)."
echo "=========================================================="
