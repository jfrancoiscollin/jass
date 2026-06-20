#!/usr/bin/env bash
# id: ccx33-0384-corpus-d10
# description: GÉNÉRATEUR DE CORPUS d10 (volume) (parallèle à la boucle cpx62-0381). ccx33 génère un GROS lot de self-play
# d12 (issues + véridiques, profond) piloté par le champion (0378), et committe un shard GZIPPÉ que la PROCHAINE
# itération de boucle piochera pour injecter de la diversité (d12 ∪ d10). Additif/non-bloquant : la boucle cpx62 ne
# DÉPEND pas de ça. Tout hors-tree, transport gzip. Aucun Scan.
# expected_duration: ~3 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-220}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0384-corpus-d10/artefacts"; mkdir -p "$ART"
W=/root/cw-d12; rm -rf "$W"; mkdir -p "$W"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
PLAY_DEPTH=10; EVAL_DEPTH=4; TARGET_TOTAL=3000000; BATCH_MIN=25
SEED_CH=jobs/results/cpx62-0378-champion-geometry/artefacts/champion.pjtw.gz
preflight_build 1; preflight_note "génération d12 diversité (~${TARGET_TOTAL})" 180; preflight_check

echo "=== champion (0378) comme pilote ==="
ok=0; for i in $(seq 1 120); do git fetch origin main >/dev/null 2>&1 || true
  git cat-file -e "origin/main:$SEED_CH" 2>/dev/null && { ok=1; break; }; echo "  attente 0378 ($i)"; sleep 30; done
[ "$ok" = 1 ] || { echo "ABORT: champion 0378 absent"; exit 4; }
git show "origin/main:$SEED_CH" | gunzip > "$W/champion.pjtw"

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
B="$W/build"; cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$W/build.log" 2>&1 || { echo "BUILD FAIL"; tail -8 "$W/build.log"; exit 6; }
JASS="$B/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted

gen(){ local nn="$1" out="$2"; local per=$(( (nn+NCPU-1)/NCPU ))
  for s in $(seq 1 "$NCPU"); do "$JASS" --gen-data-wdl "$per" "$out.$s" "$EVAL_DEPTH" "$PLAY_DEPTH" 200 "$((RANDOM*RANDOM+s))" --nnue "$W/champion.pjtw" >/dev/null 2>&1 & done; wait
  python3 - "$out" <<'PY'
import struct,glob,sys,re
out=sys.argv[1]; REC=38; body=b""; tot=0
for f in sorted(glob.glob(out+".*"),key=lambda p:int(re.search(r"\.(\d+)$",p).group(1))):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; tot+=n; body+=b[8:8+n*REC]
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body); print(tot)
PY
  rm -f "$out".[0-9]* ; }
append(){ python3 - "$1" "$2" <<'PY'
import struct,sys,os; REC=38
src,acc=sys.argv[1],sys.argv[2]
b=open(src,'rb').read(); n=(len(b)-8)//REC; body=b[8:8+n*REC]
if os.path.exists(acc) and os.path.getsize(acc)>=8:
    raw=open(acc,'rb').read(); old=struct.unpack('<I',raw[4:8])[0]
    o=open(acc,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+n)); o.close(); print(old+n)
else:
    open(acc,'wb').write(b'JNNW'+struct.pack('<I',n)+body); print(n)
PY
}
ACC="$W/d10-corpus.jnnw"
echo "=== sonde débit d12 ==="
t0=$(date +%s); gen $((NCPU*120)) "$W/probe" >/dev/null 2>&1; dt=$(( $(date +%s)-t0 )); [ "$dt" -lt 1 ] && dt=1
RATE=$(( NCPU*120*60/dt )); BATCH=$(( RATE*BATCH_MIN )); [ "$BATCH" -lt 30000 ] && BATCH=30000
echo "  débit ≈ ${RATE} pos/min @ d12 → batch=${BATCH}, cible ${TARGET_TOTAL}"; rm -f "$W/probe"
N=0
while [ "$N" -lt "$TARGET_TOTAL" ]; do
  gen "$BATCH" "$W/b.jnnw" >/dev/null 2>&1
  N=$(append "$W/b.jnnw" "$ACC")
  echo "  accumulé : ${N}"
done
SZ=$(gzip -c "$ACC" | wc -c)
gzip -c "$ACC" > "$ART/d10-corpus.jnnw.gz"
echo; echo "=========================================================="
echo "   ccx33-0382 — DIVERSITÉ d12 : ${N} positions, $((SZ/1000000)) Mo gzippé → committé"
echo "   La prochaine itération de boucle (cpx62) piochera ce shard pour mixer d12 ∪ d10."
echo "=========================================================="