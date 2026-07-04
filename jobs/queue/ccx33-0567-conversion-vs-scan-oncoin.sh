#!/usr/bin/env bash
# id: ccx33-0567-conversion-vs-scan-oncoin
# description: CHECK CONVERSION COMBINAISONS vs Scan sur le NOUVEAU MOTEUR (JFC) — le gain recherche (coin +49, threat_ext
# ~+150 prov.) transfere-t-il a la cible tactique reelle ? Metrique PLAYOUT (comme 0535, la signature 0440 : jass 25% vs
# Scan 95%) : jass joue son coup au movetime, l'ORACLE Scan-deep d13 confirme si le camp au trait GAGNE TOUJOURS (>=+1
# forcé) => detection reelle, independante du coup exact. 2 bras, meme oracle, meme eval gen1 :
#   NEW = defaut BAKE (coin corner+nmp + qs_threat_ext ON)
#   OLD = ere-gen1 pre-coin (probcut=0,lmr=4,multicut=6,eg_no_nmp=1,qs_threat_ext=0)
# Si NEW > OLD nettement => le gain recherche convertit PLUS de combinaisons => transfere au tactique. Sans EGDB (conversion
# PURE eval+search, pas de bequille tablebase). Suite balanced (subsample par tempi). VERDICT job-side. AUCUN NNUE. ~25-40min.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0567-conversion-vs-scan-oncoin/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0567-conversion-vs-scan-oncoin/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-conv; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
SUITE_SRC="jobs/results/cpx62-0534-combo-gen-balanced/artefacts/combos_balanced.fen"
ORACLE_DEEP=13; MAXTEMPI=12; GAIN=1; MOVETIME=2.0; SUBN_PER_BIN=30

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*5)); done; return 1; }

say "=== CHECK CONVERSION vs Scan sur le coin (movetime ${MOVETIME}s, oracle Scan d${ORACLE_DEEP}) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
if [ ! -x "$SCAN_BIN" ]; then
  SRC=/root/jass-scan-src; [ -d "$SRC" ] || git clone --depth=1 https://github.com/rhalbersma/scan.git "$SRC" >"$W/sc.log" 2>&1
  mkdir -p /root/jass-scan; cp "$SRC/scan_linux" "$SCAN_BIN"; chmod +x "$SCAN_BIN"
  cp -r "$SRC/data" /root/jass-scan/data 2>/dev/null||true; cp "$SRC/scan.ini" /root/jass-scan/scan.ini 2>/dev/null||true
fi
[ -x "$SCAN_BIN" ] || { say "ABORT Scan absent"; exit 5; }
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
git show "origin/main:$SUITE_SRC" > "$W/suite.fen" 2>/dev/null || { say "ABORT suite"; exit 4; }
say "  suite : $(grep -cvE '^\s*(#|$)' "$W/suite.fen") combos ; eval gen1 ; sans EGDB"
say "  confirme coin dans le build (defaut NEW) : $(git show origin/main:src/search_params.hpp | grep -cE 'probcut_min_depth = 5|eg_no_nmp  = false')/2 params-cle"

export JASS="$J" CHAMP="$W/gen1.pjtw" SCAN="$SCAN_BIN" SUITE="$W/suite.fen" TABLE="$ART/detection.txt" \
       DEEP="$ORACLE_DEEP" MAXT="$MAXTEMPI" GAIN="$GAIN" MT="$MOVETIME" SUBN="$SUBN_PER_BIN"
set +e
python3 - <<'PY' 2>&1 | tee -a "$RES"
import os,sys,re,collections
sys.path.insert(0,'tools')
from gen_combinations import ScanOracle
from calibrate_vs_scan import JassEngine
J=os.environ["JASS"]; CH=os.environ["CHAMP"]; SCAN=os.environ["SCAN"]; SUITE=os.environ["SUITE"]; TABLE=os.environ["TABLE"]
DEEP=int(os.environ["DEEP"]); MAXT=int(os.environ["MAXT"]); GAIN=int(os.environ["GAIN"]); MT=float(os.environ["MT"]); SUBN=int(os.environ["SUBN"])
byt=collections.defaultdict(list)
for ln in open(SUITE):
    if '#' not in ln: continue
    fen,meta=ln.split('#',1); fen=fen.strip(); m=dict(re.findall(r'(\w+)=([^\s]+)',meta))
    if 'tempi' in m and m.get('win'): byt[int(m['tempi'])].append((fen,m['win']))
