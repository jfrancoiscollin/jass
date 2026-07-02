#!/usr/bin/env bash
# id: cpx62-0529-combo-gen-validate
# description: VALIDATION du générateur de combinaisons GRADUÉ (tools/gen_combinations.py, demande JFC 2026-07-01).
# Prouve la machinerie AVANT de scaler : (1) self-test du classifieur pur ; (2) tourne le générateur sur les combinaisons
# CONNUES dilf (305, vraie vérité-terrain) avec oracle Scan-deep d18 + egdb -> suite GRADUÉE par D_min (2..12 temps) +
# gain ; (3) TEST DE DÉTECTION jass : pour chaque combo, jass joue-t-il le coup gagnant à profondeur >= D_min ? (élagage
# ON vs OFF, échelle de profondeur), temps-agnostique. LECTURE : détection ~100% par bin = moteur fiable ; un combo à N
# temps raté à d>=N = TROU d'élagage (à réparer). La source scale-up = Scan-vs-Scan DÉSÉQUILIBRÉ (ballots) — job suivant
# une fois la machinerie verte. AUCUN NNUE. expected_duration: ~1-2 h.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0529-combo-gen-validate/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-combogen; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
CHAMP_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
DILF=data/dilf_combinations.fen
DEEP=18; MAXTEMPI=12; LIMIT=200

say "=== VALIDATION générateur de combinaisons gradué ==="
say "=== (1) self-test du classifieur pur (scale-free, sans moteur) ==="
python3 tools/gen_combinations.py --self-test 2>&1 | tee -a "$RES" || { say "ABORT self-test"; exit 3; }

say "=== build jass (egdb ON) ==="
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/sc.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null||true; }
[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable"; exit 5; }
git show "origin/main:$CHAMP_GZ" | gunzip > "$W/champ.pjtw" || { say "ABORT champ"; exit 4; }

say "=== (2) génère la suite GRADUÉE depuis dilf (oracle Scan d${DEEP} + egdb, max ${LIMIT} candidats) ==="
SUITE="$ART/combos_graded.fen"
python3 tools/gen_combinations.py --scan "$SCAN_BIN" --jass "$J" --fens "$DILF" \
    --deep "$DEEP" --max-tempi "$MAXTEMPI" --limit "$LIMIT" --out-fens "$SUITE" 2>&1 | tee -a "$RES" \
    || { say "ABORT génération"; exit 7; }
[ -s "$SUITE" ] || { say "ABORT: suite vide"; exit 7; }
say "  suite écrite : $(grep -cvE '^\s*#' "$SUITE") combos gradués"

say ""
say "=== (3) TEST DE DÉTECTION jass (par bin D_min, élagage ON vs OFF, temps-agnostique) ==="
export JASS="$J" CHAMP="$W/champ.pjtw" SUITE="$SUITE" MAXTEMPI="$MAXTEMPI"
python3 - <<'PY' 2>&1 | tee -a "$RES"
import os,sys,re
sys.path.insert(0,'tools')
from calibrate_vs_scan import JassEngine
J=os.environ["JASS"]; CH=os.environ["CHAMP"]; SUITE=os.environ["SUITE"]; MAXT=int(os.environ["MAXTEMPI"])
# parse la suite : FEN + D_min + win
combos=[]
for ln in open(SUITE):
    if '#' not in ln: continue
    fen,meta=ln.split('#',1); fen=fen.strip()
    m=dict(re.findall(r'(\w+)=([^\s]+)', meta))
    if 'D_min' in m and 'win' in m and m['win']:
        combos.append((fen,int(m['D_min']),m['win']))
print(f"  {len(combos)} combos à tester")
ELAG={'ON':'', 'OFF':'multicut_min_depth=0,razor_max_depth=0,lmp_min_depth=0'}
def det_rate(combos_bin, depth, params):
    if not combos_bin: return None
    eng=JassEngine(J, pattern_path=CH, no_book=True, search_params=params) if params else JassEngine(J, pattern_path=CH, no_book=True)
    hit=0
    for fen,dmin,win in combos_bin:
        try:
            eng.set_position_fen(fen); mv=eng.go(depth=depth)
            if mv is not None and mv.jass_str()==win: hit+=1
        except Exception: pass
    eng.close()
    return hit/len(combos_bin)
print(f"  {'D_min':>5} {'n':>4} {'det@Dmin(ON)':>13} {'det@Dmin(OFF)':>14} {'det@20(ON)':>11} {'det@20(OFF)':>12}")
for n in range(2,MAXT+1):
    cb=[c for c in combos if c[1]==n]
    if not cb: continue
    def f(x): return "n/a" if x is None else f"{x:.2f}"
    r_on =det_rate(cb, n, ELAG['ON']); r_off=det_rate(cb, n, ELAG['OFF'])
    r20on=det_rate(cb,20, ELAG['ON']); r20of=det_rate(cb,20, ELAG['OFF'])
    print(f"  {n:>5} {len(cb):>4} {f(r_on):>13} {f(r_off):>14} {f(r20on):>11} {f(r20of):>12}")
PY

say ""
say "================= LECTURE (VALIDATION) ================="
say "  Machinerie OK si : self-test vert + suite non-vide répartie sur des bins D_min + le test détection tourne."
say "  Détection ~1.00 par bin à d>=D_min => moteur capte les combos de façon quasi-certaine (l'objectif JFC)."
say "  Détection < 1 à d>=D_min AVEC élagage OFF meilleur que ON => TROU d'élagage (forward-pruning coupe la ligne)."
say "  Détection qui monte seulement à d=20 => horizon (il fallait chercher plus profond que D_min mesuré par l'oracle)."
say "  Scale-up (job suivant) : source = Scan-vs-Scan DÉSÉQUILIBRÉ (ballots) + --per-bin K pour un quota par longueur."
say "======================================================="
