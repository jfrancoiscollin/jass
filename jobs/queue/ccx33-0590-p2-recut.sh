#!/usr/bin/env bash
# id: ccx33-0590-p2-recut
# description: P2 RE-CUT INSTRUMENTE (mini-memo JFC) — l'audit 0585 n'a stocke que la matrice AGREGEE ; le tableau
# phase x classe (le coeur decisionnel) exige le per-sample jamais dumpe. Ici on RE-AUDITE le MEME echantillon
# (corpus-regen-mix2M, strat par phase, sampling deterministe identique 0583) et on DUMPE un CSV per-sample
# {idx, pieces, band, label_wdl, arbitre_score_BRUT, tb_verdict}. Arbitre = deep-relabel d14 params coin (SANS --egdb
# => pur d14, identique 0585). TB-verdict = --egdb-relabel avec astuce SENTINELLE (byte37:=2 avant probe => 2 restant
# = hors-TB=NA, sinon = verdict TB exact). Post-traitement PUR : classes C1(unconverted/BIAIS) C2(signe-inverse/BIAIS)
# C3(label-decisif arb-nul/VARIANCE) par phase, AUX SEUILS bruts {25,50,100}, + controle erreur-arbitre vs TB en finale
# (borne la part 'erreur d'arbitre' du desaccord hors-finale). CSV committe => re-cut a tout seuil pour toujours.
# NB : ply/longueur-restante PAS dans le record 38B => proxy indisponible (corroborant, non decisif). AUCUN NNUE, AUCUNE
# distillation (deep-search = mesure de coherence, jamais source de label). Code arbitre depuis DEVELOP.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0590-p2-recut/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0590-p2-recut/artefacts"
W=/root/cw-p2recut; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0566-regen-mix-oncoin/artefacts/corpus-regen-mix2M.jnnw.gz
ARB_DEPTH=14; N=1600; DRAWBAND=50
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

say "=== P2 RE-CUT instrumente (arbitre d${ARB_DEPTH} + TB) — HEAD $(git log --oneline -1|cat) ==="
# build EGDB (necessaire pour --egdb-relabel ; deep-relabel reste pur d14 car appele SANS --egdb)
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
HAVE_TB=0
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
if grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" && [ -d /root/egdb_extracted ]; then HAVE_TB=1; else
  say "  (EGDB indispo -> build simple, controle TB = N/A) : egdb_build=$(grep -c 'EXTERNAL EGDB ENABLED' "$W/cmake.log") data=$([ -d /root/egdb_extracted ]&&echo 1||echo 0)"
  cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
        -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake2.log" 2>&1
fi
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw" || { say "ABORT corpus"; exit 4; }
say "  HAVE_TB=$HAVE_TB (controle erreur-arbitre) ; N=$N (400/bande) ; arbitre pur d${ARB_DEPTH} (deep-relabel sans --egdb)"

# echantillon stratifie par phase — SAMPLING DETERMINISTE IDENTIQUE 0583 (per=N/4 par bande)
python3 - "$W/corpus.jnnw" "$W/sub.jnnw" "$N" <<'PY' | tee -a "$VERD"
import struct,sys,collections
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38; body=b[8:]; K=int(sys.argv[3])
def pc(r):
    wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); return bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
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

