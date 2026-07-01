#!/usr/bin/env bash
# id: cpx62-0523-scan-static-eval-localizer
# description: LOCALISEUR ÉVAL-vs-RECHERCHE (le dernier test avant la gate NNUE, demande JFC "Par curiosité va y").
# Question gravée (CURRENT, DIAG#1a) : la distillation Scan a-t-elle visé son éval STATIQUE (in-class) ou son score de
# RECHERCHE (contaminé) ? Réponse historique : TOUTES nos distillations (0073-0086/0147-0149) ont visé le score de Scan
# À PROFONDEUR (d10 = master-clean-scan-d10) => contaminé. L'éval STATIQUE de Scan n'a JAMAIS été distillée proprement.
# CE JOB : relabel le corpus au SCAN STATIQUE (depth 0 : en dames, la depth-0 ne résout que les prises FORCÉES, jamais le
# SACRIFICE d'une combinaison => vraiment statique, aveugle aux combos) -> fit l'éval Scan-portée (src/scan_eval.cpp, v3
# phase-split, features DÉJÀ matchées à Scan cf SCAN_EVAL_DIFF) -> JOUE jass-search + Scan-static-eval vs Scan sur la jauge
# 0440 (combinaisons dilf, depth 11, eval-pur no-DB). LECTURE : conversion ~Scan(0,95) => le gap était l'ÉVAL (notre fit) ;
# conversion ~baseline(0,30-0,52) => jass-search ne convertit PAS même avec une éval Scan-dérivée => le gap est la RECHERCHE.
# Bras contrôle = ccx33-0524 (MÊME corpus/pipeline, relabel depth 12 = score de RECHERCHE) => static-vs-search apples-to-apples.
# AUCUN NNUE (règle gravée). expected_duration: ~3-6 h.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0523-scan-static-eval-localizer/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-scan-static; rm -rf "$W"; mkdir -p "$W"

SCAN_BIN=/root/jass-scan/scan_linux
CORPUS=jobs/results/ccx33-0328-scan-selfplay-corpus/artefacts/scan-selfplay-corpus.jnnw
CHAMP_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
FENS=data/dilf_combinations.fen
RELABEL_DEPTH=0        # 0 = éval STATIQUE de Scan (ce bras)
MAXREC=400000          # diagnostic-grade (couvre les buckets fréquents du milieu ; 0440 = 26 pièces)
PLAY_DEPTH=11          # jauge 0440

say "=== LOCALISEUR ÉVAL-vs-RECHERCHE — bras STATIQUE (Scan depth ${RELABEL_DEPTH}) ==="
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/sc.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null||true; }
[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable $SCAN_BIN"; exit 5; }
[ -f "$CORPUS" ] || { say "ABORT: corpus absent $CORPUS"; exit 4; }
[ -f "$FENS" ]   || { say "ABORT: dilf FENS absentes $FENS"; exit 4; }

say "=== build jass (flags champion : ENDGAME+KING_MOBILITY+SCAN_PARITY+TEMPO — NUM_EXTRAS cohérent train<->play) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1 \
    || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 \
    || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
JASS="$W/build/jass"
git show "origin/main:$CHAMP_GZ" 2>/dev/null | gunzip > "$W/champ.pjtw" || { say "ABORT: champion absent"; exit 4; }
unset JASS_EGDB_PATH

say "=== Phase 1 : relabel corpus au SCAN STATIQUE (depth ${RELABEL_DEPTH}, ${MAXREC} pos, ${NCPU} threads) ==="
LAB="$W/static-labelled.jnnw"
python3 tools/relabel_with_scan.py --in "$CORPUS" --out "$LAB" \
    --scan "$SCAN_BIN" --depth "$RELABEL_DEPTH" --max-records "$MAXREC" --threads "$NCPU" \
    >"$W/relabel.log" 2>&1 || { say "ABORT relabel"; tail -10 "$W/relabel.log"|sed 's/^/  /'; exit 7; }
[ -f "$LAB" ] || { say "ABORT: relabel sans sortie"; exit 7; }
# garde-fou : distribution des scores non-dégénérée (Scan depth-0 doit produire des scores variés)
python3 - "$LAB" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*38]
sc=[struct.unpack('<i',body[i*38+33:i*38+37])[0] for i in range(min(n,n))]
nz=sum(1 for s in sc if s!=0); import statistics as st
print(f"  relabel : {n} pos ; scores non-nuls {nz}/{n} ({100*nz/max(n,1):.1f}%) ; "
      f"min {min(sc)} max {max(sc)} mediane {int(st.median(sc))}")
if nz < 0.5*n:
    print("  ⚠️ WARN : >50% de scores nuls — Scan depth-0 possiblement dégénéré (vérifier le HUB level depth=0)")
PY

