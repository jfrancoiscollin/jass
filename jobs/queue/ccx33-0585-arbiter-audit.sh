#!/usr/bin/env bash
# id: ccx33-0585-arbiter-audit
# description: P2 batterie sanity gen (JFC) — AUDIT ARBITRE FORT : la seule mesure DIRECTE de verite des labels. On
# echantillonne ~800 positions du corpus (corpus-regen-mix2M), on les fait trancher par l'arbitre le plus fort dispo
# (champion gen1 + archi complete + coin, deep-search d14 + qs_sacs) et on mesure le TAUX DE DESACCORD label-stocke
# (issue-partie WDL) vs arbitre, par PHASE + matrice de confusion. Un desaccord eleve sur les gagnes-non-convertis =
# le "23%" chiffre directement (nos labels mentent la ou le self-play faible n'a pas converti). Diagnostique aussi le
# 100%/100% buggé de 0582 (on imprime toute la distribution). L'arbitre = mesure de COHERENCE (angles morts V^pi), a
# croiser TB ou elle porte. Lectures = deep-search, pas de source de label => pas de distillation. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0585-arbiter-audit/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0585-arbiter-audit/artefacts"
W=/root/cw-arb; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0566-regen-mix-oncoin/artefacts/corpus-regen-mix2M.jnnw.gz
ARB_DEPTH=14; N=800; DRAWBAND=50
VERD="$ART/VERDICT.txt"; : > "$VERD"; say(){ echo "$@" | tee -a "$VERD"; }

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
merge_into(){ python3 - "$@" <<'PY'
import struct,glob,sys
out=sys.argv[1]; body=b""; tot=0
for p in sys.argv[2:]:
    for f in sorted(glob.glob(p)):
        try: b=open(f,'rb').read()
        except: continue
        if len(b)<8 or b[:4]!=b'JNNW': continue
        n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*38]; tot+=n
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body); print(tot)
PY
}

say "=== P2 AUDIT ARBITRE (champion+coin d${ARB_DEPTH}) — HEAD $(git log --oneline -1|cat) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw" || { say "ABORT corpus"; exit 4; }

# echantillon stratifie par phase (nb pieces) : ~N positions reparties
python3 - "$W/corpus.jnnw" "$W/sub.jnnw" "$N" <<'PY'
import struct,sys,collections
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38; body=b[8:]; K=int(sys.argv[3])
def pc(r):
    wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); return bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
