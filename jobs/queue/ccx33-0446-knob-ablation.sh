#!/usr/bin/env bash
# id: ccx33-0446-knob-ablation
# description: ABLATION (suite 0445) — 0445 a montré que désactiver TOUT l'élagage récupère ~11% des combinaisons que jass
# rate à d11, mais full-OFF est trop lent pour le jeu réel. Ici on désactive chaque mécanisme UN PAR UN (à d11, même
# profondeur que Scan) pour trouver LEQUEL cache les sacrifices => on ne re-tunera QUE celui-là, sans perdre la vitesse.
# Configs : baseline / LMR off / LMP off / NMP off / RFP off / razor off / multicut off / ALL off (borne sup 0445).
# Métrique par config sur les 305 combinaisons : %voit>=1 pion (score>=85) + accord coup==Scan d11, et surtout le nombre
# de combinaisons RÉCUPÉRÉES vs baseline (ratée baseline, vue avec ce knob off). Le knob au plus gros gain = le coupable.
# AUCUN changement des défauts moteur (pur diagnostic). AUCUN NNUE. 1 pion ~ 85 unités.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0446-knob-ablation/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-ablation; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
CHAMP_GZ=jobs/results/ccx33-0426-l2sweep/artefacts/w32-chal-l2-3e5-47410792.pjtw.gz
FENS=data/dilf_combinations.fen
DEPTH=11

