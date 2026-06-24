#!/usr/bin/env bash
# id: ccx33-0449-promo-sac-egdb
# description: TEST promotion EXACT (egdb dispo sur ccx33, dixit JFC). Version gold-standard de 0448 : au lieu d'un oracle
# Scan+jass, on MINE l'EGDB (verite exacte <=7 pieces). On genere des positions egdb-resolues (--gen-egdb-wld), on garde
# celles ou le camp au trait GAGNE (egdb), a un HOMME AVANCE, dont le coup optimal (jass+egdb) est un SACRIFICE forcant,
# et — preuve de PROMOTION — on deroule la ligne egdb-optimale et on confirme qu'une DAME apparait pour le camp au trait.
# => set de "sacrifie 1 homme pour faire une dame sure" PROUVE. Puis batterie eval-pur (SANS egdb) : jass d11/d15/d18
# baseline vs no_reduce_forcing=1 -> a quelle profondeur/reglage jass DETECTE le gain (score>=+1.5 homme). AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0449-promo-sac-egdb/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-promosac-egdb; rm -rf "$W"; mkdir -p "$W"
CHAMP_GZ=jobs/results/ccx33-0426-l2sweep/artefacts/w32-chal-l2-3e5-47410792.pjtw.gz
EGDIR=/root/egdb_extracted
POOL=400000; TARGET=40

[ -d "$EGDIR" ] || { say "ABORT: egdb absent ($EGDIR) — installer d'abord (cf ccx33-028x)"; exit 4; }
say "=== build jass JASS_EGDB=ON (from-source) ==="
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb (build)"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
JASS="$W/build/jass"
git show "origin/main:$CHAMP_GZ" 2>/dev/null | gunzip > "$W/champ.pjtw" || { say "ABORT: champion absent"; exit 4; }

say "=== generation pool egdb-resolu (<=7 pieces) ==="
"$JASS" --gen-egdb-wld "$POOL" "$W/pool.jnnw" "$EGDIR" 7 2048 12345 >"$W/gen.log" 2>&1 || { say "ABORT gen-egdb-wld"; tail -6 "$W/gen.log"|sed 's/^/  /'; exit 7; }
NP=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/pool.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
say "  pool egdb : ${NP} positions"

say "=== PHASE 1 : filtrer + PROUVER (egdb gain + homme avance + sac forcant + DAME dans la ligne optimale) ==="
export JASS="$JASS" CHAMP="$W/champ.pjtw" WDIR="$W" EGDIR="$EGDIR" TARGET="$TARGET"
JASS_EGDB_PATH="$EGDIR" python3 - <<'PY' 2>&1 | tee -a "$RES"
import os,sys,re,struct
sys.path.insert(0,'tools')
from calibrate_vs_scan import JassEngine, Referee, parse_jass_bestmove, parse_jass_fen
JASS=os.environ["JASS"]; CHAMP=os.environ["CHAMP"]; W=os.environ["WDIR"]; TARGET=int(os.environ["TARGET"])
MAN=85; ORACLE_D=22; WALK=16
REC=38
def bbs_fen(wm,wk,bm,bk,stm):
    sl=lambda bb:[i+1 for i in range(50) if (bb>>i)&1]
    Wp=[str(s) for s in sl(wm)]+[f"K{s}" for s in sl(wk)]
    Bp=[str(s) for s in sl(bm)]+[f"K{s}" for s in sl(bk)]
    return f"{'W' if stm==0 else 'B'}:W{','.join(Wp)}:B{','.join(Bp)}"
def adv_man(wm,bm,stm):
    sl=lambda bb:[i+1 for i in range(50) if (bb>>i)&1]
    return any(6<=s<=15 for s in sl(wm)) if stm==0 else any(36<=s<=45 for s in sl(bm))
