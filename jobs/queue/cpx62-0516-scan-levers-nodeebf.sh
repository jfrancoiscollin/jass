#!/usr/bin/env bash
# id: cpx62-0516-scan-levers-nodeebf
# description: LEVIERS SCAN (memo JFC, lus dans rhalbersma/scan) — validation + node-EBF EXACT. (a) VALIDE le build +
# jass_tests (defauts byte-identiques : ext_single_reply=0, lmr_first_full_pv=nonpv=4). (b) node-EBF paired (--search-profile,
# d12 = fenetre milieu) : ref=baseline vs (1) ext_single_reply=1 (extension ETROITE largeur-1 : node-ratio doit rester ~1 =
# PEU de noeuds ajoutes => "forcing gratuit" ; sa VALEUR combo se teste a movetime, pas ici), (2) LMR asym nonpv=1,pv=3
# (reduit plus tot aux noeuds cut : node-ratio doit BAISSER <1 = le vrai levier EBF 1,6->1,25), (3) les deux. + accord
# best-move vs baseline. GATE : asym ratio<1 hors-bruit => candidat EBF => A/B Elo (#2). single-reply ~1 noeuds => cheap =>
# A/B movetime (le WIN test #1, 3 bras vs ext_forcing large). AUCUN NNUE. Rapide (~15min).
# expected_duration: ~20 min
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0516-scan-levers-nodeebf/artefacts"; mkdir -p "$ART"
W=/root/cw-scl; mkdir -p "$W"
CH=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
DILF=data/dilf_combinations.fen; NFEN=120; DEPTH=12
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb build"; tail -6 "$W/cmake.log"; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { echo "BUILD FAIL (src scan-levers casse ?)"; tail -12 "$W/build.log"; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
echo "=== VALIDATION : jass_tests (defauts byte-identiques) ==="
if cmake --build "$W/build" -j"$NCPU" --target jass_tests >"$W/tb.log" 2>&1 && "$W/build/jass_tests" >"$W/tests.log" 2>&1; then
  echo "  jass_tests : $(grep -iE 'assert|pass|FAIL|all' "$W/tests.log" | tail -1)"
else echo "  ⚠️ jass_tests : $(grep -iE 'FAIL' "$W/tests.log" | tail -3)"; fi
git cat-file -e "origin/main:$CH" 2>/dev/null && git show "origin/main:$CH" | gunzip > "$W/champ.pjtw" || { echo "ABORT champion absent"; exit 4; }
grep -vE '^\s*#|^\s*$' "$DILF" | sed 's/#.*//' | head -$NFEN > "$W/fens.txt"
echo "=== node-EBF leviers Scan : $(wc -l <"$W/fens.txt") FEN @ d$DEPTH ===" | tee "$ART/VERDICT.txt"
python3 - "$J" "$W/champ.pjtw" "$W/fens.txt" "$DEPTH" <<'PY' | tee -a "$ART/VERDICT.txt"
import sys,subprocess,statistics as st,re
J,CH,FENS,D=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4]
fens=[l.strip() for l in open(FENS) if l.strip()]
def probe(fen,spec):
    try:
        o=subprocess.run([J,"--search-profile",fen,D,"0",CH,spec],capture_output=True,text=True,timeout=30).stdout
        m=re.search(r'nodes=(\d+)\s+bestmove=(\S+)',o); return (int(m.group(1)),m.group(2)) if m else (None,None)
    except Exception: return (None,None)
ref={f:probe(f,"") for f in fens}; ref={f:v for f,v in ref.items() if v[0]}
print(f"baseline : {len(ref)} FEN, median nodes={st.median([v[0] for v in ref.values()]):.0f}")
CFG={"single_reply":"ext_single_reply=1",
     "lmr_asym_1_3":"lmr_first_full_nonpv=1,lmr_first_full_pv=3",
     "both":"ext_single_reply=1,lmr_first_full_nonpv=1,lmr_first_full_pv=3"}
print(f"\n{'config':>14} | {'node_ratio':>10} {'accord_bm':>9}  (vs baseline)")
for name,spec in CFG.items():
    rr=[]; ag=0; n=0
    for f in ref:
        nodes,bm=probe(f,spec)
        if nodes is None: continue
        rr.append(nodes/ref[f][0]); ag+=(bm==ref[f][1]); n+=1
    if n: print(f"{name:>14} | {st.median(rr):>10.3f} {ag/n:>9.3f}")
print()
print("LECTURE : lmr_asym ratio<1 (hors bruit) ET accord~1 => REDUIT l'arbre sans changer les decisions => candidat EBF")
print("  gratuit => A/B Elo movetime + balayer (nonpv,pv). single_reply : ratio~1 (peu de noeuds, EXTENSION largeur-1 cheap)")
print("  + accord<1 sur les lignes forcees = il cherche plus profond la (= combos) => sa valeur = A/B MOVETIME (WIN test #1,")
print("  3 bras : baseline vs single_reply vs ext_forcing LARGE=neutre 0,473). Si single_reply>baseline & >ext_forcing => BAKE.")
PY
echo "=== FIN 0516 ==="