say "=== Phase 2 : dump-eval-features (extras = source unique C++/train, cohérente au build) ==="
FEAT="$W/static.feat"
"$JASS" --dump-eval-features "$LAB" "$FEAT" >"$W/dump.log" 2>&1 || { say "ABORT dump-eval-features"; tail -6 "$W/dump.log"|sed 's/^/  /'; exit 8; }
[ -f "$FEAT" ] || { say "ABORT: feat absent"; exit 8; }

say "=== Phase 3 : fit éval Scan-portée v3 sur le SCORE STATIQUE de Scan ==="
V3="$ART/scan_static_eval_v3.pjtw"
python3 pattern_jass/tools/train.py --data "$LAB" --scan-eval \
    --eval-features-file "$FEAT" --target score --score-clip 5000 \
    --l2 1e-5 --max-iter 200 --scale 1000 --out "$V3" >"$W/train.log" 2>&1 \
    || { say "ABORT train"; tail -12 "$W/train.log"|sed 's/^/  /'; exit 9; }
[ -f "$V3" ] || { say "ABORT: v3 non produit"; exit 9; }
say "  QUALITÉ DU FIT (résidu = notre linéaire peut-il matcher l'éval STATIQUE de Scan ?) :"
grep -iE "loss|iter|final|converg|r2|corr|rmse" "$W/train.log" | tail -6 | sed 's/^/    /' | tee -a "$RES"
cp "$V3" "$ART/" 2>/dev/null || true

say ""
say "=== Phase 4 : JOUE jass-search + Scan-STATIC-eval vs Scan sur la jauge 0440 (depth ${PLAY_DEPTH}, no-DB) ==="
say "    baselines connus : notre champion egdbmix = 0,302 ; Scan = 0,95 ; movetime baseline = 0,519 (0451)"
timeout 18000 python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$V3" \
    --scan-bb-size 0 --depth "$PLAY_DEPTH" --pairs 1 --openings-file "$FENS" \
    --dump-games-dir "$ART/games" >"$W/match.log" 2>&1 || say "  (match interrompu/timeout — on analyse les parties dumpées)"
tail -6 "$W/match.log" | sed 's/^/    /' | tee -a "$RES"

say ""
say "=== ANALYSE : conversion du camp AU TRAIT (identique à 0440) ==="
python3 - "$ART/games" "$FENS" <<'PY' | tee -a "$RES"
import json,glob,sys,os
gdir,fens=sys.argv[1],sys.argv[2]
stm={}
for ln in open(fens):
    b=ln.split('#',1)[0].strip()
    if not b: continue
    stm[b]=b.split(':',1)[0].strip()
ja_w=ja_n=0; sc_w=sc_n=0; tot=0; nolegal=0
for f in sorted(glob.glob(os.path.join(gdir,"game-*.json"))):
    try: g=json.load(open(f))
    except Exception: continue
    op=g.get("opening","").strip(); s=stm.get(op)
    if s is None: continue
    tot+=1
    jw=g.get("jass_is_white"); out=g.get("outcome")
    if g.get("reason","")=="no-legal-move" and g.get("plies",1)<=1: nolegal+=1
    jass_is_attacker = (jw and s=="W") or ((not jw) and s=="B")
    if out=="D": att_win=0.5
    elif (out=="W" and s=="W") or (out=="L" and s=="B"): att_win=1.0
    else: att_win=0.0
    if jass_is_attacker: ja_w+=att_win; ja_n+=1
    else:                sc_w+=att_win; sc_n+=1
def pct(w,n): return f"{w/n:.3f} ({w:.1f}/{n})" if n else "n/a"
print(f"  parties analysees      : {tot}  (sans coup legal au depart : {nolegal})")
print(f"  JASS(+Scan-static-eval) au trait : {pct(ja_w,ja_n)}")
print(f"  SCAN au trait                    : {pct(sc_w,sc_n)}")
if ja_n and sc_n:
    d=ja_w/ja_n - sc_w/sc_n
    print(f"  ECART jass - scan : {d:+.3f}")
PY

say ""
say "================= LECTURE (LOCALISEUR) ================="
say "  jass(+Scan-static-eval) ~ Scan (0,9+)  => avec l'éval de Scan, NOTRE recherche convertit comme Scan"
say "     => le gap était l'ÉVAL (notre fit/point-fixe), PAS la recherche => re-distiller/enrichir l'éval (pas encore NNUE)."
say "  jass(+Scan-static-eval) ~ baseline (0,30-0,52) << Scan  => même avec une éval dérivée de Scan, jass-search ne"
say "     convertit PAS => le gap est la RECHERCHE (jass-search < Scan-search) => cohérent 'recherche proche épuisée'"
say "     => avec le faisceau plateau-linéaire, condition de la gate NNUE remplie (preuve, pas impression)."
say "  Comparer au bras contrôle ccx33-0524 (relabel depth 12 = score de RECHERCHE) : static ~ search => label-depth"
say "     n'est pas le levier ; static >> search => la contamination-recherche PLOMBAIT nos distillations historiques."
say "======================================================="
say "  (parties dumpées dans artefacts/games/ ; v3 statique = artefacts/scan_static_eval_v3.pjtw)"
