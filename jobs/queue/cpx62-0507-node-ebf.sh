#!/usr/bin/env bash
# id: cpx62-0507-node-ebf
# description: MESURE EBF PAR NOEUDS (exacte) — corrige le bruit fatal de l'EBF-par-temps (0504 vs 0506 contredits, +-11%
# sur baseline => incapable de detecter ~6%). Les node-counts a profondeur fixe sont EXACTS/deterministes. On utilise
# --search-profile <fen> <depth> 0 <eval> <search-params> (commit 24ef71dc6) pour compter les noeuds sous chaque knob
# d'ordering, PAIRED (memes positions => ratio nodes_knob/nodes_baseline direct, variance-position annulee). Si iid/conthist
# baissent vraiment l'arbre (surtout en d12, la fenetre milieu), le ratio median < 1. Rappel : ces knobs sont Elo-NEUTRES
# (0505 n=610) => un ratio<1 = gain EBF GRATUIT. ratio~1 partout => l'ordering ne bouge pas l'arbre (le 0504 etait du bruit)
# => le LMR-shape ET l'ordering sont des impasses EBF => re-orienter. AUCUN NNUE, build valide le src --search-profile.
# expected_duration: ~20-30 min
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0507-node-ebf/artefacts"; mkdir -p "$ART"
W=/root/cw-nebf; mkdir -p "$W"
CH=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
DILF=data/dilf_combinations.fen; NFEN=40; DEPTHS="9 12 15"

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb build"; tail -6 "$W/cmake.log"; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { echo "BUILD FAIL (src --search-profile casse ?)"; tail -12 "$W/build.log"; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
git cat-file -e "origin/main:$CH" 2>/dev/null && git show "origin/main:$CH" | gunzip > "$W/champ.pjtw" || { echo "ABORT champion absent"; exit 4; }
# echantillon de FEN dilf
grep -vE '^\s*#|^\s*$' "$DILF" | sed 's/#.*//' | head -$NFEN > "$W/fens.txt"
echo "=== node-EBF : $(wc -l <"$W/fens.txt") FEN x depths {$DEPTHS} x configs ==="

declare -A SPEC=( [baseline]="" [iid6]="iid_min_depth=6" [iid8]="iid_min_depth=8" [conthist]="use_conthist=1" )
# nodes[$cfg,$d,$i] -> on stocke en fichiers
for cfg in baseline iid6 iid8 conthist; do
  for d in $DEPTHS; do
    : > "$W/n-$cfg-$d.txt"
    while IFS= read -r fen; do
      [ -z "$fen" ] && continue
      n=$("$J" --search-profile "$fen" "$d" 0 "$W/champ.pjtw" "${SPEC[$cfg]}" 2>/dev/null | grep -oE 'nodes=[0-9]+' | head -1 | cut -d= -f2)
      echo "${n:-0}" >> "$W/n-$cfg-$d.txt"
    done < "$W/fens.txt"
  done
  echo "  $cfg fait"
done

echo "=== RATIOS PAIRED (median nodes_knob/nodes_baseline par depth) + node-EBF ===" | tee "$ART/VERDICT.txt"
python3 - "$W" <<'PY' | tee -a "$ART/VERDICT.txt"
import statistics as st
W=__import__('sys').argv[1]
def col(cfg,d): return [int(x) for x in open(f"{W}/n-{cfg}-{d}.txt").read().split() if x.strip()]
depths=[9,12,15]; cfgs=["baseline","iid6","iid8","conthist"]
base={d:col("baseline",d) for d in depths}
# node-EBF baseline (median per-position EBF d9->d15)
def ebf(cfg,a,b):
    A=col(cfg,a); B=col(cfg,b); rs=[(y/x)**(1/(b-a)) for x,y in zip(A,B) if x>0]
    return st.median(rs) if rs else float('nan')
print(f"{'config':>9} | {'EBFn d9-12':>10} {'EBFn d12-15':>11} | {'ratio@d12':>9} {'ratio@d15':>9}  (vs baseline, median)")
for cfg in cfgs:
    e1=ebf(cfg,9,12); e2=ebf(cfg,12,15)
    if cfg=="baseline":
        print(f"{cfg:>9} | {e1:>10.3f} {e2:>11.3f} | {'1.000':>9} {'1.000':>9}")
        continue
    r12=st.median([b/a for a,b in zip(base[12],col(cfg,12)) if a>0])
    r15=st.median([b/a for a,b in zip(base[15],col(cfg,15)) if a>0])
    print(f"{cfg:>9} | {e1:>10.3f} {e2:>11.3f} | {r12:>9.3f} {r15:>9.3f}")
print()
print("LECTURE (EXACTE, sans bruit) : ratio@d12 < 1 => le knob reduit VRAIMENT l'arbre au milieu => gain EBF gratuit")
print("(Elo neutre, 0505) => baker. ratio ~1.0 partout => l'ordering ne bouge pas l'arbre (0504 etait du bruit) => l'EBF")
print("n'est reductible NI par LMR-shape NI par ordering => le levier recherche est clos, re-orienter (ext_forcing regime / gen).")
PY
echo "=== FIN 0507 ==="
