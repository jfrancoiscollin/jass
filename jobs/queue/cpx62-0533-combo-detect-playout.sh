#!/usr/bin/env bash
# id: cpx62-0533-combo-detect-playout
# description: DÉTECTION COMBOS v2 — métrique PLAYOUT (demande JFC). 0529/0531 mesuraient le match EXACT du coup de Scan
# (sous-estime : jass peut jouer un AUTRE coup gagnant). Ici : jass joue son coup à profondeur d ; l'ORACLE (Scan-deep)
# vérifie si le camp au trait GAGNE TOUJOURS (≥+1 homme forcé) après ce coup => détection RÉELLE, indépendante du coup exact.
# 3 configs : élagage ON, élagage OFF, ext_forcing (l'EXTENSION que 0531 n'avait pas testée — 0483 la disait efficace).
# Réutilise la suite gradée par tempi de 0531. LECTURE : playout >> move-match => c'était la métrique ; ext_forcing >> ON =>
# extension manquante (réparable) ; tout reste bas => vraie cécité tactique. AUCUN NNUE. expected_duration: ~1-2 h.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0533-combo-detect-playout/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-detplayout; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
CHAMP_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
SUITE_SRC="jobs/results/cpx62-0531-combo-scaleup/artefacts/combos_graded.fen"
ORACLE_DEEP=13; MAXTEMPI=12; GAIN=1; TEST_DEPTH=20

say "=== DÉTECTION COMBOS v2 (playout) ==="
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/sc.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null||true; }
[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable"; exit 5; }
git show "origin/main:$CHAMP_GZ" | gunzip > "$W/champ.pjtw" || { say "ABORT champ"; exit 4; }
git show "origin/main:$SUITE_SRC" > "$W/suite.fen" 2>/dev/null || { say "ABORT: suite 0531 absente"; exit 4; }
say "  suite : $(grep -cvE '^\s*(#|$)' "$W/suite.fen") combos"

export JASS="$J" CHAMP="$W/champ.pjtw" SCAN="$SCAN_BIN" SUITE="$W/suite.fen" \
       DEEP="$ORACLE_DEEP" MAXT="$MAXTEMPI" GAIN="$GAIN" TD="$TEST_DEPTH"
python3 - <<'PY' 2>&1 | tee -a "$RES"
import os,sys,re
sys.path.insert(0,'tools')
from gen_combinations import ScanOracle
from calibrate_vs_scan import JassEngine
J=os.environ["JASS"]; CH=os.environ["CHAMP"]; SCAN=os.environ["SCAN"]; SUITE=os.environ["SUITE"]
DEEP=int(os.environ["DEEP"]); MAXT=int(os.environ["MAXT"]); GAIN=int(os.environ["GAIN"]); TD=int(os.environ["TD"])

combos=[]
for ln in open(SUITE):
    if '#' not in ln: continue
    fen,meta=ln.split('#',1); fen=fen.strip(); m=dict(re.findall(r'(\w+)=([^\s]+)',meta))
    if 'tempi' in m and m.get('win'): combos.append((fen,int(m['tempi']),m['win']))
print(f"  {len(combos)} combos ; oracle Scan d{DEEP} ; test à d{TD}")

oracle=ScanOracle(SCAN, J, deep=DEEP)   # oracle (Scan) + referee (jass) for applying moves + forced lines

def playout_wins(jass_eng, fen, depth):
    """jass joue son coup à `depth` ; l'oracle confirme si le camp au trait GAGNE encore (≥GAIN forcé)."""
    jass_eng.set_position_fen(fen)
    m=jass_eng.go(depth=depth)
    if m is None: return (False, False)
    exact = (m.jass_str()==WIN_HOLDER[0])
    oracle.ref.set_position_fen(fen)
    if not oracle.ref.apply_move(m): return (False, exact)
    new_fen=oracle.ref.current_fen()
    net,_=oracle.forced_line(new_fen, MAXT)      # opponent-POV net trajectory after jass's move
    return (bool(net) and net[-1] <= -GAIN, exact)   # opponent ends down => original mover still wins

CFG={'ON':'', 'OFF':'multicut_min_depth=0,razor_max_depth=0,lmp_min_depth=0', 'ext_forcing':'ext_forcing=1,forcing_ext_cap=6'}
# aggregate per tempi : playout-detection per config + exact-match (ON) for reference
from collections import defaultdict
pl=defaultdict(lambda: defaultdict(lambda:[0,0]))   # pl[tempi][cfg]=[hits,n]
ex=defaultdict(lambda:[0,0])                          # exact-match @ ON
engs={k:(JassEngine(J,pattern_path=CH,no_book=True,search_params=v) if v else JassEngine(J,pattern_path=CH,no_book=True)) for k,v in CFG.items()}
WIN_HOLDER=[""]
for fen,t,win in combos:
    WIN_HOLDER[0]=win
    for k,eng in engs.items():
        won,exact=playout_wins(eng, fen, TD)
        pl[t][k][0]+=won; pl[t][k][1]+=1
        if k=='ON': ex[t][0]+=exact; ex[t][1]+=1
for e in engs.values():
    try: e.close()
    except Exception: pass
oracle.close()
def r(hn): return "n/a" if not hn[1] else f"{hn[0]/hn[1]:.2f}"
print(f"\n  {'tempi':>5} {'n':>4} | {'PLAYOUT ON':>10} {'PLAYOUT OFF':>11} {'PLAYOUT extF':>12} | {'exact ON':>9}   (tous à d{TD})")
tot=defaultdict(lambda:[0,0]); totex=[0,0]
for t in sorted(pl):
    row=pl[t]
    for k in CFG: tot[k][0]+=row[k][0]; tot[k][1]+=row[k][1]
    totex[0]+=ex[t][0]; totex[1]+=ex[t][1]
    print(f"  {t:>5} {row['ON'][1]:>4} | {r(row['ON']):>10} {r(row['OFF']):>11} {r(row['ext_forcing']):>12} | {r(ex[t]):>9}")
print(f"  {'TOT':>5} {tot['ON'][1]:>4} | {r(tot['ON']):>10} {r(tot['OFF']):>11} {r(tot['ext_forcing']):>12} | {r(totex):>9}")
PY

say ""
say "================= LECTURE ================="
say "  PLAYOUT ON >> exact ON  => 0529/0531 sous-estimaient (jass gagne via un AUTRE coup) : moins grave qu'il semblait."
say "  PLAYOUT extF >> PLAYOUT ON => l'EXTENSION forçante récupère les combos => levier recherche réel (baker au jeu)."
say "  PLAYOUT reste bas partout => vraie cécité tactique (au-delà de l'extension/élagage) => piste recherche + curriculum."
say "==========================================="
