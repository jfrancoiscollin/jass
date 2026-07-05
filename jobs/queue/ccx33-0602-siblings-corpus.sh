#!/usr/bin/env bash
# id: ccx33-0602-siblings-corpus
# description: PISTE (a) etape 1 — valide le mode --gen-siblings (develop 874bf360) au runtime ET produit le mini-corpus
# de fratries 50k parents (manifest). Pour chaque parent QUIET, recherche chaque enfant a d9 eval-pur (pilote=gen1), emet
# les paires ordonnees parent-POV a marge>=15cp, sortie JNNW par couples (2k=better,2k+1=worse). Shardé (NCPU instances sur
# des tranches du corpus, merge). Manifest = comptes/phase, marge moyenne, nb paires. C'est de la DATA (utile quel que soit
# le verdict ordering 0600/0601) ; le FIT+G1 (la decision) vient APRES lecture de 0600/0601. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0602-siblings-corpus/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0602-siblings-corpus/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-sib; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
NPAR=50000; DEPTH=9; MMIN=15

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== siblings-corpus (piste a etape 1) — HEAD main $(git log --oneline -1|cat) ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; git checkout -- src/main.cpp; exit 6; }
J="$W/build/jass"; git checkout -- src/main.cpp 2>/dev/null || true
"$J" --gen-siblings 2>&1 | head -1 | grep -q 'usage' && say "  --gen-siblings present ✓" || say "  ⚠ mode absent ?"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw" || { say "ABORT corpus"; exit 4; }

# split corpus en NCPU sous-corpus (tranches de records) pour paralleliser
python3 - "$W/corpus.jnnw" "$W/sh" "$NCPU" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38; body=b[8:]; nsh=int(sys.argv[3]); per=(n+nsh-1)//nsh
for s in range(nsh):
    lo=s*per; hi=min((s+1)*per,n); m=max(0,hi-lo)
    open(f"{sys.argv[2]}.{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',m)+(body[lo*REC:hi*REC] if m else b''))
print(f"  corpus={n} -> {nsh} shards de ~{per}")
PY
PERSH=$(( (NPAR + NCPU - 1) / NCPU ))
say "=== gen-siblings x$NCPU (d$DEPTH, m_min=$MMIN, ~$PERSH parents/shard) ==="
for s in $(seq 0 $((NCPU-1))); do "$J" --gen-siblings "$W/sh.$s.jnnw" "$W/pairs.$s.jnnw" "$DEPTH" \
   --nnue "$W/gen1.pjtw" --m-min "$MMIN" --max-parents "$PERSH" >"$W/g_$s.log" 2>&1 & done; wait
grep -h '^GENSIB' "$W"/g_*.log | sed 's/^/  /' | tee -a "$RES" >/dev/null
# merge (concat records, alignement pair preserve car chaque shard est pair)
python3 - "$W/siblings-50k.jnnw" "$W"/pairs.*.jnnw <<'PY' 2>&1 | tee -a "$RES"
import struct,glob,sys
out=sys.argv[1]; body=b""; tot=0
for f in sorted(sys.argv[2:]):
    try: b=open(f,'rb').read()
    except: continue
    if len(b)<8 or b[:4]!=b'JNNW': continue
    m=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+m*38]; tot+=m
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body)
print(f"  MERGE : {tot} records = {tot//2} paires")
PY
# manifest agrege
python3 - "$W"/g_*.log <<'PY' 2>&1 | tee -a "$RES"
import re,sys
seen=used=cap=pairs=0; mm=0.0; ph=[0,0,0,0]; nlog=0
for f in sys.argv[1:]:
    for ln in open(f):
        m=re.search(r'GENSIB parents_seen=(\d+) quiet_used=(\d+) cap_nodes=(\d+) pairs=(\d+) records=\d+ depth=\d+ m_min=\d+ margin_mean=([\d.]+) phase\[fin/13-20/21-28/ouv\]=(\d+)/(\d+)/(\d+)/(\d+)',ln)
        if m:
            seen+=int(m.group(1)); used+=int(m.group(2)); cap+=int(m.group(3)); pairs+=int(m.group(4))
            mm+=float(m.group(5)); nlog+=1
            for k in range(4): ph[k]+=int(m.group(6+k))
print(f"  MANIFEST : parents_seen={seen} quiet_used={used} cap_nodes={cap} ({cap/max(1,seen)*100:.0f}% captures)")
print(f"    pairs={pairs} ; margin_mean~{mm/max(1,nlog):.0f}cp ; phase[fin/13-20/21-28/ouv]={ph} (finale%={ph[0]/max(1,pairs)*100:.0f})")
PY
gzip -c "$W/siblings-50k.jnnw" > "$ART/siblings-50k.jnnw.gz"
commit_to_main "$ART/siblings-50k.jnnw.gz" "$ARTREL/siblings-50k.jnnw.gz" "siblings-corpus: 50k parents, paires d9 m_min15 (piste-a etape 1)" \
  && say "  corpus committe job-side ($(du -h "$ART/siblings-50k.jnnw.gz"|cut -f1))" || say "  ⚠ commit corpus echoue"
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0602 siblings-corpus : valide --gen-siblings + manifest 50k (piste-a etape 1)" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "  => prochaine etape (apres lecture 0600/0601) : trainer rank-loss + G1 (survie held-out)."
say "=== fin siblings-corpus ==="
