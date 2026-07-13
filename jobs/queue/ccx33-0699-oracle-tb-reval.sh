#!/usr/bin/env bash
# id: ccx33-0699-oracle-tb-reval
# description: REVALIDATION MOTEUR des oracles dilf E1/E2 (gravé A4 : verified_engine=true ou quarantaine). Les 390
# claims (data/pcblues_oracles.jsonl : 193 TB-eligible ≤7p + 197 >7p) sont position-vérifiés par re-jeu côté dilf mais
# le VERDICT du livre (expected) n'est pas encore validé moteur. Ce job fait la revalidation EXACTE des 193 ≤7p par
# egdb (--egdb-relabel, WLD exact STM-POV) : expected==TB -> verified_engine=true ; expected!=TB -> QUARANTAINE ;
# expected null -> TB REMPLIT (verified, TB-labellisé). Les >7p (locks middlegame) exigent un harnais search-d14
# (verdict fuzzy) = FOLLOW-UP séparé, listés ici mais non tranchés. Sortie : oracles_verified.jsonl + quarantine +
# stats d'accord par famille. Build JASS_EGDB=ON. Léger (build ~5min + relabel qq sec). Robustesse (df, RES hors-arbre,
# pull src divergents develop, garde-fou archi). AUCUN NNUE. Ne touche pas le champion.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0699-oracle-tb-reval/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0699-oracle-tb-reval/artefacts"
W=/root/cw-oracrev
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 3000 ] || { echo "ABORT disque <3Go"; exit 3; }
CMK="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== revalidation TB oracles E1/E2 — HEAD $(git log --oneline -1|cat) — df=${DFA}Mo ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
for f in $DIVERGED; do git show "origin/develop:$f" > "$f"; done
restore_src(){ git checkout -- src pattern_jass/src 2>/dev/null||true; }
grep -q "g_emasks" src/scan_eval.cpp || { say "ABORT archi"; restore_src; exit 5; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT egdb"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0699 ABORT egdb"; exit 4; }
cmake -S . -B "$W/build" $CMK >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" \
  || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0699 ABORT cmake"; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0699 ABORT build"; exit 6; }
J="$W/build/jass"; restore_src
git show origin/main:data/pcblues_oracles.jsonl > "$W/oracles.jsonl" || { say "ABORT oracles absent"; exit 4; }
say "  ✓ build egdb ($EGDIR) ; oracles=$(grep -c . "$W/oracles.jsonl")"

# --- FEN -> JNNW (≤7p uniquement) avec index pour recoller expected ---
python3 - "$W/oracles.jsonl" "$W/tb.jnnw" "$W/idx.tsv" <<'PY' | tee -a "$RES"
import json,struct,sys
REC=38
orc,outj,outi=sys.argv[1],sys.argv[2],sys.argv[3]
def parse(fen):
    turn,rest=fen.split(':',1); stm=1 if turn.strip().upper().startswith('B') else 0
    wm=wk=bm=bk=0
    for part in rest.split(':'):
        side=part[0].upper()
        for tok in part[1:].split(','):
            tok=tok.strip()
            if not tok: continue
            king=tok[0].upper()=='K'; s=int(tok[1:] if king else tok); bit=1<<(s-1)
            if side=='W': (wk:=wk|bit) if king else (wm:=wm|bit)
            else: (bk:=bk|bit) if king else (bm:=bm|bit)
    return wm,wk,bm,bk,stm
recs=[]; idx=[]
for line in open(orc):
    d=json.loads(line)
    if not d.get('tb_eligible'): continue
    wm,wk,bm,bk,stm=parse(d['fen'])
    recs.append(struct.pack('<QQQQ',wm,wk,bm,bk)+struct.pack('<B',stm)+struct.pack('<i',0)+struct.pack('<b',0))
    idx.append((d['position_hash'], d.get('expected') or 'NULL', d.get('family','?')))
open(outj,'wb').write(b'JNNW'+struct.pack('<I',len(recs))+b''.join(recs))
open(outi,'w').write("\n".join(f"{h}\t{e}\t{f}" for h,e,f in idx)+"\n")
print(f"  TB-eligible ≤7p convertis : {len(recs)}")
PY
NTB=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/tb.jnnw','rb').read(8)[4:8])[0])")

# --- relabel egdb (WLD exact) ---
say ""; say "=== --egdb-relabel (WLD exact STM-POV) sur $NTB positions ≤7p ==="
"$J" --egdb-relabel "$W/tb.jnnw" "$EGDIR" "$W/tb_rel.jnnw" 2048 >"$W/rel.log" 2>&1 || { say "ABORT relabel"; tail -4 "$W/rel.log"|sed 's/^/  /'; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0699 ABORT relabel"; exit 7; }
say "  $(grep -i 'egdb-relabel' "$W/rel.log" | head -1)"

# --- comparer TB vs expected -> verified / quarantine / filled ---
python3 - "$W/tb_rel.jnnw" "$W/idx.tsv" "$ART/oracles_verified.jsonl" "$ART/oracles_quarantine.jsonl" <<'PY' | tee -a "$RES"
import json,struct,sys,collections
REC=38
rel,idxf,vout,qout=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4]
b=open(rel,'rb').read(); n=struct.unpack('<I',b[4:8])[0]
wdls=[struct.unpack_from('<b',b,8+i*REC+37)[0] for i in range(n)]
idx=[l.rstrip('\n').split('\t') for l in open(idxf) if l.strip()]
assert len(idx)==n, (len(idx),n)
def tb_verdict(w): return {1:'WIN',0:'DRAW',-1:'LOSS'}.get(w,'?')
ver=[]; quar=[]; agree=collections.Counter(); tot=collections.Counter()
for (h,exp,fam),w in zip(idx,wdls):
    tbv=tb_verdict(w); tot[fam]+=1
    rec={"position_hash":h,"family":fam,"expected":exp,"tb_verdict":tbv,"verified_engine":True}
    if exp=='NULL':
        rec["note"]="TB-labelled (expected était null)"; ver.append(rec); agree[fam]+=1
    elif exp==tbv:
        ver.append(rec); agree[fam]+=1
    else:
        rec["verified_engine"]=False; rec["reason"]="expected != TB"; quar.append(rec)
open(vout,'w').write("\n".join(json.dumps(r,ensure_ascii=False) for r in ver)+"\n")
open(qout,'w').write("\n".join(json.dumps(r,ensure_ascii=False) for r in quar)+"\n")
print(f"  TB revalidation : verified={len(ver)}  quarantine={len(quar)}  (sur {n} ≤7p)")
for fam in sorted(tot):
    print(f"    {fam}: {agree[fam]}/{tot[fam]} accord TB")
# taux d'accord sur les non-null seulement (le vrai signal de qualité des verdicts livre)
nn=sum(1 for (h,e,f) in idx if e!='NULL'); nnq=len(quar)
print(f"  ACCORD verdict-livre vs TB (non-null) : {nn-nnq}/{nn} = {100*(nn-nnq)/max(nn,1):.1f}%")
PY

say ""; say "  >7p (197 locks/finales profondes) = revalidation search-d14 = FOLLOW-UP (harnais verdict à écrire)."
commit_to_main "$ART/oracles_verified.jsonl" "$ARTREL/oracles_verified.jsonl" "0699 oracles verified (TB)" >/dev/null 2>&1 || true
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0699 FIN revalidation TB oracles E1/E2 : accord verdict-livre vs TB" \
  && say "  ✓ RESULTS committé" || say "  ⚠ commit échoue"
say "=== 0699 FINI ==="