# bucket par phase, prendre ~K/4 par bande
bands={0:(0,12),1:(13,20),2:(21,28),3:(29,40)}; byb=collections.defaultdict(list)
step=max(1,n//(K*6))
for i in range(0,n,step):
    r=body[i*REC:(i+1)*REC]; p=pc(r)
    for bi,(lo,hi) in bands.items():
        if lo<=p<=hi: byb[bi].append(r); break
recs=[]; per=K//4
for bi in range(4): recs+=byb[bi][:per]
open(sys.argv[2],'wb').write(b'JNNW'+struct.pack('<I',len(recs))+b''.join(recs))
print(f"  echantillon : {len(recs)} pos ({[len(byb[b][:per]) for b in range(4)]} par bande phase)")
PY

# split + deep-relabel (arbitre d14, params defaut = coin+qs_sacs) => score = valeur arbitre
python3 - "$W/sub.jnnw" "$W/ash" "$NCPU" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38; body=b[8:]; nsh=int(sys.argv[3]); per=(n+nsh-1)//nsh
for s in range(nsh):
    lo=s*per; hi=min((s+1)*per,n); m=max(0,hi-lo)
    open(f"{sys.argv[2]}.{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',m)+(body[lo*REC:hi*REC] if m else b''))
PY
say "=== deep-relabel arbitre (d${ARB_DEPTH}, params coin defaut) ==="
for s in $(seq 0 $((NCPU-1))); do "$J" --deep-relabel "$W/ash.$s.jnnw" "$W/adeep.$s.jnnw" "$ARB_DEPTH" \
    --nnue "$W/gen1.pjtw" --draw-band "$DRAWBAND" >"$W/arl_$s.log" 2>&1 & done; wait
merge_into "$W/adeep.jnnw" "$W/adeep.*.jnnw" >/dev/null

# analyse : desaccord label(wdl-partie) vs arbitre(sign deep-score), + matrice + par phase
python3 - "$W/sub.jnnw" "$W/adeep.jnnw" "$DRAWBAND" <<'PY' 2>&1 | tee -a "$VERD"
import struct,sys,collections
REC=38
orig=open(sys.argv[1],'rb').read(); no=struct.unpack('<I',orig[4:8])[0]; ob=orig[8:]
deep=open(sys.argv[2],'rb').read(); nd=struct.unpack('<I',deep[4:8])[0]; db=deep[8:]
band=int(sys.argv[3]); m=min(no,nd)
def pc(r):
    wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); return bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
conf=collections.Counter(); phase_dis=collections.defaultdict(lambda:[0,0]); sc_hist=collections.Counter()
lab_hist=collections.Counter()
for i in range(m):
    ro=ob[i*REC:(i+1)*REC]; rd=db[i*REC:(i+1)*REC]
    wdl=struct.unpack('<b',ro[37:38])[0]            # label = issue partie (STM-POV)
    sc=struct.unpack('<i',rd[33:37])[0]             # arbitre = deep-score (STM-POV, reecrit)
    arb = 1 if sc>band else (-1 if sc<-band else 0)
    lab_hist[wdl]+=1; sc_hist[arb]+=1; conf[(wdl,arb)]+=1
    p=pc(ro); band_i=0 if p<=12 else (1 if p<=20 else (2 if p<=28 else 3))
    # desaccord = arbitre DECISIF mais label different (on juge la ou l'arbitre a un avis)
    if arb!=0:
        phase_dis[band_i][1]+=1
        if arb!=wdl: phase_dis[band_i][0]+=1
print(f"positions appariees : {m} ; arbitre = champion+coin d-search, draw-band {band}")
print(f"distribution LABEL (wdl-partie) : win={lab_hist[1]} draw={lab_hist[0]} loss={lab_hist[-1]}")
print(f"distribution ARBITRE (deep sign): win={sc_hist[1]} draw={sc_hist[0]} loss={sc_hist[-1]}")
print("")
print("MATRICE label(ligne) x arbitre(col)  [W/D/L] :")
for wl in (1,0,-1):
    print(f"  label={wl:+d} : arb+1={conf[(wl,1)]:4d}  arb0={conf[(wl,0)]:4d}  arb-1={conf[(wl,-1)]:4d}")
# desaccord global sur positions ou l'arbitre est decisif
dec=sum(v for (w,a),v in conf.items() if a!=0); dis=sum(v for (w,a),v in conf.items() if a!=0 and a!=w)
print("")
print(f"DESACCORD (arbitre decisif, label != arbitre) : {dis}/{dec} = {dis/dec:.3f}" if dec else "  (arbitre jamais decisif ?!)")
print("par PHASE (bande pieces) :")
names={0:'finale<=12',1:'13-20',2:'21-28',3:'ouverture>=29'}
for bi in range(4):
    d,t=phase_dis[bi]
    print(f"  {names[bi]:>14} : desaccord {d}/{t} = {d/t:.3f}" if t else f"  {names[bi]:>14} : (aucune decisive)")
print("")
# le finding cle : gagnes-par-arbitre mais label PAS gagnant (unconverted / le 23%)
unconv = conf[(0,1)]+conf[(-1,1)] + conf[(0,-1)]+conf[(1,-1)]
arb_dec = sc_hist[1]+sc_hist[-1]
print(f"UNCONVERTED (arbitre decide gagnant/perdant mais label ne suit pas) : {unconv}/{arb_dec} = {unconv/arb_dec:.3f}" if arb_dec else "")
print("  => c'est la mesure directe du '23%' : fraction des positions ou le label ment sur l'issue reelle.")
PY
commit_to_main "$VERD" "$ARTREL/VERDICT.txt" "0583 audit arbitre : desaccord label vs deep-arbitre par phase (mesure directe verite des labels)" \
  && say "  VERDICT committe ✓" || say "  ⚠ commit echoue"
say "=== fin audit arbitre ==="
