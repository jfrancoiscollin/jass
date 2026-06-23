#!/usr/bin/env bash
# id: ccx33-0445-combo-pruning-autopsy
# description: AUTOPSIE (demande JFC) — pourquoi jass rate des combinaisons que la recherche devrait dérouler trivialement
# (prises OBLIGATOIRES => séquence forcée => déterministe). La quiescence de jass est PROUVÉE correcte (elle épuise toutes
# les rafles forcées avant d'évaluer, src/search.cpp:382) => l'effet d'horizon-sur-captures est exclu. Donc si jass rate
# un shot matériel, c'est que son ÉLAGAGE/RÉDUCTIONS coupent le coup de sacrifice (un coup TRANQUILLE) avant de dérouler.
# Test décisif : à la MÊME profondeur que Scan (d11, cf 0440 où Scan convertit 95%), est-ce que jass TOUTES RÉDUCTIONS OFF
# saute de ~3% à ~Scan ? On mesure coup+score jass en {d11 défaut, d18 défaut, d11 OFF, d14 OFF} vs le coup de référence
# Scan d11, sur les 305 combinaisons dilf. CSV par position pour fouiller les ratés. Classe : 'récupéré par OFF' = élagage
# coupable (fix recherche, cheap, PAS d'éval/NNUE) ; 'raté même OFF d14' = horizon profond ou gain positionnel (éval).
# 1 pion ~ 85 unités (mesuré 0444). AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0445-combo-pruning-autopsy/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-autopsy; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
CHAMP_GZ=jobs/results/ccx33-0426-l2sweep/artefacts/w32-chal-l2-3e5-47410792.pjtw.gz
FENS=data/dilf_combinations.fen
OFF="rfp_max_depth=0,nmp_min_depth=99,lmr_min_depth=99,lmp_max_depth=0,razor_max_depth=0,multicut_min_depth=0,probcut_min_depth=0"

