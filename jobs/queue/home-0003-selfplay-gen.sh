#!/usr/bin/env bash
# id: home-0003-selfplay-gen
# description: 1er vrai job du runner maison — génération SELF-PLAY WDL (sans egdb : le PC n'a pas la
# bitbase, seulement les box). Produit de la diversité midgame/ouverture pour compléter les datasets
# finale-enrichis des box. Shardé ×threads, build RAM-aware (-j via mem_safe_jobs). Sortie dimensionnée
# pour être COMMITTABLE (~30 MB < 50 MB) → une box pourra la récupérer (git) et la fusionner au training.
# expected_duration: ~45-90 min (CPU portable)
set -uo pipefail
cd /root/jass
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/home-0003-selfplay-gen/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

EVAL_DEPTH=8; PLAY_DEPTH=6; TOTAL=500000; MAXPLIES=200
preflight_build 1
preflight_note "self-play ${TOTAL} WDL (depth ${EVAL_DEPTH}/${PLAY_DEPTH}, ×$NCPU, CPU portable)" 55
preflight_check

echo "=== build jass (Release, RAM-aware) ==="
cmake -S . -B build-home -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-home -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-home/jass

echo "=== self-play WDL (${TOTAL}, depth ${EVAL_DEPTH}/${PLAY_DEPTH}, ×$NCPU shards) ==="
PER=$(( (TOTAL + NCPU - 1) / NCPU ))
for s in $(seq 1 "$NCPU"); do
  "$JASS" --gen-data-wdl "$PER" "$ART/sp-$s.jnnw" "$EVAL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" $((4242 + RANDOM*s + s)) >"$ART/sp-$s.log" 2>&1 &
done
wait
echo "shards: $(ls "$ART"/sp-*.jnnw 2>/dev/null | wc -l)/$NCPU"

# --- fusion shards → home-selfplay.jnnw + rapport ---
python3 - "$ART" <<'PY'
import sys,glob,struct,collections
art=sys.argv[1]; REC=38
files=sorted(glob.glob(art+'/sp-*.jnnw'))
out=open(art+'/home-selfplay.jnnw','wb'); total=0
out.write(b'JNNW'+struct.pack('<I',0))
def pieces(rec):
    wm,wk,bm,bk=struct.unpack('<4Q',rec[0:32]); return bin(wm|wk|bm|bk).count('1')
phase=collections.Counter()
for f in files:
    b=open(f,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]
    for i in range(n):
        rec=body[i*REC:(i+1)*REC]
        if len(rec)<REC: break
        out.write(rec); phase[pieces(rec)]+=1; total+=1
out.seek(4); out.write(struct.pack('<I',total)); out.close()
import os
mb=os.path.getsize(art+'/home-selfplay.jnnw')/1e6
le12=sum(v for k,v in phase.items() if k<=12)
print(f"FUSION  total={total}  taille={mb:.1f} MB  (<50 MB → committable)")
print(f"PHASE   ≤12p={le12} ({le12/total*100:.1f}%)  >12p={total-le12}")
# clean shards to keep the committed artefacts small
for f in files: os.remove(f)
PY

echo; echo "=========================================================="
echo "   home-0003 — self-play WDL généré sur le PC ($NCPU threads)"
echo "   home-selfplay.jnnw committé → une box le fusionnera au training."
echo "=========================================================="