# lecture pool : garder STM-win (wdl==+1) a homme avance
b=open(f"{W}/pool.jnnw",'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*REC]
cands=[]
for i in range(n):
    wm,wk,bm,bk=struct.unpack('<QQQQ',body[i*REC:i*REC+32]); stm=body[i*REC+32]; wdl=struct.unpack('<b',body[i*REC+37:i*REC+38])[0]
    if wdl==1 and adv_man(wm,bm,stm): cands.append(bbs_fen(wm,wk,bm,bk,stm))
print(f"  candidats (egdb-win + homme avance) : {len(cands)}")
jass=JassEngine(JASS, pattern_path=CHAMP, no_book=True)   # herite JASS_EGDB_PATH => joue egdb-parfait
ref =Referee(JASS); probe=JassEngine(JASS, pattern_path=CHAMP, no_book=True)
def best(eng,fen,d):
    eng.set_position_fen(fen); eng._drain(); eng._send(f"go depth {d}")
    try: L=eng._read_until(lambda l:l.startswith("bestmove") or l.startswith("error"),timeout_s=60)[-1]
    except Exception: return None
    if L.startswith("error") or L.startswith("bestmove 0-0"): return None
    try: return parse_jass_bestmove(L)
    except Exception: return None
def is_forcing(fen):  # apres avoir applique le coup : adversaire force de prendre ?
    m=best(probe,fen,1); return m is not None and m.is_capture
def stm_kings(fen,stm0):
    side,wm,wk,bm,bk=parse_jass_fen(fen); return len(wk) if stm0=="W" else len(bk)
out=open(f"{W}/promo_sac_tests.fen","w")
out.write(f"# sacrifice-de-promotion PROUVE par egdb (gain exact + sac forcant + dame dans la ligne optimale)\n")
kept=0
for fen in cands:
    if kept>=TARGET: break
    stm0=fen.split(':',1)[0]
    mv=best(jass,fen,ORACLE_D)                 # coup optimal (egdb)
    if mv is None or mv.is_capture: continue   # on veut un sacrifice (coup tranquille)
    # applique le sac, verifie que l'adversaire est force de prendre
    ref.set_position_fen(fen)
    if not ref.apply_move(mv): continue
    nf=ref.current_fen()
    if not is_forcing(fen): continue           # le coup laisse l'adversaire en prise obligatoire
    # deroule la ligne egdb-optimale, cherche une promotion du camp au trait
    k0=stm_kings(fen,stm0); promoted=False; cur=nf
    for ply in range(WALK):
        mm=best(jass,cur,ORACLE_D)
        if mm is None: break
        ref.set_position_fen(cur)
        if not ref.apply_move(mm): break
        cur=ref.current_fen()
        if stm_kings(cur,stm0) > k0: promoted=True; break
    if not promoted: continue
    out.write(f"{fen}  # sac {mv.frm}-{mv.to} (egdb-win, dame en <= {WALK} demi-coups)\n"); out.flush(); kept+=1
out.close()
print(f"  positions PROUVEES (sac -> dame sure, egdb) : {kept}")
jass.close(); ref.close(); probe.close()
PY
cp "$W/promo_sac_tests.fen" "$ART/promo_sac_tests.fen" 2>/dev/null || true
NSET=$(grep -cvE '^\s*(#|$)' "$W/promo_sac_tests.fen" 2>/dev/null || echo 0)
[ "${NSET:-0}" -ge 5 ] || { say "  (set trop maigre: ${NSET})"; say "FIN"; exit 0; }

say ""; say "=== PHASE 2 : batterie EVAL-PUR (SANS egdb) — baseline vs no_reduce_forcing=1 ==="
export JASS CHAMP="$W/champ.pjtw"
python3 - "$W/promo_sac_tests.fen" <<'PY' 2>&1 | tee -a "$RES"
import os,sys,re
sys.path.insert(0,'tools')
from calibrate_vs_scan import JassEngine
JASS=os.environ["JASS"]; CHAMP=os.environ["CHAMP"]; MAN=85; WIN=int(1.5*MAN)
rows=[ln.split('#',1)[0].strip() for ln in open(sys.argv[1]) if ln.split('#',1)[0].strip()]
def eng(sp): return JassEngine(JASS, pattern_path=CHAMP, no_book=True, search_params=(sp or None))
def sc(e,fen,d):
    e.set_position_fen(fen); e._drain(); e._send(f"go depth {d}")
    L=e._read_until(lambda l:l.startswith("bestmove") or l.startswith("error"),timeout_s=120)[-1]
    if L.startswith("error"): return None
    m=re.search(r"score=(-?\d+)",L); return int(m.group(1)) if m else None
import statistics as st
configs=[("d11 base",11,""),("d11 FIX",11,"no_reduce_forcing=1"),
         ("d15 base",15,""),("d15 FIX",15,"no_reduce_forcing=1"),
         ("d18 base",18,""),("d18 FIX",18,"no_reduce_forcing=1")]
N=len(rows); print(f"  positions test = {N}  (detecte = score >= +1.5 homme = {WIN}) ; rappel eval-pur, SANS egdb")
print(f"  {'config':>9} | {'detecte':>10} | {'score med':>9}")
for name,d,sp in configs:
    e=eng(sp); scs=[s for s in (sc(e,f,d) for f in rows) if s is not None]; e.close()
    det=sum(1 for s in scs if s>=WIN)
    print(f"  {name:>9} | {det:>4}/{N} {100*det/max(N,1):>3.0f}% | {int(st.median(scs)) if scs else 0:>9}")
print("\n  LECTURE : FIX>>base a prof egale => le fix debloque les sacs de promotion. Monte avec la prof => horizon.")
print("            reste bas partout => l'eval ne capte pas le motif meme roi-value OK (a investiguer : features).")
PY
say ""; say "# set egdb-PROUVE : artefacts/promo_sac_tests.fen (a committer en data/ pour la batterie permanente)."