# ---- arbitre : deep-relabel d14 (SANS --egdb => pur d14, identique 0585) ; score BRUT ecrit en byte 33-37 ----
python3 - "$W/sub.jnnw" "$W/ash" "$NCPU" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38; body=b[8:]; nsh=int(sys.argv[3]); per=(n+nsh-1)//nsh
for s in range(nsh):
    lo=s*per; hi=min((s+1)*per,n); m=max(0,hi-lo)
    open(f"{sys.argv[2]}.{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',m)+(body[lo*REC:hi*REC] if m else b''))
PY
say "=== deep-relabel arbitre (d${ARB_DEPTH}, params coin defaut, SANS egdb) ==="
for s in $(seq 0 $((NCPU-1))); do "$J" --deep-relabel "$W/ash.$s.jnnw" "$W/adeep.$s.jnnw" "$ARB_DEPTH" \
    --nnue "$W/gen1.pjtw" --draw-band "$DRAWBAND" >"$W/arl_$s.log" 2>&1 & done; wait
merge_into "$W/adeep.jnnw" "$W/adeep.*.jnnw" >/dev/null

# ---- TB-verdict : sentinelle byte37:=2 puis --egdb-relabel (2 restant=NA, sinon=verdict TB) ----
if [ "$HAVE_TB" = 1 ]; then
  python3 - "$W/sub.jnnw" "$W/tbprobe.jnnw" <<'PY'
import struct,sys
b=bytearray(open(sys.argv[1],'rb').read()); n=struct.unpack('<I',b[4:8])[0]; REC=38
for i in range(n): b[8+i*REC+37]=2   # sentinelle hors-plage wdl
open(sys.argv[2],'wb').write(bytes(b))
PY
  "$J" --egdb-relabel "$W/tbprobe.jnnw" /root/egdb_extracted "$W/tb.jnnw" >"$W/tb.log" 2>&1 \
    && say "  egdb-relabel : $(tail -1 "$W/tb.log")" || { say "  ⚠ egdb-relabel echoue -> TB N/A"; HAVE_TB=0; }
fi

# ---- DUMP CSV per-sample + POST-TRAITEMENT (classes x phase x seuils + controle erreur-arbitre TB) ----
say ""; say "=== RE-CUT : CSV per-sample + phase x classe aux seuils bruts {25,50,100} ==="
TBARG="$W/tb.jnnw"; [ "$HAVE_TB" = 1 ] || TBARG="NONE"
python3 - "$W/sub.jnnw" "$W/adeep.jnnw" "$TBARG" "$ART/p2-recut.csv" <<'PY' 2>&1 | tee -a "$VERD"
import struct,sys,collections,math
REC=38
sub=open(sys.argv[1],'rb').read();  ns=struct.unpack('<I',sub[4:8])[0];  sb=sub[8:]
adp=open(sys.argv[2],'rb').read();  na=struct.unpack('<I',adp[4:8])[0];  ab=adp[8:]
tbp=None
if sys.argv[3]!="NONE":
    tbb=open(sys.argv[3],'rb').read(); tbp=tbb[8:] if tbb[:4]==b'JNNW' else None
m=min(ns,na)
def pc(r):
    wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); return bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
def band(p): return 0 if p<=12 else (1 if p<=20 else (2 if p<=28 else 3))
BN={0:'finale<=12',1:'milieu13-20',2:'milieu21-28',3:'ouverture>=29'}
rows=[]
for i in range(m):
    ro=sb[i*REC:(i+1)*REC]; rd=ab[i*REC:(i+1)*REC]
    lab=struct.unpack('<b',ro[37:38])[0]
    sc =struct.unpack('<i',rd[33:37])[0]
    p=pc(ro); bi=band(p)
    tv=None
    if tbp is not None:
        t=struct.unpack('<b',tbp[i*REC+37:i*REC+38])[0]
        tv = None if t==2 else t
    rows.append((i,p,bi,lab,sc,tv))
# CSV
with open(sys.argv[4],'w') as f:
    f.write("idx,pieces,band,label_wdl,arb_score_raw,tb_verdict\n")
    for (i,p,bi,lab,sc,tv) in rows:
        f.write(f"{i},{p},{bi},{lab},{sc},{'' if tv is None else tv}\n")
print(f"  CSV : {len(rows)} lignes -> p2-recut.csv")
# distribution des |score| arbitre (mapping seuil<->pion)
mags=sorted(abs(sc) for (_,_,_,_,sc,_) in rows)
def pct(q):
    k=int(q*(len(mags)-1)); return mags[k]
print(f"  |arb_score| percentiles : p50={pct(.5)} p75={pct(.75)} p90={pct(.90)} p95={pct(.95)} max={mags[-1]}")
print(f"  (seuil T en unites brutes du score ; si 100~=1 pion alors T=25/50/100 ~ 0.25/0.50/1.0 pion)")

def sign(x,T): return 1 if x>T else (-1 if x<-T else 0)
def recut(T):
    # par bande : C1 unconverted, C2 signe-inverse, C3 variance, agree_dec, agree_draw
    tab=collections.defaultdict(lambda: collections.Counter())
    for (_,_,bi,lab,sc,_) in rows:
        a=sign(sc,T)
        if a!=0 and lab==0:            tab[bi]['C1']+=1
        elif a!=0 and lab!=0 and a!=lab:tab[bi]['C2']+=1
        elif a!=0 and lab!=0 and a==lab:tab[bi]['agree_dec']+=1
        elif a==0 and lab!=0:          tab[bi]['C3']+=1
        else:                          tab[bi]['agree_draw']+=1
    return tab
