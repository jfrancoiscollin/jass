#!/usr/bin/env bash
# id: cpx62-0514-boxcox-search
# description: RECHERCHE DE FORME LMR (Box-Cox, idee JFC) — au lieu de tester des formules fixes (le log a echoue),
# on optimise la forme R=BC_ld(d)*BC_lidx(idx)*mul/100 sur une grille (lmr_formula=2, PR #323). CRITERE EXACT sans games :
# pour chaque forme, mesurer en NODE-COUNT exact (--search-profile, d12 = la fenetre milieu qui explose) : (a) ratio de
# noeuds vs le LINEAIRE de reference, (b) taux d'ACCORD du best-move avec le lineaire. Une forme avec ratio<1 (reduit
# l'arbre) ET accord~1 (ne change pas les decisions) = compression GRATUITE => gain EBF. On cherche les formes qui
# DOMINENT le lineaire sur (ratio bas, accord haut). Aucune => l'EBF est structurel, prouve sur toute la famille (pas juste
# 5 muls a la main). Le gagnant sera ensuite valide en Elo movetime. Rapide (~10min). AUCUN NNUE, AUCUN re-entrainement.
# expected_duration: ~20 min
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0514-boxcox-search/artefacts"; mkdir -p "$ART"
W=/root/cw-bc; mkdir -p "$W"
CH=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
DILF=data/dilf_combinations.fen; NFEN=120; DEPTH=12
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb build"; tail -6 "$W/cmake.log"; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { echo "BUILD FAIL (src Box-Cox casse ?)"; tail -12 "$W/build.log"; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
git cat-file -e "origin/main:$CH" 2>/dev/null && git show "origin/main:$CH" | gunzip > "$W/champ.pjtw" || { echo "ABORT champion absent"; exit 4; }
grep -vE '^\s*#|^\s*$' "$DILF" | sed 's/#.*//' | head -$NFEN > "$W/fens.txt"
echo "=== Box-Cox shape search : $(wc -l <"$W/fens.txt") FEN @ d$DEPTH ==="
python3 - "$J" "$W/champ.pjtw" "$W/fens.txt" "$DEPTH" <<'PY' | tee "$ART/VERDICT.txt"
import sys,subprocess,statistics as st,re
J,CH,FENS,D=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4]
fens=[l.strip() for l in open(FENS) if l.strip()]
def probe(fen,spec):
    try:
        out=subprocess.run([J,"--search-profile",fen,D,"0",CH,spec],capture_output=True,text=True,timeout=30).stdout
        m=re.search(r'nodes=(\d+)\s+bestmove=(\S+)',out)
        return (int(m.group(1)),m.group(2)) if m else (None,None)
    except Exception: return (None,None)
# reference = lineaire (lmr_formula=0)
ref={f:probe(f,"lmr_formula=0") for f in fens}
ref={f:v for f,v in ref.items() if v[0]}
print(f"reference lineaire : {len(ref)} FEN OK, median nodes={st.median([v[0] for v in ref.values()]):.0f}")
# grille Box-Cox : lmr_bc_ld (depth exp x100), lmr_bc_lidx (index exp x100), lmr_log_mul
LD=[0,50,100,150]; LIDX=[0,50,100]; MUL=[40,80]
rows=[]
for ld in LD:
 for lidx in LIDX:
  for mul in MUL:
    spec=f"lmr_formula=2,lmr_bc_ld={ld},lmr_bc_lidx={lidx},lmr_log_mul={mul}"
    ratios=[]; agree=0; n=0
    for f in ref:
        nodes,bm=probe(f,spec)
        if nodes is None: continue
        ratios.append(nodes/ref[f][0]); agree+= (bm==ref[f][1]); n+=1
    if n:
        rr=st.median(ratios); ag=agree/n
        rows.append((rr,ag,ld,lidx,mul,n))
rows.sort()  # ratio croissant
print(f"\n{'ld':>4}{'lidx':>5}{'mul':>5} | {'node_ratio':>10} {'accord_bm':>9}  (vs lineaire ; ratio<1 = reduit l'arbre)")
dom=[]
for rr,ag,ld,lidx,mul,n in rows:
    flag=" <== DOMINE (ratio<0.92 & accord>0.90)" if (rr<0.92 and ag>0.90) else ""
    if flag: dom.append((rr,ag,ld,lidx,mul))
    print(f"{ld:>4}{lidx:>5}{mul:>5} | {rr:>10.3f} {ag:>9.3f}{flag}")
print()
if dom:
    b=min(dom)
    print(f"GAGNANT : ld={b[2]} lidx={b[3]} mul={b[4]} => node_ratio={b[0]:.3f} accord={b[1]:.3f} => forme qui REDUIT l'arbre")
    print(f"  SANS changer les decisions => gain EBF gratuit candidat => valider en Elo movetime + vs Scan, puis baker.")
else:
    print("AUCUNE forme ne domine le lineaire (ratio<0.92 & accord>0.90) sur d12 => l'EBF est STRUCTUREL, prouve sur toute")
    print("  la famille Box-Cox (pas juste 5 muls a la main) => la forme LMR n'est definitivement pas le levier. Clore.")
PY
echo "=== FIN 0514 ==="
