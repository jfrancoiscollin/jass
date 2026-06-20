#!/usr/bin/env bash
# id: cpx62-0398-corpus-d10
# description: CORPUS continu cpx62 (volume d10, vers les 30M du gros fit train_stream). Génère 2800000 pos
# piloté champion (0378), committe UN shard gzippé à la finalisation. Maillon de chaîne. Hors-tree, gzip. Aucun Scan.
# expected_duration: ~150 min
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-110}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0398-corpus-d10/artefacts"; mkdir -p "$ART"
W=/root/cw-cpx62-0398-corpus-d10; rm -rf "$W"; mkdir -p "$W"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
PLAY_DEPTH=10; EVAL_DEPTH=4; TARGET=2800000
SEED_CH=jobs/results/cpx62-0378-champion-geometry/artefacts/champion.pjtw.gz
preflight_build 1; preflight_note "corpus d10 2800000" 90; preflight_check
ok=0; for i in $(seq 1 120); do git fetch origin main >/dev/null 2>&1 || true
  git cat-file -e "origin/main:$SEED_CH" 2>/dev/null && { ok=1; break; }; sleep 30; done
[ "$ok" = 1 ] || { echo "ABORT: champion absent"; exit 4; }
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
app(){ python3 - "$1" "$2" <<'PY'
import struct,sys,os; REC=38
b=open(sys.argv[1],'rb').read(); n=(len(b)-8)//REC; body=b[8:8+n*REC]; acc=sys.argv[2]
if os.path.exists(acc) and os.path.getsize(acc)>=8:
    raw=open(acc,'rb').read(); old=struct.unpack('<I',raw[4:8])[0]
    o=open(acc,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+n)); o.close(); print(old+n)
else: open(acc,'wb').write(b'JNNW'+struct.pack('<I',n)+body); print(n)
PY
}
ACC="$W/corpus.jnnw"; N=0
while [ "$N" -lt "$TARGET" ]; do gen 350000 "$W/b" >/dev/null 2>&1; N=$(app "$W/b" "$ACC"); echo "  accumulé $N"; done
gzip -c "$ACC" > "$ART/corpus-d10.jnnw.gz"
SZ=$(stat -c%s "$ART/corpus-d10.jnnw.gz")
echo "=== shard d10 : $N pos, $((SZ/1000000)) Mo gz → committé ==="
