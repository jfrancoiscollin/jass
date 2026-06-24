#!/usr/bin/env bash
# id: ccx33-0448-promo-sac
# description: TEST (demande JFC) — le champion detecte-t-il les SACRIFICES DE PROMOTION evidents ? Calibration mesuree :
# 1 homme ~ 85 unites, 1 ROI ~ 3.5 hommes (l'eval valorise deja le roi -> le mur n'est PAS la valeur du roi mais
# atteindre+ne-pas-elaguer la promotion). On CONSTRUIT un jeu de positions "sacrifier 1 homme pour faire une dame sure"
# (genere aleatoire avec un homme STM avance, filtre par un ORACLE : jass-d20 voit un gros gain + meilleur coup = un
# sacrifice forcant + Scan-d18 joue LE MEME coup). Puis on les passe dans la batterie : jass eval-pur d11/d15/d18,
# baseline vs no_reduce_forcing=1 -> a quelle profondeur / avec quel reglage jass DETECTE le gain (score>=+1.5 homme et
# joue le sacrifice). Set sauve en data/promo_sac_tests.fen. AUCUN egdb requis (oracle = Scan+jass-profond). AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0448-promo-sac/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-promosac; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
CHAMP_GZ=jobs/results/ccx33-0426-l2sweep/artefacts/w32-chal-l2-3e5-47410792.pjtw.gz

