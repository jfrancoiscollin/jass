#!/usr/bin/env bash
# id: ccx33-0440-dilf-tactical
# description: TEST TACTIQUE sur combinaisons reelles de livres (dilf ALL_DIAGRAMS -> data/dilf_combinations.fen, 305
# positions legales, mediane 26 pieces = milieu de partie = NOTRE zone de faiblesse diagnostiquee). On joue le champion
# lineaire 3e-5 vs Scan A PARTIR de chaque position (no-DB des 2 cotes, depth 11, --openings-file). Chaque position est
# jouee 2x (jass=trait / scan=trait via swap couleur). Metrique-cle = TAUX DE CONVERSION DU CAMP AU TRAIT (celui qui a
# le coup gagnant) : jass-attaquant vs scan-attaquant. L'ecart = notre trou tactique sur des combinaisons reelles, chiffre.
# Reste STRICTEMENT dans la classe lineaire (AUCUN NNUE — regle gravee). Dump des parties pour analyse.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0440-dilf-tactical/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-dilf-tac; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
CHAMP_GZ=jobs/results/ccx33-0426-l2sweep/artefacts/w32-chal-l2-3e5-47410792.pjtw.gz
FENS=data/dilf_combinations.fen
D=11; PAIRS=1

[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable $SCAN_BIN"; exit 4; }
[ -f "$FENS" ]     || { say "ABORT: positions absentes $FENS"; exit 4; }
NPOS=$(grep -cvE '^\s*(#|$)' "$FENS"); say "# corpus combinaisons : ${NPOS} positions ($FENS)"

say "=== build jass (32-pat, extras champion, SANS egdb) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
JASS="$W/build/jass"
git show "origin/main:$CHAMP_GZ" 2>/dev/null | gunzip > "$W/champ.pjtw" || { say "ABORT: champion absent"; exit 4; }
unset JASS_EGDB_PATH

say "=== match champion 3e-5 vs Scan depuis ${NPOS} combinaisons (depth ${D}, no-DB, ~4h max) ==="
timeout 14400 python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" \
    --scan-bb-size 0 --depth "$D" --pairs "$PAIRS" --openings-file "$FENS" \
    --dump-games-dir "$ART/games" >"$W/match.log" 2>&1 || say "  (match interrompu/timeout — on analyse ce qui est dumpe)"
tail -6 "$W/match.log" | sed 's/^/    /' | tee -a "$RES"

say ""
say "=== ANALYSE : conversion du camp AU TRAIT (qui a la combinaison) ==="
python3 - "$ART/games" "$FENS" <<'PY' | tee -a "$RES"
import json,glob,sys,os
gdir,fens=sys.argv[1],sys.argv[2]
# stm par position d'ouverture
stm={}
for ln in open(fens):
    b=ln.split('#',1)[0].strip()
    if not b: continue
    stm[b]=b.split(':',1)[0].strip()  # 'W' ou 'B'
ja_w=ja_n=0; sc_w=sc_n=0; tot=0; nolegal=0
for f in sorted(glob.glob(os.path.join(gdir,"game-*.json"))):
    try: g=json.load(open(f))
    except Exception: continue
    op=g.get("opening","").strip(); s=stm.get(op)
    if s is None: continue
    tot+=1
    jw=g.get("jass_is_white"); out=g.get("outcome")
    if g.get("reason","")=="no-legal-move" and g.get("plies",1)<=1: nolegal+=1
    # camp au trait = jass ?  (jass blanc & trait blancs) ou (jass noir & trait noirs)
    jass_is_attacker = (jw and s=="W") or ((not jw) and s=="B")
    # l'attaquant (camp au trait) a-t-il gagne ?  W=>blanc gagne, L=>noir gagne
    if out=="D": att_win=0.5
    elif (out=="W" and s=="W") or (out=="L" and s=="B"): att_win=1.0
    else: att_win=0.0
    if jass_is_attacker: ja_w+=att_win; ja_n+=1
    else:                sc_w+=att_win; sc_n+=1
def pct(w,n): return f"{w/n:.3f} ({w:.1f}/{n})" if n else "n/a"
print(f"  parties analysees      : {tot}  (positions sans coup legal au depart : {nolegal})")
print(f"  JASS au trait (convertit la combinaison) : {pct(ja_w,ja_n)}")
print(f"  SCAN au trait (convertit la combinaison) : {pct(sc_w,sc_n)}")
if ja_n and sc_n:
    d=ja_w/ja_n - sc_w/sc_n
    print(f"  ECART jass - scan : {d:+.3f}  => {'jass convertit MIEUX' if d>0.02 else ('parite' if abs(d)<=0.02 else 'jass convertit MOINS = trou tactique')}")
PY

say ""
say "================= LECTURE ================="
say "  jass-au-trait << scan-au-trait => on RATE des combinaisons que Scan trouve => trou tactique d'EVAL"
say "    (shot-vulnerable) sur des positions de livre => cible d'entrainement : injecter ces positions au fit."
say "  jass-au-trait ~ scan-au-trait => on convertit aussi bien => la faiblesse vs Scan est ailleurs (jeu positionnel)."
say "  (parties dumpees dans artefacts/games/ pour rejouer les ratees)"
say "==========================================="