[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable $SCAN_BIN"; exit 4; }
[ -f "$FENS" ]     || { say "ABORT: positions absentes $FENS"; exit 4; }

say "=== build jass (32-pat, extras champion, SANS egdb) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
JASS="$W/build/jass"
git show "origin/main:$CHAMP_GZ" 2>/dev/null | gunzip > "$W/champ.pjtw" || { say "ABORT: champion absent"; exit 4; }
unset JASS_EGDB_PATH

say "=== ablation knob-par-knob a d${DEPTH} (sharde ${NCPU} coeurs) ==="
export JASS="$JASS" SCAN="$SCAN_BIN" CHAMP="$W/champ.pjtw" FENS="$FENS" WDIR="$W" DEPTH="$DEPTH"
worker(){ SHARD="$1" NSHARDS="$2" python3 - <<'PY'
import os,sys,re
sys.path.insert(0,'tools')
from calibrate_vs_scan import JassEngine, ScanEngine, jass_fen_to_scan_pos, parse_jass_bestmove
JASS=os.environ["JASS"]; SCAN=os.environ["SCAN"]; CHAMP=os.environ["CHAMP"]; FENS=os.environ["FENS"]
W=os.environ["WDIR"]; SH=int(os.environ["SHARD"]); NS=int(os.environ["NSHARDS"]); D=int(os.environ["DEPTH"])
CONFIGS=[("baseline",""),
         ("lmr_off","lmr_min_depth=99"),
         ("lmp_off","lmp_max_depth=0"),
         ("nmp_off","nmp_min_depth=99"),
         ("rfp_off","rfp_max_depth=0"),
         ("razor_off","razor_max_depth=0"),
         ("multicut_off","multicut_min_depth=0"),
         ("all_off","rfp_max_depth=0,nmp_min_depth=99,lmr_min_depth=99,lmp_max_depth=0,razor_max_depth=0,multicut_min_depth=0,probcut_min_depth=0")]
fens=[ln.split('#',1)[0].strip() for ln in open(FENS) if ln.split('#',1)[0].strip()]
mine=[f for i,f in enumerate(fens) if i%NS==SH]
def key(m): return f"{m.frm}-{m.to}-{'.'.join(map(str,sorted(m.captures)))}" if m else ""
# Scan ref d11 une fois par position
scan=ScanEngine(SCAN, bb_size=0); refs={}
for fen in mine:
    r=scan.go_from(jass_fen_to_scan_pos(fen), [], depth=D); refs[fen]=key(r) if r else ""
scan.close()
def jms(eng,fen):
    eng.set_position_fen(fen); eng._drain(); eng._send(f"go depth {D}")
    try: L=eng._read_until(lambda l:l.startswith("bestmove") or l.startswith("error"), timeout_s=120)[-1]
    except Exception: return "",None
    if L.startswith("error") or L.startswith("bestmove 0-0"): return "",None
    sc=re.search(r"score=(-?\d+)",L)
    try: mv=parse_jass_bestmove(L)
    except Exception: mv=None
    return (key(mv) if mv else ""),(int(sc.group(1)) if sc else None)
out=open(f"{W}/rows.{SH}.csv","w")
for cname,cp in CONFIGS:
    eng=JassEngine(JASS, pattern_path=CHAMP, no_book=True, search_params=(cp or None))
    for fen in mine:
        mk,sv=jms(eng,fen)
        out.write(f"{cname},{fen.replace(',',';')},{refs[fen]},{mk},{'' if sv is None else sv}\n"); out.flush()
    eng.close()
out.close()
PY
}
export -f worker
for s in $(seq 0 $((NCPU-1))); do worker "$s" "$NCPU" >"$W/w.$s.log" 2>&1 & done; wait
cat "$W"/rows.*.csv > "$ART/per-config.csv" 2>/dev/null
say "  lignes mesurees : $(wc -l < "$ART/per-config.csv" 2>/dev/null || echo 0)"

say ""; say "=== AGREGAT (MAN=85 ; recupere = raté baseline, vu avec ce knob off) ==="
python3 - "$ART/per-config.csv" <<'PY' | tee -a "$RES"
import sys,csv,collections
MAN=85; rows=list(csv.reader(open(sys.argv[1])))
# config, fen, scanref, jass_move, jass_score
by=collections.defaultdict(dict)   # by[config][fen]=(move,score,ref)
for r in rows:
    if len(r)<5: continue
    cfg,fen,ref,mk,sv=r[0],r[1],r[2],r[3],r[4]
    sv=int(sv) if sv not in("","None") else None
    by[cfg][fen]=(mk,sv,ref)
configs=[c for c in ["baseline","lmr_off","lmp_off","nmp_off","rfp_off","razor_off","multicut_off","all_off"] if c in by]
base=by.get("baseline",{})
def seen(t):
    mk,sv,ref=t; return (ref!="" and mk==ref) or (sv is not None and sv>=MAN)
nb={f for f,t in base.items() if not seen(t)}   # ratees baseline
N=len(base)
print(f"  positions={N}  ratees par baseline={len(nb)}")
print(f"  {'config':>13} | {'voit>=1pion':>11} | {'accord Scan':>11} | {'recuperees vs baseline':>22}")
for c in configs:
    d=by[c]; v=sum(1 for f,t in d.items() if t[1] is not None and t[1]>=MAN)
    ag=sum(1 for f,t in d.items() if t[2]!="" and t[0]==t[2])
    rec=sum(1 for f in nb if f in d and seen(d[f]))
    tag=" <= COUPABLE" if (c!="baseline" and c!="all_off") else ""
    print(f"  {c:>13} | {v:>4} {100*v/N:>3.0f}% | {ag:>4} {100*ag/N:>3.0f}% | {rec:>5} ({100*rec/max(len(nb),1):>3.0f}% des ratees){tag if rec>0 else ''}")
print("\n  LECTURE : le knob (hors all_off) avec le plus de 'recuperees' = celui qui cache les sacrifices.")
print("   Si un seul knob ~= all_off => re-tuner CE knob seul (vs adversaire tactique) = gain cheap, vitesse preservee.")
print("   Si recuperees etalees sur plusieurs => combinaison de reductions ; sinon c'est surtout l'eval (cf 0445, ~60%).")
PY
say ""; say "# CSV : artefacts/per-config.csv (config,fen,coup_scan,coup_jass,score) ; defauts moteur INCHANGES (diagnostic)."
