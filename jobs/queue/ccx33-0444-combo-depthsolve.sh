#!/usr/bin/env bash
# id: ccx33-0444-combo-depthsolve
# description: TEST (demande JFC) — est-ce qu'une recherche jass PLUS PROFONDE (d18/d20) transforme les combinaisons en
# COUP GAGNANT, ou est-ce que l'eval reste aveugle quel que soit l'horizon ? Sur les 305 combinaisons de livre (dilf), pour
# chaque position on demande a jass (champion 3e-5, eval pur no-DB) son meilleur coup + score a d11/d15/d18/d20, et a SCAN
# d18 son coup de reference (Scan resout ~95% => son coup = la combinaison gagnante). Deux mesures par profondeur :
#   (A) ACCORD coup jass == coup Scan (jass trouve-t-il LE coup gagnant ?)  (B) EVAL-JUMP : score jass >= +1 pion (~85) /
#   +2 pions (~170) (l'eval VOIT-elle un gain ?). Si A et B montent vers d20 => c'est l'HORIZON (plus de profondeur aide).
# Si A/B restent plats et bas meme a d20 => c'est l'EVAL (shot-blind), la profondeur n'y change rien. Bonus : d18 elagage OFF
# (multicut/razor) pour voir si l'elagage cache le coup en profondeur. AUCUN NNUE. Calibration : 1 pion ~ 85 unites (mesure).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0444-combo-depthsolve/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-depthsolve; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
CHAMP_GZ=jobs/results/ccx33-0426-l2sweep/artefacts/w32-chal-l2-3e5-47410792.pjtw.gz
FENS=data/dilf_combinations.fen

[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable $SCAN_BIN"; exit 4; }
[ -f "$FENS" ]     || { say "ABORT: positions absentes $FENS"; exit 4; }

say "=== build jass (32-pat, extras champion, SANS egdb) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
JASS="$W/build/jass"
git show "origin/main:$CHAMP_GZ" 2>/dev/null | gunzip > "$W/champ.pjtw" || { say "ABORT: champion absent"; exit 4; }
unset JASS_EGDB_PATH

say "=== sonde profondeur sur 305 combinaisons (jass d11/15/18/20 + Scan d18 ref) ==="
JASS="$JASS" SCAN="$SCAN_BIN" CHAMP="$W/champ.pjtw" FENS="$FENS" RES="$RES" \
python3 - <<'PY' 2>&1 | tee -a "$RES"
import os,sys,re
sys.path.insert(0,'tools')
from calibrate_vs_scan import JassEngine, ScanEngine, jass_fen_to_scan_pos, parse_jass_bestmove
JASS=os.environ["JASS"]; SCAN=os.environ["SCAN"]; CHAMP=os.environ["CHAMP"]; FENS=os.environ["FENS"]
DEPTHS=[11,15,18,20]; SCAN_REF_DEPTH=18; MAN=85
fens=[ln.split('#',1)[0].strip() for ln in open(FENS) if ln.split('#',1)[0].strip()]
print(f"  positions : {len(fens)}  | 1 pion ~ {MAN} unites | accord = coup jass == coup Scan d{SCAN_REF_DEPTH}")

jass=JassEngine(JASS, pattern_path=CHAMP, no_book=True)
jass_off=JassEngine(JASS, pattern_path=CHAMP, no_book=True,
                    search_params="multicut_min_depth=0,razor_max_depth=0")
scan=ScanEngine(SCAN, bb_size=0)

def key(m): return (m.frm, m.to, frozenset(m.captures)) if m else None  # order-robust move id
def jass_move_score(eng, fen, depth):
    eng.set_position_fen(fen); eng._drain(); eng._send(f"go depth {depth}")
    L=eng._read_until(lambda l:l.startswith("bestmove") or l.startswith("error"), timeout_s=180)[-1]
    if L.startswith("error") or L.startswith("bestmove 0-0"): return None,None
    sc=re.search(r"score=(-?\d+)",L)
    try: mv=parse_jass_bestmove(L)
    except Exception: mv=None
    return (key(mv) if mv else None), (int(sc.group(1)) if sc else None)

agree={d:0 for d in DEPTHS}; agree_off=0
ge1={d:0 for d in DEPTHS}; ge2={d:0 for d in DEPTHS}
scores={d:[] for d in DEPTHS}; n=0; scan_ok=0
for fen in fens:
    sp=jass_fen_to_scan_pos(fen)
    ref=scan.go_from(sp, [], depth=SCAN_REF_DEPTH)
    refk=key(ref) if ref else None
    if refk: scan_ok+=1
    n+=1
    for d in DEPTHS:
        mk,scv=jass_move_score(jass, fen, d)
        if scv is not None:
            scores[d].append(scv)
            if scv>=MAN:   ge1[d]+=1
            if scv>=2*MAN: ge2[d]+=1
        if refk and mk==refk: agree[d]+=1
    mko,_=jass_move_score(jass_off, fen, 18)
    if refk and mko==refk: agree_off+=1
    if n%50==0: print(f"    ... {n}/{len(fens)}")

import statistics as st
def med(x): return int(st.median(x)) if x else 0
print(f"\n  Scan a fourni un coup de reference sur {scan_ok}/{n} positions (anchor 'un gain existe').")
print(f"  {'prof':>5} | {'accord/Scan':>12} | {'score median':>12} | {'>=1 pion':>9} | {'>=2 pions':>9}")
for d in DEPTHS:
    print(f"  d{d:>4} | {agree[d]:>5}/{n} {100*agree[d]/n:>4.0f}% | {med(scores[d]):>12} | {ge1[d]:>4}/{n} {100*ge1[d]/n:>3.0f}% | {ge2[d]:>4}/{n} {100*ge2[d]/n:>3.0f}%")
print(f"  d18-OFF| {agree_off:>5}/{n} {100*agree_off/n:>4.0f}%  (elagage multicut/razor desactive)")
print("\n  LECTURE :")
print("   accord & %>=pion MONTENT vers d20  => HORIZON : plus de profondeur trouve la combinaison (search, recuperable).")
print("   restent PLATS et BAS meme a d20     => EVAL shot-blind : la profondeur n'aide pas, c'est l'eval qu'il faut enrichir.")
print("   d18-OFF >> d18                       => notre ELAGAGE cache le coup en profondeur (a re-tuner vs adversaire fort).")
jass.close(); jass_off.close(); scan.close()
PY
say ""
say "# cible de reference : Scan convertit 95% (0440). Ici on mesure si jass VOIT/JOUE le coup gagnant a profondeur croissante."
