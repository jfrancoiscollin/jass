#!/usr/bin/env bash
# id: cpx62-0535-combo-detect-playout2
# description: DÉTECTION COMBOS v2 (playout) — RELANCE de 0533 (crash : jass go depth=20 > timeout HUB 60s, masqué par | tee).
# FIX : test à MOVETIME (attente bornée, "donne-lui du temps réel") + fixe court d12 ; FAIL-LOUD (vérifie la table produite) ;
# sous-échantillon BALANCÉ par tempi pour tenir en ~30 min. Métrique PLAYOUT : jass joue -> l'oracle confirme si le camp au
# trait gagne encore (≥+1 forcé) => détection RÉELLE (pas match exact). 3 configs : ON / élagage-OFF / ext_forcing. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0535-combo-detect-playout2/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-detpl2; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
CHAMP_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
SUITE_SRC="jobs/results/cpx62-0534-combo-gen-balanced/artefacts/combos_balanced.fen"
ORACLE_DEEP=13; MAXTEMPI=12; GAIN=1; MOVETIME=3.0; DSHALLOW=12; SUBN_PER_BIN=30

say "=== DÉTECTION COMBOS v2 (playout, movetime=${MOVETIME}s) ==="
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/sc.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null||true; }
[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable"; exit 5; }
git show "origin/main:$CHAMP_GZ" | gunzip > "$W/champ.pjtw" || { say "ABORT champ"; exit 4; }
git show "origin/main:$SUITE_SRC" > "$W/suite.fen" 2>/dev/null || { say "ABORT: suite 0534 absente"; exit 4; }
say "  suite : $(grep -cvE '^\s*(#|$)' "$W/suite.fen") combos (avant sous-échantillon)"

export JASS="$J" CHAMP="$W/champ.pjtw" SCAN="$SCAN_BIN" SUITE="$W/suite.fen" TABLE="$ART/detection.txt" \
       DEEP="$ORACLE_DEEP" MAXT="$MAXTEMPI" GAIN="$GAIN" MT="$MOVETIME" DSH="$DSHALLOW" SUBN="$SUBN_PER_BIN"
set +e
python3 - <<'PY' 2>&1 | tee -a "$RES"
import os,sys,re,collections
sys.path.insert(0,'tools')
from gen_combinations import ScanOracle
from calibrate_vs_scan import JassEngine
J=os.environ["JASS"]; CH=os.environ["CHAMP"]; SCAN=os.environ["SCAN"]; SUITE=os.environ["SUITE"]; TABLE=os.environ["TABLE"]
DEEP=int(os.environ["DEEP"]); MAXT=int(os.environ["MAXT"]); GAIN=int(os.environ["GAIN"])
MT=float(os.environ["MT"]); DSH=int(os.environ["DSH"]); SUBN=int(os.environ["SUBN"])
byt=collections.defaultdict(list)
for ln in open(SUITE):
    if '#' not in ln: continue
    fen,meta=ln.split('#',1); fen=fen.strip(); m=dict(re.findall(r'(\w+)=([^\s]+)',meta))
    if 'tempi' in m and m.get('win'): byt[int(m['tempi'])].append((fen,m['win']))
combos=[]
for t in sorted(byt): combos += [(fen,t,win) for fen,win in byt[t][:SUBN]]
print(f"  {len(combos)} combos (≤{SUBN}/bin) ; oracle Scan d{DEEP} ; movetime {MT}s + fixe d{DSH}", flush=True)
oracle=ScanOracle(SCAN, J, deep=DEEP); WIN=[""]
def keeps_win(eng, fen, depth=None, movetime=None):
    eng.set_position_fen(fen)
    m=eng.go(depth=depth, movetime=movetime)
    if m is None: return (False,False)
    exact=(m.jass_str()==WIN[0])
    oracle.ref.set_position_fen(fen)
    if not oracle.ref.apply_move(m): return (False,exact)
    net,_=oracle.forced_line(oracle.ref.current_fen(), MAXT)
    return (bool(net) and net[-1] <= -GAIN, exact)
CFG={'ON':'', 'OFF':'multicut_min_depth=0,razor_max_depth=0,lmp_min_depth=0', 'extF':'ext_forcing=1,forcing_ext_cap=6'}
engs={k:(JassEngine(J,pattern_path=CH,no_book=True,search_params=v) if v else JassEngine(J,pattern_path=CH,no_book=True)) for k,v in CFG.items()}
mt=collections.defaultdict(lambda:collections.defaultdict(lambda:[0,0]))   # movetime playout
sh=collections.defaultdict(lambda:[0,0])                                   # shallow d fixed (ON)
ex=collections.defaultdict(lambda:[0,0])                                   # exact-match (ON, movetime)
for fen,t,win in combos:
    WIN[0]=win
    for k,eng in engs.items():
        won,exact=keeps_win(eng,fen,movetime=MT); mt[t][k][0]+=won; mt[t][k][1]+=1
        if k=='ON': ex[t][0]+=exact; ex[t][1]+=1
    won,_=keeps_win(engs['ON'],fen,depth=DSH); sh[t][0]+=won; sh[t][1]+=1
for e in engs.values():
    try: e.close()
    except: pass
oracle.close()
def r(hn): return "n/a" if not hn[1] else f"{hn[0]/hn[1]:.2f}"
lines=[f"{'tempi':>5} {'n':>4} | {'PLAY ON':>7} {'PLAY OFF':>8} {'PLAY extF':>9} | {'exact ON':>8} {'PLAY@d'+str(DSH):>9}"]
tot=collections.defaultdict(lambda:[0,0]); te=[0,0]; ts=[0,0]
for t in sorted(mt):
    for k in CFG: tot[k][0]+=mt[t][k][0]; tot[k][1]+=mt[t][k][1]
    te[0]+=ex[t][0]; te[1]+=ex[t][1]; ts[0]+=sh[t][0]; ts[1]+=sh[t][1]
    lines.append(f"{t:>5} {mt[t]['ON'][1]:>4} | {r(mt[t]['ON']):>7} {r(mt[t]['OFF']):>8} {r(mt[t]['extF']):>9} | {r(ex[t]):>8} {r(sh[t]):>9}")
lines.append(f"{'TOT':>5} {tot['ON'][1]:>4} | {r(tot['ON']):>7} {r(tot['OFF']):>8} {r(tot['extF']):>9} | {r(te):>8} {r(ts):>9}")
open(TABLE,'w').write("\n".join(lines)+"\n")
print("\n".join(lines), flush=True)
PY
PYRC=${PIPESTATUS[0]}; set -e
[ "$PYRC" = 0 ] && [ -s "$ART/detection.txt" ] || { say "ABORT: détection échouée (PYRC=$PYRC, table vide)"; exit 8; }

say ""
say "================= LECTURE ================="
say "  PLAY ON >> exact ON  => la métrique move-match sous-estimait (jass gagne via un AUTRE coup)."
say "  PLAY extF >> PLAY ON => l'extension forçante récupère les combos => levier recherche (baker au jeu)."
say "  PLAY reste bas partout => vraie cécité tactique => recherche + curriculum combos."
say "==========================================="
