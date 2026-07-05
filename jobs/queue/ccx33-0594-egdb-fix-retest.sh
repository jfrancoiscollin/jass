#!/usr/bin/env bash
# id: ccx33-0594-egdb-fix-retest
# description: FIX + RETEST EGDB (JFC). Cause racine trouvee : mes jobs 0587/0589/0590 pointaient JASS_EGDB_PATH /
# --egdb-relabel sur /root/egdb_extracted (PARENT) alors que les fichiers DB (db2.idx1, db5.idx1 ... base WLD 6-pieces)
# sont dans le SOUS-DOSSIER /root/egdb_extracted/app (cf jobs 0286/0287/0295/0319 qui marchaient). egdb_identify(parent)
# echoue => init false => available=false => tb_relabel=0 / egdb-relabel "echoue". Ici on PROUVE le fix par un A/B de
# chemin : egdb-relabel au MAUVAIS chemin (attendu: fail/0) vs au BON chemin /app (attendu: egdb-resolved>0, changes>0,
# stalls>0). Sur un echantillon corpus riche en finales (<=6 pieces couverts par la base). Si /app resout => EGDB REPARE,
# on pourra re-tester tb-relabel proprement. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0594-egdb-fix-retest/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0594-egdb-fix-retest/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-egdbfix; rm -rf "$W"; mkdir -p "$W"
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
PARENT=/root/egdb_extracted; APP=/root/egdb_extracted/app; K=300000

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== EGDB FIX + RETEST — HEAD $(git log --oneline -1|cat) ==="
say "  structure /root/egdb_extracted :"
{ ls -la "$PARENT" 2>&1 | head -20; echo "  --- app/ ---"; ls "$APP" 2>&1 | head -12; } | sed 's/^/    /' | tee -a "$RES"
say "  fichiers DB attendus dans app/ : $(ls "$APP"/db*.idx1 2>/dev/null | wc -l) *.idx1 ; taille app/=$(du -sh "$APP" 2>/dev/null|cut -f1)"

# build EGDB
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT build egdb non actif"; tail -8 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw" || { say "ABORT corpus"; exit 4; }

# echantillon + comptage <=6 pieces (couverture de la base 6-pieces)
python3 - "$W/corpus.jnnw" "$W/sub.jnnw" "$K" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys
d=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',d[4:8])[0]; REC=38; body=d[8:]; K=int(sys.argv[3])
step=max(1,n//K); idx=list(range(0,n,step))[:K]; out=bytearray()
def pc(r):
    wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); return bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
le6=0
for i in idx:
    r=body[i*REC:(i+1)*REC]; out+=r
    if pc(r)<=6: le6+=1
open(sys.argv[2],'wb').write(b'JNNW'+struct.pack('<I',len(idx))+bytes(out))
print(f"  echantillon={len(idx)} pos ; <=6 pieces (couverts par la base)={le6} ({le6/len(idx)*100:.2f}%)")
PY

# ---- A/B chemin : egdb-relabel MAUVAIS (parent) vs BON (/app) ----
say ""; say "=== A/B CHEMIN : egdb-relabel (init -> egdb_identify -> egdb_open) ==="
say "  [MAUVAIS] db_dir=$PARENT (mon bug 0587/0589/0590) :"
"$J" --egdb-relabel "$W/sub.jnnw" "$PARENT" "$W/out_wrong.jnnw" 512 >"$W/wrong.log" 2>&1; RCW=$?
{ echo "    rc=$RCW"; sed 's/^/    /' "$W/wrong.log" | head -4; } | tee -a "$RES"
say "  [BON] db_dir=$APP :"
"$J" --egdb-relabel "$W/sub.jnnw" "$APP" "$W/out_right.jnnw" 512 >"$W/right.log" 2>&1; RCR=$?
{ echo "    rc=$RCR"; sed 's/^/    /' "$W/right.log" | head -4; } | tee -a "$RES"

# extraire les chiffres cle du bon chemin
RESOLVED=$(grep -oE '[0-9]+ egdb-resolved' "$W/right.log" | grep -oE '[0-9]+' | head -1)
CHANGED=$(grep -oE '[0-9]+ labels changed' "$W/right.log" | grep -oE '[0-9]+' | head -1)
STALLS=$(grep -oE '[0-9]+ stalls' "$W/right.log" | grep -oE '[0-9]+' | head -1)
say ""
say "=== VERDICT FIX ==="
if [ "${RESOLVED:-0}" -gt 0 ] 2>/dev/null; then
  say "  ✅ EGDB REPARE : /app resout $RESOLVED positions (dont $CHANGED labels changes, $STALLS stalls=finales gagnees/perdues"
  say "     etiquetees nulles = le VRAI biais finale). Le bug etait bien le chemin (/app manquant). Le mauvais chemin a rc=$RCW."
  say "  => On peut re-tester tb-relabel proprement (gen avec JASS_EGDB_PATH=$APP) : la manche 0589 est a refaire avec /app."
  say "     Rappel couverture : base 6-pieces => tb-relabel ne corrige QUE les finales <=6 pieces (fraction du biais 0590 <=12)."
else
  say "  ❌ /app ne resout toujours rien (rc=$RCR) => le probleme n'est PAS que le chemin. Voir right.log :"
  sed 's/^/    /' "$W/right.log" | head -12 | tee -a "$RES"
  say "     verifier : base extraite complete ? maxpieces ? egdb_identify sur $APP."
fi
gzip -c "$W/right.log" > "$ART/egdb-right.log.gz" 2>/dev/null || true
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0594 egdb fix+retest : A/B chemin parent-vs-app (root cause = /app manquant), egdb-relabel resolved?" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin egdb fix+retest ==="
