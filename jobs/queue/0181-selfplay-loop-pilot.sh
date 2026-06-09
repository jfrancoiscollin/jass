#!/usr/bin/env bash
# id: 0181-selfplay-loop-pilot
# description: PILOTE SELF-PLAY (dé-risquer l'INFRA, pas gagner). On a toujours
# distillé Scan (plafond = Scan). Le self-play casse ce plafond : le moteur joue
# contre lui-même, on étiquette par le RÉSULTAT (WDL), on réentraîne. Mais on
# s'est brûlés (effondrement 0149). Ce pilote valide UNE itération de la boucle :
#
#   champion (distillé) → self-play WDL → réentraîne ANCRÉ → champion_v1
#
# Question : la boucle TIENT-elle (pas d'effondrement vs v15) et BOUGE-t-elle ?
# 3 variantes pour trouver le régime stable :
#   SD   : self-distillation (target=score d12, ancré) — expert-iteration douce.
#   WDL-a1.0 : WDL×5 (piece-units) + ancre forte (anti-oubli).
#   WDL-a0.3 : WDL×5 + ancre faible (plus de mouvement, sonde l'effondrement).
# Réf champion_v0 : vs v15≈0.38, vs hc≈1.0.
#
# expected_duration: ~2-3 h.
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0181-selfplay-loop-pilot/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo ABORT; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
./build-prod/jass_tests >"$ART/tests.log" 2>&1 && echo "tests OK" || { echo TESTS FAIL; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }

echo; echo "=== iter0 : (re)train champion ==="
./build-prod/jass --dump-eval-features "$CLEAN" "$ART/champ.feat" 2>&1 | tail -1
python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$ART/champ.feat" \
  --target score --score-clip 5000 --score-drop 4900 --l2 1e-4 --max-iter 200 --scale 1000 \
  --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/champ.pjtw" 2>&1 | grep -E "val   :"
[ -f "$ART/champ.pjtw" ] || { echo "ABORT champ train"; exit 7; }
echo "  champion_v0 : vs v15 + vs hc (référence)"
./build-prod/jass --benchmark-scan-eval "$ART/champ.pjtw" "$V15" 9 6 1 0 "" 64 >"$ART/champ-v15.log" 2>&1
./build-prod/jass --benchmark-scan-eval "$ART/champ.pjtw" hc    8 6 1 0 "" 64 >"$ART/champ-hc.log"  2>&1
echo "    champ_v0 : v15=$(rate "$ART/champ-v15.log")  hc=$(rate "$ART/champ-hc.log")"

echo; echo "=== self-play WDL avec le champion (~200K, eval_depth 12, sharded) ==="
PER=$(( (200000 + NCPU - 1) / NCPU )); pids=(); files=(); t0=$(date +%s)
for sh in $(seq 0 $((NCPU-1))); do
  f="$ART/sp-shard-$sh.jnnw"; files+=("$f")
  ( ./build-prod/jass --gen-data-wdl --nnue "$ART/champ.pjtw" "$PER" "$f" 12 4 200 $((sh+1)) \
      > "$ART/gen-$sh.log" 2>&1 ) & pids+=($!)
done
for p in "${pids[@]}"; do wait "$p" || echo "  (gen shard rc!=0)"; done
SP="$ART/selfplay.jnnw"
python3 - "$SP" "${files[@]}" <<'PYEOF'
import struct,sys
from pathlib import Path
out=sys.argv[1]; shards=sys.argv[2:]; total=0
with open(out,'wb') as o:
    o.write(b"JNNW"); o.write(struct.pack("<I",0))
    for s in shards:
        r=Path(s).read_bytes(); n=struct.unpack_from('<I',r,4)[0]; o.write(r[8:8+n*38]); total+=n
    o.seek(4); o.write(struct.pack("<I",total))
print(f"  merged {total} self-play WDL records  (gen wall {0}s placeholder)")
PYEOF
echo "  gen wall : $(( $(date +%s) - t0 ))s"
NSP=$(python3 -c "import struct;print(struct.unpack_from('<I',open('$SP','rb').read(8),4)[0])")
python3 - "$SP" <<'PYEOF'
import struct,numpy as np,sys
raw=open(sys.argv[1],'rb').read(); n=struct.unpack_from('<I',raw,4)[0]
a=np.frombuffer(raw,np.uint8,count=8+n*38)[8:].reshape(n,38); w=a[:,37].astype(np.int8)
print(f"  WDL : +1={int((w>0).sum())} 0={int((w==0).sum())} -1={int((w<0).sum())} (n={n})")
PYEOF
./build-prod/jass --dump-eval-features "$SP" "$ART/sp.feat" 2>&1 | tail -1

retr(){ # $1=tag  $2..=train args ; bench vs v15(d9) + hc(d8)
  local tag="$1"; shift
  python3 pattern_jass/tools/train.py --data "$SP" --scan-eval --eval-features-file "$ART/sp.feat" \
    --l2 1e-4 --max-iter 200 --scale 1000 --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 \
    --anchor-weights "$ART/champ.pjtw" "$@" --out "$ART/$tag.pjtw" >"$ART/$tag-train.log" 2>&1
  [ -f "$ART/$tag.pjtw" ] || { echo "  ABORT $tag"; return; }
  ./build-prod/jass --benchmark-scan-eval "$ART/$tag.pjtw" "$V15" 9 6 1 0 "" 64 >"$ART/$tag-v15.log" 2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/$tag.pjtw" hc    8 6 1 0 "" 64 >"$ART/$tag-hc.log"  2>&1
  echo "  $tag : vs v15=$(rate "$ART/$tag-v15.log")  vs hc=$(rate "$ART/$tag-hc.log")"
}

echo; echo "=== iter1 : réentraîne sur le self-play (ancré) ==="
retr sd        --target score --score-clip 5000 --score-drop 4900 --anchor-l2 1.0
retr wdl-a1.0  --target wdl --wdl-scale 5.0 --anchor-l2 1.0
retr wdl-a0.3  --target wdl --wdl-scale 5.0 --anchor-l2 0.3

echo; echo "=========================================================="
echo "        0181 PILOTE SELF-PLAY — VERDICT (la boucle TIENT-elle ?)"
echo "  champion_v0 (réf)  : vs v15=$(rate "$ART/champ-v15.log")  vs hc=$(rate "$ART/champ-hc.log")   [$NSP positions self-play]"
echo "  SD (score+ancre)   : vs v15=$(rate "$ART/sd-v15.log")  vs hc=$(rate "$ART/sd-hc.log")"
echo "  WDL ancre 1.0      : vs v15=$(rate "$ART/wdl-a1.0-v15.log")  vs hc=$(rate "$ART/wdl-a1.0-hc.log")"
echo "  WDL ancre 0.3      : vs v15=$(rate "$ART/wdl-a0.3-v15.log")  vs hc=$(rate "$ART/wdl-a0.3-hc.log")"
echo "  → ≈ champ_v0 = la boucle TIENT (anti-oubli OK, infra validée)."
echo "  → << champ_v0 = effondrement (ancre trop faible / signal toxique)."
echo "  → > champ_v0 = auto-amélioration (bonus : le self-play paie déjà)."
echo "=========================================================="
