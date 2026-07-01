#!/usr/bin/env bash
# id: ccx33-0522-diag1-jass-decomp
# description: DIAG #1a (briefing localisateurs) — decomposition node-count de JASS a d1-d6, pour localiser si l'arbre gras
# vs Scan part des faibles profondeurs et PAR QUEL CANAL. Valide aussi le build DIAG #1 (PR #325) + jass_tests. Metriques
# par profondeur (via --search-profile instrumente) : N(d), multiplicateur N(d)/N(d-1), taux cutoff-1er (cut1/cutoffs =
# qualite ordering, un moteur sain ~85-95%), taux re-recherche (research/nodes = instabilite valeurs), coups/noeud
# (movessearched/nodes). LECTURE : cutoff-1er BAS + research HAUT => suspect structure/discrimination EVAL => justifie #2
# (port Scan-eval). multiplicateur qui explose des d2-d4 => inefficacite structurelle precoce (these JFC). AUCUN NNUE.
# (Scan cote = #1b : instrumenter le clone scan ; ici jass en absolu + son multiplicateur, deja tres parlant.)
# expected_duration: ~20 min
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0522-diag1-jass-decomp/artefacts"; mkdir -p "$ART"; W=/root/cw-d1; mkdir -p "$W"
CH=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz; DILF=data/dilf_combinations.fen; NFEN=40
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb"; tail -6 "$W/cmake.log"; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { echo "BUILD FAIL (DIAG#1 casse ?)"; tail -12 "$W/build.log"; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
echo "=== VALIDATION jass_tests (DIAG#1 passif => inchange) ==="
if cmake --build "$W/build" -j"$NCPU" --target jass_tests >"$W/tb.log" 2>&1 && "$W/build/jass_tests" >"$W/tests.log" 2>&1; then
  echo "  $(grep -iE 'assert|FAIL|pass' "$W/tests.log" | tail -1)"; else echo "  jass_tests : $(grep -iE FAIL "$W/tests.log"|tail -2)"; fi
git show "origin/main:$CH" | gunzip > "$W/champ.pjtw" || { echo "ABORT champ"; exit 4; }
grep -vE '^\s*#|^\s*$' "$DILF" | sed 's/#.*//' | head -$NFEN > "$W/fens.txt"
echo "=== DIAG #1 jass decomposition d1-d6 sur $(wc -l <"$W/fens.txt") FEN ===" | tee "$ART/VERDICT.txt"
python3 - "$J" "$W/champ.pjtw" "$W/fens.txt" <<'PY' | tee -a "$ART/VERDICT.txt"
import sys,subprocess,re
J,CH,FENS=sys.argv[1],sys.argv[2],sys.argv[3]
fens=[l.strip() for l in open(FENS) if l.strip()]
print(f"{'d':>2} {'N(d)':>10} {'mult':>6} {'cutoff1er%':>10} {'research%':>9} {'coups/noeud':>11}")
prevN=None
for d in range(1,7):
    tot={'nodes':0,'cutoffs':0,'cut1':0,'research':0,'ms':0}
    for f in fens:
        try:
            o=subprocess.run([J,"--search-profile",f,str(d),"0",CH,""],capture_output=True,text=True,timeout=30).stdout
            g=lambda k:int(re.search(k+r'=(\d+)',o).group(1)) if re.search(k+r'=(\d+)',o) else 0
            tot['nodes']+=g('nodes'); tot['cutoffs']+=g('cutoffs'); tot['cut1']+=g('cut1'); tot['research']+=g('research'); tot['ms']+=g('movessearched')
        except Exception: pass
    N=tot['nodes']; mult=(N/prevN) if prevN else 0
    c1=100*tot['cut1']/tot['cutoffs'] if tot['cutoffs'] else 0
    rs=100*tot['research']/N if N else 0; mn=tot['ms']/N if N else 0
    print(f"{d:>2} {N:>10} {mult:>6.2f} {c1:>10.1f} {rs:>9.2f} {mn:>11.2f}")
    prevN=N
print()
print("LECTURE : cutoff-1er% BAS (<~85 ?) => ordering faible = suspect discrimination EVAL => #2 (port Scan-eval).")
print("  research% HAUT => instabilite des valeurs (echelle/discrimination eval). multiplicateur qui monte des d2-d4 =>")
print("  inefficacite STRUCTURELLE precoce (these JFC etayee). Compare a Scan = #1b (instrumenter le clone). base : un")
print("  moteur alpha-beta sain a ~90%+ de cutoff-1er et un multiplicateur qui se tasse en profondeur.")
PY
echo "=== FIN 0522 ==="