[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable"; exit 4; }
say "=== build jass (SANS egdb) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
JASS="$W/build/jass"
git show "origin/main:$CHAMP_GZ" 2>/dev/null | gunzip > "$W/champ.pjtw" || { say "ABORT: champion absent"; exit 4; }
unset JASS_EGDB_PATH

export JASS="$JASS" SCAN="$SCAN_BIN" CHAMP="$W/champ.pjtw" WDIR="$W"
say "=== PHASE 1 : construire + verifier le jeu de positions (oracle jass-d20 + Scan-d18) ==="
python3 - <<'PY' 2>&1 | tee -a "$RES"
import os,sys,re,random
sys.path.insert(0,'tools')
from calibrate_vs_scan import JassEngine, ScanEngine, Referee, jass_fen_to_scan_pos, parse_jass_bestmove
JASS=os.environ["JASS"]; SCAN=os.environ["SCAN"]; CHAMP=os.environ["CHAMP"]; W=os.environ["WDIR"]
MAN=85; WIN=int(1.5*MAN); TARGET=40; ATTEMPTS=6000; ORACLE_D=20; SCAN_D=18
random.seed(20260624)
def fen_from(stm, wm, wk, bm, bk):
    def lst(men,kings): return ",".join([str(s) for s in sorted(men)]+[f"K{s}" for s in sorted(kings)])
    return f"{stm}:W{lst(wm,wk)}:B{lst(bm,bk)}"
def rnd_pos():
    stm = random.choice("WB")
    tot = random.randint(4,7); wt = random.randint(1,tot-1); bt = tot-wt
    sqs=random.sample(range(1,51), tot)
    # assign : si stm=W, garantir un homme blanc AVANCE (6..15, proche promo 1-5) ; sinon homme noir avance (36..45)
    wm=set(); wk=set(); bm=set(); bk=set()
    wsq=sqs[:wt]; bsq=sqs[wt:]
    for s in wsq:
        (wk if (random.random()<0.25 or s<=5) else wm).add(s)
    for s in bsq:
        (bk if (random.random()<0.25 or s>=46) else bm).add(s)
    # forcer un homme avance du camp au trait
    if stm=="W":
        adv=[s for s in wsq if 6<=s<=15]
        if not adv:
            if wm:
                s=min(wm); wm.discard(s); ns=random.choice([x for x in range(6,16) if x not in sqs] or [None])
                if ns is None: return None
                wm.add(ns)
            else: return None
    else:
        adv=[s for s in bsq if 36<=s<=45]
        if not adv:
            if bm:
                s=max(bm); bm.discard(s); ns=random.choice([x for x in range(36,46) if x not in sqs] or [None])
                if ns is None: return None
                bm.add(ns)
            else: return None
    return fen_from(stm,wm,wk,bm,bk)

jass=JassEngine(JASS, pattern_path=CHAMP, no_book=True)
scan=ScanEngine(SCAN, bb_size=0)
ref =Referee(JASS)
probe=JassEngine(JASS, pattern_path=CHAMP, no_book=True)
def key(m): return (m.frm,m.to,frozenset(m.captures)) if m else None
def jbest(eng,fen,d):
    eng.set_position_fen(fen); eng._drain(); eng._send(f"go depth {d}")
    try: L=eng._read_until(lambda l:l.startswith("bestmove") or l.startswith("error"),timeout_s=120)[-1]
    except Exception: return None,None
    if L.startswith("error") or L.startswith("bestmove 0-0"): return None,None
    sc=re.search(r"score=(-?\d+)",L)
    try: mv=parse_jass_bestmove(L)
    except Exception: mv=None
    return mv,(int(sc.group(1)) if sc else None)
def legal_quiet(fen):
    probe.set_position_fen(fen); probe._drain(); probe._send("go depth 1")
    try: L=probe._read_until(lambda l:l.startswith("bestmove") or l.startswith("error"),timeout_s=20)[-1]
    except Exception: return False
    if L.startswith("error") or L.startswith("bestmove 0-0"): return False
    try: mv=parse_jass_bestmove(L)
    except Exception: return False
    return not mv.is_capture   # quiet (pas de prise en attente)
def forcing_after(fen, mv):
    ref.set_position_fen(fen)
    if not ref.apply_move(mv): return False
    nf=ref.current_fen()
    probe.set_position_fen(nf); probe._drain(); probe._send("go depth 1")
    try: L=probe._read_until(lambda l:l.startswith("bestmove") or l.startswith("error"),timeout_s=20)[-1]
    except Exception: return False
    try: m=parse_jass_bestmove(L)
    except Exception: return False
    return m.is_capture        # adversaire force de prendre

kept=[]; att=0
out=open(f"{W}/promo_sac_tests.fen","w")
out.write("# positions sacrifice-de-promotion (oracle jass-d%d gain>=%d + coup forcant sac + accord Scan-d%d)\n"%(ORACLE_D,WIN,SCAN_D))
while att<ATTEMPTS and len(kept)<TARGET:
    att+=1
    fen=rnd_pos()
    if not fen: continue
    if not legal_quiet(fen): continue
    mj,sj=jbest(jass,fen,ORACLE_D)
    if mj is None or sj is None or sj<WIN: continue   # jass-profond ne voit pas un gros gain
    if mj.is_capture: continue                      # on veut un sacrifice (coup tranquille)
    if not forcing_after(fen,mj): continue            # ... qui force une prise
    ms=scan.go_from(jass_fen_to_scan_pos(fen), [], depth=SCAN_D)
    if key(ms)!=key(mj): continue                     # Scan joue LE MEME coup => corroboration
    kept.append((fen, f"{mj.frm}-{mj.to}", sj))
    out.write(f"{fen}  # sac {mj.frm}-{mj.to} jass_d{ORACLE_D}={sj}\n"); out.flush()
out.close()
print(f"  tentatives={att}  positions VERIFIEES (sac-promotion gagnant)={len(kept)}")
jass.close(); scan.close(); ref.close(); probe.close()
PY
cp "$W/promo_sac_tests.fen" "$ART/promo_sac_tests.fen" 2>/dev/null || true
NSET=$(grep -cvE '^\s*(#|$)' "$W/promo_sac_tests.fen" 2>/dev/null || echo 0)
[ "${NSET:-0}" -ge 5 ] || { say "  (set trop maigre: ${NSET} — la generation aleatoire n'a pas trouve assez de motifs ; relancer avec plus d'ATTEMPTS ou miner egdb)"; say "FIN (pas de batterie)"; exit 0; }

say ""; say "=== PHASE 2 : batterie de detection (jass eval-pur, baseline vs no_reduce_forcing=1) ==="
python3 - "$W/promo_sac_tests.fen" <<'PY' 2>&1 | tee -a "$RES"
import os,sys,re
sys.path.insert(0,'tools')
from calibrate_vs_scan import JassEngine, parse_jass_bestmove
JASS=os.environ["JASS"]; CHAMP=os.environ["CHAMP"]; MAN=85; WIN=int(1.5*MAN)
rows=[]
for ln in open(sys.argv[1]):
    b=ln.split('#',1)[0].strip()
    if b: rows.append(b)
def eng(sp): return JassEngine(JASS, pattern_path=CHAMP, no_book=True, search_params=(sp or None))
def jbest(e,fen,d):
    e.set_position_fen(fen); e._drain(); e._send(f"go depth {d}")
    L=e._read_until(lambda l:l.startswith("bestmove") or l.startswith("error"),timeout_s=120)[-1]
    if L.startswith("error"): return None
    sc=re.search(r"score=(-?\d+)",L); return int(sc.group(1)) if sc else None
configs=[("d11 base",11,""),("d11 FIX",11,"no_reduce_forcing=1"),
         ("d15 base",15,""),("d15 FIX",15,"no_reduce_forcing=1"),
         ("d18 base",18,""),("d18 FIX",18,"no_reduce_forcing=1")]
N=len(rows); print(f"  positions test = {N}  (detecte = score >= +1.5 homme = {WIN})")
print(f"  {'config':>10} | {'detecte':>10} | {'score median':>12}")
import statistics as st
for name,d,sp in configs:
    e=eng(sp); scs=[]
    for fen in rows:
        s=jbest(e,fen,d)
        if s is not None: scs.append(s)
    e.close()
    det=sum(1 for s in scs if s>=WIN)
    print(f"  {name:>10} | {det:>4}/{N} {100*det/max(N,1):>3.0f}% | {int(st.median(scs)) if scs else 0:>12}")
print("\n  LECTURE : FIX >> base a profondeur egale => le fix debloque les sacs de promotion (de-elagage).")
print("            detection monte avec la profondeur => il faut surtout atteindre la promotion (horizon).")
print("            reste bas partout => motif non capte par l'eval lineaire meme en voyant le roi (rare, vu valeur roi OK).")
PY
say ""; say "# set sauve : artefacts/promo_sac_tests.fen (+ a committer en data/ si on veut l'integrer a la batterie permanente)."
