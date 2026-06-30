#!/usr/bin/env bash
# id: cpx62-0510-evalbound-nodeebf
# description: CLOTURE chantier recherche : (a) VALIDE le bake conthist (build + jass_tests sur main avec use_conthist=true)
# (b) test EVAL-BOUND en node-EBF EXACT. Tous les leviers search sont epuises (LMR-shape non, IID zero, ext_forcing clos,
# TT deja 4-way, conthist=seul gain modeste). Reste a confirmer POURQUOI l'EBF (~1,7 vs Scan 1,25) est coince : structurel
# ou EVAL-BOUND ? Mesure node-counts (exact, --search-profile) sous eval FAIBLE (hc handcrafted) vs FORTE (egdbmix), memes
# FEN, paired. Si egdbmix << hc en noeuds => une meilleure eval = moins de noeuds => EBF EVAL-BOUND => l'EBF gap ET le gap
# de conversion (0,52 vs Scan 0,95) sont LE MEME probleme (l'eval) => ameliorer l'eval baisse l'EBF en bonus => pivot eval
# pleinement justifie. Si egdbmix ~ hc => EBF structurel independant de l'eval. AUCUN NNUE de jeu, AUCUN re-entrainement.
# expected_duration: ~20-30 min
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0510-evalbound-nodeebf/artefacts"; mkdir -p "$ART"
W=/root/cw-ebnd; mkdir -p "$W"
CH=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
DILF=data/dilf_combinations.fen; NFEN=40; DEPTHS="9 12 15"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb build"; tail -6 "$W/cmake.log"; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { echo "BUILD FAIL (bake conthist casse ?)"; tail -12 "$W/build.log"; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
echo "=== VALIDATION bake conthist : jass_tests ==="
if cmake --build "$W/build" -j"$NCPU" --target jass_tests >"$W/tb.log" 2>&1 && "$W/build/jass_tests" >"$W/tests.log" 2>&1; then
  echo "  jass_tests VERTS (conthist=true OK) : $(grep -iE 'assert|pass|all|test' "$W/tests.log" | tail -1)"
else echo "  ⚠️ jass_tests ECHEC avec conthist=true : $(tail -3 "$W/tests.log")"; fi
git cat-file -e "origin/main:$CH" 2>/dev/null && git show "origin/main:$CH" | gunzip > "$W/champ.pjtw" || { echo "ABORT champion absent"; exit 4; }
grep -vE '^\s*#|^\s*$' "$DILF" | sed 's/#.*//' | head -$NFEN > "$W/fens.txt"
echo "=== EVAL-BOUND node-EBF : $(wc -l <"$W/fens.txt") FEN x {$DEPTHS} x {hc, egdbmix} ==="
declare -A EV=( [hc]="hc" [egdbmix]="$W/champ.pjtw" )
for ev in hc egdbmix; do
  for d in $DEPTHS; do
    : > "$W/n-$ev-$d.txt"
    while IFS= read -r fen; do [ -z "$fen" ] && continue
      n=$("$J" --search-profile "$fen" "$d" 0 "${EV[$ev]}" 2>/dev/null | grep -oE 'nodes=[0-9]+' | head -1 | cut -d= -f2)
      echo "${n:-0}" >> "$W/n-$ev-$d.txt"
    done < "$W/fens.txt"
  done
  echo "  $ev fait"
done
echo "=== EBF eval-bound (median ratio nodes egdbmix/hc, exact) ===" | tee "$ART/VERDICT.txt"
python3 - "$W" <<'PY' | tee -a "$ART/VERDICT.txt"
import statistics as st, sys
W=sys.argv[1]
def col(ev,d): return [int(x) for x in open(f"{W}/n-{ev}-{d}.txt").read().split() if x.strip()]
for d in [9,12,15]:
    hc=col("hc",d); eg=col("egdbmix",d)
    rs=[e/h for h,e in zip(hc,eg) if h>0]
    print(f"  d{d}: median nodes hc={st.median(hc):.0f} egdbmix={st.median(eg):.0f} | ratio egdbmix/hc = {st.median(rs):.3f}")
print()
print("LECTURE : ratio egdbmix/hc NETTEMENT <1 => eval forte = moins de noeuds => EBF EVAL-BOUND => l'eval est LE levier")
print("(baisse l'EBF ET la conversion) => pivot eval justifie/unifie. ratio ~1 => EBF structurel, independant de l'eval.")
PY
echo "=== FIN 0510 ==="