for T in (25,50,100):
    tab=recut(T)
    print("")
    print(f"  ---- SEUIL brut T={T} ----")
    print(f"  {'phase':>13} | {'n':>4} {'C1':>4} {'C2':>4} | {'C3':>4} | {'agD':>4} {'agN':>4} | desaccord(C1+C2)/arb-dec")
    tot=collections.Counter()
    for bi in range(4):
        c=tab[bi]; n=sum(c.values()); tot.update(c)
        arbdec=c['C1']+c['C2']+c['agree_dec']; dis=c['C1']+c['C2']
        r=f"{dis}/{arbdec}={dis/arbdec:.2f}" if arbdec else "-"
        print(f"  {BN[bi]:>13} | {n:>4} {c['C1']:>4} {c['C2']:>4} | {c['C3']:>4} | {c['agree_dec']:>4} {c['agree_draw']:>4} | {r}")
    arbdec=tot['C1']+tot['C2']+tot['agree_dec']; dis=tot['C1']+tot['C2']
    print(f"  {'TOTAL':>13} | {sum(tot.values()):>4} {tot['C1']:>4} {tot['C2']:>4} | {tot['C3']:>4} | {tot['agree_dec']:>4} {tot['agree_draw']:>4} | {dis}/{arbdec}={dis/arbdec:.3f}" if arbdec else "")
    print(f"     => desaccord = C1({tot['C1']})+C2({tot['C2']}) = BIAIS ; C3({tot['C3']}) = variance (hors desaccord) ; C4 (bord de seuil)=0 en recompute propre")

# ---- controle erreur-arbitre vs TB (la ou la verite existe) ----
tbrows=[r for r in rows if r[5] is not None]
if tbrows:
    print("")
    print(f"  ==== CONTROLE ERREUR-ARBITRE vs TB ({len(tbrows)} pos resolues TB, seuil T=50) ====")
    T=50
    # arbitre se trompe : sign(arb,T) != tb_sign
    arb_err=sum(1 for (_,_,_,_,sc,tv) in tbrows if sign(sc,T)!=(1 if tv>0 else (-1 if tv<0 else 0)))
    # label ment vs TB (vrai unconverted en finale) : lab != tb_sign
    lab_err=sum(1 for (_,_,_,lab,_,tv) in tbrows if lab!=(1 if tv>0 else (-1 if tv<0 else 0)))
    # arbitre decisif ET tb decisif mais signes opposes (vraie erreur grave arbitre)
    tb_dec=[(sc,tv) for (_,_,_,_,sc,tv) in tbrows if tv!=0]
    arb_flip=sum(1 for (sc,tv) in tb_dec if sign(sc,T)!=0 and sign(sc,T)!=(1 if tv>0 else -1))
    print(f"  arbitre != TB      : {arb_err}/{len(tbrows)} = {arb_err/len(tbrows):.3f}  (borne la part 'erreur arbitre' du desaccord)")
    print(f"  label   != TB      : {lab_err}/{len(tbrows)} = {lab_err/len(tbrows):.3f}  (vrai taux de label-ment en finale, ancre TB)")
    if tb_dec: print(f"  arbitre signe-inverse vs TB-decisif : {arb_flip}/{len(tb_dec)} = {arb_flip/len(tb_dec):.3f}  (erreur grave arbitre)")
    print(f"  => si erreur-arbitre >0 la ou TB tranche, une PART du desaccord hors-finale est de l'ARBITRE, pas du label.")
else:
    print("")
    print("  (controle erreur-arbitre TB : N/A — HAVE_TB=0)")
print("")
print("  ROUTAGE (mini-memo §2) : finale C1-dominee => biais (coherent tb-relabel +18) ; ouverture C3-dominee => axe")
print("  label FERME (variance saine + erreur-arbitre) ; milieu 21-28 C1 substantiel => biais milieu actionnable (E3 /")
print("  multi-rollout doux, JAMAIS relabel-arbitre). Conclure sur les 2 seuils.")
PY

gzip -c "$ART/p2-recut.csv" > "$ART/p2-recut.csv.gz" 2>/dev/null || true
commit_to_main "$ART/p2-recut.csv.gz" "$ARTREL/p2-recut.csv.gz" "0590 p2-recut : CSV per-sample {phase,label,score arbitre brut,TB} (re-cut a tout seuil)" \
  && say "  CSV committe job-side" || say "  ⚠ commit CSV echoue"
commit_to_main "$VERD" "$ARTREL/VERDICT.txt" "0590 p2-recut : tableau phase x classe (C1/C2/C3) aux seuils {25,50,100} + controle erreur-arbitre TB" \
  && say "  VERDICT committe ✓" || say "  ⚠ commit verdict echoue"
say "=== fin p2-recut ==="
