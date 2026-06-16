#!/usr/bin/env bash
# id: ccx33-0295-tb-conversion-ab
# description: QUANTIFIE le gain du fix TB distance-aware (search.cpp). 2 binaires identiques SAUF le
# score TB : bras FLAT (ancien : score gagnant constant) vs bras DIST (nouveau : -ply → préfère gain
# court / défaite longue). Chacun génère du self-play AVEC egdb (champion 0266, depth-8), puis on
# RELABEL → métrique **stalls** (positions egdb-gagnées/perdues enregistrées NULLES = conversions
# ratées). Attendu : DIST a MOINS de stalls que FLAT (+ moins de nuls globaux) = le fix convertit mieux.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0295-tb-conversion-ab/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
APP=/root/egdb_extracted/app
SRC=/root/jass/jobs/results/cpx62-0266-kingloop-deepplay/artefacts.src
CHAMP="$SRC/gen8.pjtw"
ls "$APP"/db2.idx1 >/dev/null 2>&1 || { echo "ABORT: base egdb absente"; exit 4; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1

build(){ # $1 = build dir
  cmake -S . -B "$1" -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake-$1.log" 2>&1
  cmake --build "$1" -j"$NCPU" --target jass >"$ART/build-$1.log" 2>&1 || { echo "BUILD FAIL $1"; tail -15 "$ART/build-$1.log"; exit 5; }
}
echo "=== build DIST (main, score TB distance-aware) ==="; build build-dist
echo "=== build FLAT (patch -ply → constante) ==="
sed -i 's/(MATE_SCORE - MAX_PLY - 1) - ply;/(MATE_SCORE - MAX_PLY - 1);/' src/search.cpp
grep -q '(MATE_SCORE - MAX_PLY - 1) - ply;' src/search.cpp && { echo "ABORT: patch flat n'a pas pris"; exit 6; }
build build-flat
git checkout -- src/search.cpp   # restaure la version distance-aware
echo "patch flat appliqué+build, source restauré"

JASS_REL=./build-dist/jass        # binaire de mesure (relabel = juste des probes egdb)
EVAL_DEPTH=6; PLAY_DEPTH=8; NPER=500000

gen_arm(){ # $1=tag $2=binaire
  local PER=$(( (NPER + NCPU - 1) / NCPU )); local CUM="$ART/$1.jnnw"
  for s in $(seq 1 "$NCPU"); do
    JASS_EGDB_PATH="$APP" JASS_EGDB_CACHE_MB=256 \
      "$2" --gen-data-wdl "$PER" "$ART/$1-$s.jnnw" "$EVAL_DEPTH" "$PLAY_DEPTH" 200 $((RANDOM)) >"$ART/$1-$s.log" 2>&1 &
  done; wait
  python3 - "$ART/$1" "$CUM" <<'PY'
import struct,glob,sys,re
outp,dst=sys.argv[1],sys.argv[2]; REC=38; body=b""; add=0
for s in sorted(glob.glob(outp+"-*.jnnw"),key=lambda p:int(re.search(r"-(\d+)\.jnnw$",p).group(1))):
    b=open(s,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; add+=n; body+=b[8:8+n*REC]
open(dst,'wb').write(b'JNNW'+struct.pack('<I',add)+body); print(f"{dst}: {add}")
PY
  rm -f "$ART/$1-"*.jnnw
}
drawrate(){ python3 - "$1" <<'PY'
import sys,struct
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]; REC=38
d=sum(1 for i in range(n) if struct.unpack('<b',body[i*REC+37:i*REC+38])[0]==0)
print(f"draw_rate={d/n*100:.2f}% ({d}/{n})")
PY
}

echo "=== génération + relabel : bras FLAT ==="; gen_arm flat ./build-flat/jass
RL_FLAT=$($JASS_REL --egdb-relabel "$ART/flat.jnnw" "$APP" "$ART/flat-rl.jnnw" 2>&1 | tail -1)
DR_FLAT=$(drawrate "$ART/flat.jnnw")
echo "=== génération + relabel : bras DIST ==="; gen_arm dist ./build-dist/jass
RL_DIST=$($JASS_REL --egdb-relabel "$ART/dist.jnnw" "$APP" "$ART/dist-rl.jnnw" 2>&1 | tail -1)
DR_DIST=$(drawrate "$ART/dist.jnnw")

echo; echo "=========================================================="
echo "   cpx62-0295 — A/B fix TB distance-aware (conversion)"
echo "----------------------------------------------------------"
echo "  FLAT : $RL_FLAT"
echo "         $DR_FLAT"
echo "  DIST : $RL_DIST"
echo "         $DR_DIST"
echo "----------------------------------------------------------"
echo "  stalls(DIST) < stalls(FLAT) → le fix CONVERTIT mieux (moins de finales gagnées nullifiées)."
echo "  + draw_rate(DIST) < draw_rate(FLAT) → confirme (moins de nuls globaux)."
echo "  écart ~0 → le fix mord peu à depth-8 (la navette intra-TB profonde attend MTC)."
echo "=========================================================="