combos=[]
for t in sorted(byt): combos += [(fen,t,win) for fen,win in byt[t][:SUBN]]
print(f"  {len(combos)} combos (<={SUBN}/bin tempi) ; oracle Scan d{DEEP} ; movetime {MT}s", flush=True)
oracle=ScanOracle(SCAN, J, deep=DEEP); WIN=[""]
def keeps_win(eng, fen):
    eng.set_position_fen(fen)
    m=eng.go(movetime=MT)
    if m is None: return False
    oracle.ref.set_position_fen(fen)
    if not oracle.ref.apply_move(m): return False
    net,_=oracle.forced_line(oracle.ref.current_fen(), MAXT)
    return bool(net) and net[-1] <= -GAIN
# 2 bras : NEW = defaut bake (coin+threat_ext) ; OLD = ere-gen1 pre-coin
CFG={'NEW':'', 'OLD':'probcut_min_depth=0,lmr_first_full_nonpv=4,multicut_min_depth=6,eg_no_nmp=1,qs_threat_ext=0'}
engs={k:(JassEngine(J,pattern_path=CH,no_book=True,search_params=v) if v else JassEngine(J,pattern_path=CH,no_book=True)) for k,v in CFG.items()}
mt=collections.defaultdict(lambda:collections.defaultdict(lambda:[0,0]))
for fen,t,win in combos:
    WIN[0]=win
    for k,eng in engs.items():
        w=keeps_win(eng,fen); mt[t][k][0]+=w; mt[t][k][1]+=1
for e in engs.values():
    try: e.close()
    except: pass
oracle.close()
def r(hn): return "n/a" if not hn[1] else f"{hn[0]/hn[1]:.3f}"
lines=[f"{'tempi':>5} {'n':>4} | {'NEW(coin)':>10} {'OLD(gen1)':>10}"]
tot=collections.defaultdict(lambda:[0,0])
for t in sorted(mt):
    for k in CFG: tot[k][0]+=mt[t][k][0]; tot[k][1]+=mt[t][k][1]
    lines.append(f"{t:>5} {mt[t]['NEW'][1]:>4} | {r(mt[t]['NEW']):>10} {r(mt[t]['OLD']):>10}")
nN=tot['NEW']; nO=tot['OLD']
lines.append(f"{'TOT':>5} {nN[1]:>4} | {r(nN):>10} {r(nO):>10}")
open(TABLE,'w').write("\n".join(lines)+"\n")
print("\n".join(lines), flush=True)
import math
def se(hn):
    if not hn[1]: return 0
    p=hn[0]/hn[1]; return math.sqrt(max(p*(1-p),1e-9)/hn[1])
dN,dO=(nN[0]/nN[1] if nN[1] else 0),(nO[0]/nO[1] if nO[1] else 0)
sd=math.sqrt(se(nN)**2+se(nO)**2); delta=dN-dO
print("")
print(f"=== VERDICT conversion : NEW(coin) {dN:.3f} vs OLD(gen1) {dO:.3f} ; delta {delta:+.3f} +- {1.96*sd:.3f} (95%) ===")
if delta-1.96*sd>0:   print("=> NEW convertit PLUS hors-IC : le gain recherche TRANSFERE au tactique reel (vs Scan-oracle).")
elif delta+1.96*sd<0: print("=> NEW convertit MOINS : regression tactique (a investiguer).")
else:                 print("=> delta non-significatif : conversion inchangee (le gain self-play ne se lit pas ici, ou n<).")
print("Reference historique 0440 : jass ~0.25 vs Scan ~0.95. Oracle Scan-deep = plafond ~1.0 par construction.")
PY
RC=$?
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0567 conversion vs Scan sur coin : RESULTS job-side (NEW vs OLD detection)" \
  && say "  RESULTS committe job-side ✓" || say "  ⚠ commit RESULTS echoue"
say "=== fin 0567 (rc python=$RC) ==="
