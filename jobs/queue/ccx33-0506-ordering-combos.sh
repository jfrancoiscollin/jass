#!/usr/bin/env bash
# id: ccx33-0506-ordering-combos
# description: PISTE ORDERING (le levier EBF sur du calme, cout Elo zero) — mesure l'EBF PAR FENETRE sous des knobs
# d'ordering, vs baseline. Constat (#0/v2) : tout le deficit movetime est l'EBF, concentre en d9-d12 (jass 1,79 vs Scan
# 1,17 ; au fond l'ecart se referme). En dames les captures sont forcees => ce sont les coups CALMES qui font l'arbre =>
# l'EBF = qualite de l'ordering des calmes au milieu. DECOUVERTE : iid_min_depth=0 (IID DESACTIVE) — or l'IID est LE fix
# textbook pour les noeuds sans coup-TT (frequents au milieu en dames, peu de transpositions). On mesure R(d) d9/12/15 +
# EBF PAR FENETRE pour : baseline, IID{4,6,8}, hist_malus, conthist. Si un config baisse l'EBF d9->d12 (la fenetre qui
# explose) => candidat ordering => ensuite A/B Elo (l'ordering ne change PAS quels coups on cherche, juste l'ordre =>
# coupures plus tot => EBF bas SANS risque tactique, contrairement a l'elagage 0264/0268). nps_vs_scan --jass-search-params
# (PR #320). eval-pur egdbmix. AUCUN re-entrainement, AUCUN NNUE, AUCUN changement de code (tout via search-params).
# expected_duration: ~30-45 min
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-90}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0506-ordering-combos/artefacts"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
W=/root/cw-ord; mkdir -p "$W"
POS=/root/jass/jobs/results/ccx33-0328-scan-selfplay-corpus/artefacts/scan-selfplay-corpus.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
CH=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz

preflight_build 1
preflight_note "ORDERING EBF : R(d) x6 configs (baseline+IID4/6/8+malus+conthist)" 70
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
B="$W/build"; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb off"; tail -8 "$W/cmake.log"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$W/build.log" 2>&1 || { echo "BUILD FAIL"; tail -12 "$W/build.log"; exit 6; }
JASS="$B/jass"
git cat-file -e "origin/main:$CH" 2>/dev/null && git show "origin/main:$CH" | gunzip > "$W/champ.pjtw" || { echo "ABORT champion absent"; exit 4; }
[ -f "$POS" ] || { echo "ABORT corpus 0328 absent"; exit 4; }
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT Scan indispo"; exit 5; }

echo "=== ORDERING EBF — R(d) par fenetre (baseline #0 : EBF 1,79 d9-12 / 1,59 d12-15 ; Scan 1,17 / 1,34) ==="
declare -A SPEC=( [baseline]="iid_min_depth=0" [iid8]="iid_min_depth=8" [conthist]="use_conthist=1" [iid6_ch]="iid_min_depth=6,use_conthist=1" [iid8_ch]="iid_min_depth=8,use_conthist=1" )
for cfg in baseline iid8 conthist iid6_ch iid8_ch; do
  echo "--- config=$cfg (${SPEC[$cfg]}) ---"
  python3 tools/nps_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" \
      --jass-search-params "${SPEC[$cfg]}" --positions "$POS" --n 40 --depths 9,12,15 --min-pieces 14 \
      2>&1 | tee "$W/nps-$cfg.log"
done

echo ""; echo "=== EBF PAR FENETRE + R(15) par config ==="
python3 - "$W" baseline iid8 conthist iid6_ch iid8_ch <<'PY'
import sys,re
Wd=sys.argv[1]; cfgs=sys.argv[2:]
def parse(c):
    rows={}
    for ln in open(f"{Wd}/nps-{c}.log",errors='ignore'):
        m=re.match(r'\s*(\d+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)',ln)
        if m: rows[int(m.group(1))]=(float(m.group(2)),float(m.group(3)),float(m.group(4)))
    return rows
def ebf(rows,a,b): return (rows[b][0]/rows[a][0])**(1/(b-a)) if a in rows and b in rows else float('nan')
print(f"{'config':>9} {'EBF d9-12':>10} {'EBF d12-15':>11} {'R(15)':>7}")
base=None
for c in cfgs:
    r=parse(c)
    if not(9 in r and 12 in r and 15 in r): print(f"{c:>9}  incomplet"); continue
    e1=ebf(r,9,12); e2=ebf(r,12,15); R15=r[15][2]
    if c=='baseline': base=(e1,e2,R15)
    tag=""
    if base and c!='baseline':
        d1=(e1/base[0]-1)*100; dR=(R15/base[2]-1)*100
        tag=f"  d9-12 {d1:+.1f}% | R15 {dR:+.1f}%"
    print(f"{c:>9} {e1:>10.3f} {e2:>11.3f} {R15:>7.2f}{tag}")
print()
print("LECTURE : un config avec EBF d9-12 NETTEMENT < baseline (la fenetre qui explose) => l'ordering attaque le bon endroit")
print("          => candidat. Surtout IID (cible les noeuds sans coup-TT). Ensuite A/B Elo (doit etre >= baseline : l'ordering")
print("          ne change pas QUELS coups, juste l'ordre => zero risque, contrairement a l'elagage). EBF inchange partout =>")
print("          l'ordering n'est pas le frein (alors c'est l'elagage-shape ou structurel) => re-orienter.")
PY
echo "=================================================="