[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable $SCAN_BIN"; exit 4; }
[ -f "$FENS" ]     || { say "ABORT: positions absentes $FENS"; exit 4; }

say "=== build jass (32-pat, extras champion, SANS egdb) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
JASS="$W/build/jass"
git show "origin/main:$CHAMP_GZ" 2>/dev/null | gunzip > "$W/champ.pjtw" || { say "ABORT: champion absent"; exit 4; }
unset JASS_EGDB_PATH
say "# élagage OFF = $OFF"

say "=== autopsie sur 305 combinaisons (sharde ${NCPU} coeurs) ==="
export JASS="$JASS" SCAN="$SCAN_BIN" CHAMP="$W/champ.pjtw" FENS="$FENS" OFFP="$OFF" WDIR="$W"
worker(){ SHARD="$1" NSHARDS="$2" python3 - <<'PY'
import os,sys,re
sys.path.insert(0,'tools')
from calibrate_vs_scan import JassEngine, ScanEngine, jass_fen_to_scan_pos, parse_jass_bestmove
JASS=os.environ["JASS"]; SCAN=os.environ["SCAN"]; CHAMP=os.environ["CHAMP"]; FENS=os.environ["FENS"]
OFF=os.environ["OFFP"]; W=os.environ["WDIR"]; SH=int(os.environ["SHARD"]); NS=int(os.environ["NSHARDS"])
fens=[ln.split('#',1)[0].strip() for ln in open(FENS) if ln.split('#',1)[0].strip()]
mine=[f for i,f in enumerate(fens) if i%NS==SH]
jass_def=JassEngine(JASS, pattern_path=CHAMP, no_book=True)
jass_off=JassEngine(JASS, pattern_path=CHAMP, no_book=True, search_params=OFF)
scan=ScanEngine(SCAN, bb_size=0)
def key(m): return f"{m.frm}-{m.to}-{'.'.join(map(str,sorted(m.captures)))}" if m else ""
def jms(eng,fen,depth,to=240):
    eng.set_position_fen(fen); eng._drain(); eng._send(f"go depth {depth}")
    try: L=eng._read_until(lambda l:l.startswith("bestmove") or l.startswith("error"), timeout_s=to)[-1]
    except Exception: return "",None
    if L.startswith("error") or L.startswith("bestmove 0-0"): return "",None
    sc=re.search(r"score=(-?\d+)",L)
    try: mv=parse_jass_bestmove(L)
    except Exception: mv=None
    return (key(mv) if mv else ""), (int(sc.group(1)) if sc else None)
out=open(f"{W}/rows.{SH}.csv","w")
for fen in mine:
    sp=jass_fen_to_scan_pos(fen)
    ref=scan.go_from(sp, [], depth=11); refk=key(ref) if ref else ""
    r={}
    r["d11def"]=jms(jass_def,fen,11)
    r["d18def"]=jms(jass_def,fen,18)
    r["d11off"]=jms(jass_off,fen,11)
    r["d14off"]=jms(jass_off,fen,14,to=300)
    row=[fen.replace(",",";"), refk]
    for c in ("d11def","d18def","d11off","d14off"):
        mk,sv=r[c]; row+=[mk, "" if sv is None else str(sv)]
    out.write(",".join(row)+"\n"); out.flush()
out.close()
jass_def.close(); jass_off.close(); scan.close()
PY
}
export -f worker
for s in $(seq 0 $((NCPU-1))); do worker "$s" "$NCPU" >"$W/w.$s.log" 2>&1 & done; wait
cat "$W"/rows.*.csv > "$ART/per-position.csv" 2>/dev/null
NROWS=$(wc -l < "$ART/per-position.csv" 2>/dev/null || echo 0)
say "  positions mesurees : ${NROWS}"

say ""; say "=== AGREGAT (accord = coup jass == coup Scan d11 ; MAN=85) ==="
python3 - "$ART/per-position.csv" <<'PY' | tee -a "$RES"
import sys,csv
MAN=85; rows=list(csv.reader(open(sys.argv[1])))
cfgs=["d11def","d18def","d11off","d14off"]
n=0; scan_ok=0
ag={c:0 for c in cfgs}; ge1={c:0 for c in cfgs}; ge2={c:0 for c in cfgs}; meds={c:[] for c in cfgs}
recovered=0; eval_bound=0
for r in rows:
    if len(r)<2+2*len(cfgs): continue
    n+=1; ref=r[1];
    if ref: scan_ok+=1
    vals={}
    for i,c in enumerate(cfgs):
        mk=r[2+2*i]; sv=r[3+2*i]
        sv=int(sv) if sv not in ("",None) else None
        vals[c]=(mk,sv)
        if ref and mk==ref: ag[c]+=1
        if sv is not None:
            meds[c].append(sv)
            if sv>=MAN: ge1[c]+=1
            if sv>=2*MAN: ge2[c]+=1
    # classification : raté en defaut d11 mais trouve en OFF (d11 ou d14) = ELAGAGE coupable
    def found(c):
        mk,sv=vals[c]; return (ref and mk==ref) or (sv is not None and sv>=MAN)
    if not found("d11def") and (found("d11off") or found("d14off")): recovered+=1
    elif not found("d11def") and not found("d18def") and not found("d11off") and not found("d14off"): eval_bound+=1
import statistics as st
def med(x): return int(st.median(x)) if x else 0
print(f"  positions={n}  Scan a donne un coup ref sur {scan_ok}")
print(f"  {'config':>8} | {'accord/Scan':>13} | {'score med':>9} | {'>=1 pion':>9} | {'>=2 pions':>9}")
for c in cfgs:
    print(f"  {c:>8} | {ag[c]:>5}/{n} {100*ag[c]/n:>4.0f}% | {med(meds[c]):>9} | {ge1[c]:>4} {100*ge1[c]/n:>3.0f}% | {ge2[c]:>4} {100*ge2[c]/n:>3.0f}%")
print(f"\n  RECUPERES par elagage-OFF (rates en d11 defaut, trouves OFF) : {recovered}/{n} ({100*recovered/max(n,1):.0f}%)")
print(f"  RATES MEME OFF d14 (jamais vus)                             : {eval_bound}/{n} ({100*eval_bound/max(n,1):.0f}%)")
print("\n  LECTURE :")
print("   d11off >> d11def  => l'ELAGAGE cachait les combinaisons => FIX RECHERCHE (re-tuner LMR/LMP/NMP/multicut),")
print("                        SANS retrain, SANS NNUE. Le plus gros levier le moins cher.")
print("   d11off ~ d11def, d14off mieux => HORIZON : il faut chercher plus profond (extensions sacrifice).")
print("   tout plat meme d14off         => gain positionnel differe / eval shot-blind (vrai mur d'eval).")
PY
say ""
say "# CSV detaille : artefacts/per-position.csv (fen, coup_scan, puis coup+score par config) pour fouiller les ratés."
