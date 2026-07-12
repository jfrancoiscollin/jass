#!/usr/bin/env bash
# id: ccx33-0693-tb-exceptions-mine
# description: C4 MINAGE exceptions TB (go JFC "prepare job 3M" 2026-07-12, coucher — go explicite sans attendre le rate
# 0692, "tant pis"). Genere MINE_N=3M positions quietes egdb-resolvables EN SHARDS (--gen-egdb-wld, label WLD EXACT
# STM-POV, cf 0464 l.177) ; garde SEULEMENT les EXCEPTIONS (materiel STM-POV en desaccord avec le WDL : |bal|>=2&nulle,
# bal>=2&perd, bal<=-2&gagne — positions materiel-defiantes, plus haute valeur pedagogique). Produit = corpus versionne
# exceptions.jnnw. Le fit/A-B eval reste une etape ULTERIEURE gatee (prudence 0691). DURABILITE : shards de 500k,
# RESULTS + corpus committes A CHAQUE shard (regle 2, rien perdu si kill ; le 1er shard revele le rate reel). Le job
# tourne APRES 0692 (meme runner ccx33). Build JASS_EGDB=ON (pattern 0464). AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0693-tb-exceptions-mine/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0693-tb-exceptions-mine/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-tbmine; rm -rf "$W"; mkdir -p "$W"
MINE_N=${MINE_N:-3000000}       # go JFC : 3 M positions
SHARD=${SHARD:-500000}          # 6 shards ; commit progress+corpus par shard
MAXP=7; CACHE=2048; SEED0=69240
CMK="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== 0693 C4 minage TB-exceptions — MINE_N=$MINE_N SHARD=$SHARD — HEAD $(git log --oneline -1|cat) ==="
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT: egdb introuvable"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0693 ABORT egdb"; exit 4; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
say "  egdb : $EGDIR"
cmake -S . -B "$W/build" $CMK >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" \
  || { say "ABORT egdb build"; tail -8 "$W/cmake.log"|sed 's/^/  /'; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0693 ABORT cmake"; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 \
  || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0693 ABORT build"; exit 6; }
J="$W/build/jass"
ACC="$ART/exceptions.jnnw"; rm -f "$ACC"; : > "$W/tally"

filter_shard(){ python3 - "$1" "$ACC" "$W/tally" <<'PY'
import struct,sys,os
REC=38
src,acc,tally=sys.argv[1],sys.argv[2],sys.argv[3]
b=open(src,'rb').read(); assert b[:4]==b'JNNW'
n=struct.unpack('<I',b[4:8])[0]
def pc(x):
    c=0
    while x: x&=x-1; c+=1
    return c
keep=bytearray(); ex_draw=ex_loss=ex_win=0
off=8
for i in range(n):
    chunk=b[off:off+REC]; wm,wk,bm,bk,stm,score,wdl=struct.unpack('<QQQQBib',chunk); off+=REC
    bal=(pc(wm)+3*pc(wk))-(pc(bm)+3*pc(bk)); sbal=bal if stm==0 else -bal
    hit=False
    if abs(sbal)>=2 and wdl==0: ex_draw+=1; hit=True
    elif sbal>=2 and wdl<0:     ex_loss+=1; hit=True
    elif sbal<=-2 and wdl>0:    ex_win+=1; hit=True
    if hit: keep+=chunk
kept=len(keep)//REC
if os.path.exists(acc) and os.path.getsize(acc)>=8:
    old=struct.unpack('<I',open(acc,'rb').read(8)[4:8])[0]
    o=open(acc,'r+b'); o.seek(0,2); o.write(keep); o.seek(4); o.write(struct.pack('<I',old+kept)); o.close(); total=old+kept
else:
    open(acc,'wb').write(b'JNNW'+struct.pack('<I',kept)+keep); total=kept
td=tl=tw=tn=0
if os.path.exists(tally) and os.path.getsize(tally):
    td,tl,tw,tn=[int(x) for x in open(tally).read().split()]
td+=ex_draw; tl+=ex_loss; tw+=ex_win; tn+=n
open(tally,'w').write(f"{td} {tl} {tw} {tn}")
print(f"shard n={n} kept={kept} (draw={ex_draw} loss={ex_loss} win={ex_win}) | ACC_total={total} | seen={tn} density={ (td+tl+tw)/tn if tn else 0:.4f}")
PY
}

done=0; s=0; T0=$(date +%s)
while [ "$done" -lt "$MINE_N" ]; do
  this=$SHARD; [ $((done+this)) -gt "$MINE_N" ] && this=$((MINE_N-done))
  "$J" --gen-egdb-wld "$this" "$W/shard.jnnw" "$EGDIR" "$MAXP" "$CACHE" $((SEED0+s)) >"$W/ge.$s.log" 2>&1 \
    || { say "ABORT gen shard $s"; tail -6 "$W/ge.$s.log"|sed 's/^/  /'; break; }
  line=$(filter_shard "$W/shard.jnnw")
  now=$(date +%s); el=$((now-T0)); [ "$el" -lt 1 ] && el=1
  done=$((done+this)); s=$((s+1))
  rate=$(python3 -c "print(f'{$done/$el:.0f}')")
  eta=$(python3 -c "r=$done/$el; rem=($MINE_N-$done)/r if r else 0; print(f'{rem/60:.1f}min')")
  say "  [$s/$(( (MINE_N+SHARD-1)/SHARD ))] $line | rate=${rate}pos/s ETA_rest=${eta}"
  commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0693 minage shard $s : tally(draw loss win seen)=$(cat "$W/tally")" >/dev/null || true
  commit_to_main "$ACC" "$ARTREL/exceptions.jnnw" "0693 minage shard $s : corpus exceptions ACC" >/dev/null || true
done
NEX=$(python3 -c "import struct;print(struct.unpack('<I',open('$ACC','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
commit_to_main "$ACC" "$ARTREL/exceptions.jnnw" "0693 minage FINI : corpus exceptions TB ($NEX positions)" \
  && say "  ✓ corpus exceptions.jnnw committe ($NEX positions)" || say "  ⚠ commit corpus echoue"
say "=== 0693 minage FINI : $NEX exceptions / tally(draw loss win seen)=$(cat "$W/tally") ==="
