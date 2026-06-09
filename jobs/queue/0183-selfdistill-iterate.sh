#!/usr/bin/env bash
# id: 0183-selfdistill-iterate
# description: SELF-DISTILLATION itérée (expert-iteration). 0181 : SD (réentraîner
# sur les propres scores d12 du champion sur ses parties self-play, ancré) a fait
# 0.472→0.556 vs v15 à d9 — auto-amélioration GRATUITE (le WDL brut, lui, s'est
# effondré). Ici on (a) CONFIRME à movetime (le d9 doit se vérifier au temps réel)
# et (b) ITÈRE v0→v1→v2 : ça grimpe, plafonne ou s'effondre ?
#   Chaque tour : self-play(eval courant) → distill score d12 ANCRÉ au précédent.
# expected_duration: ~2.5-3.5 h.
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0183-selfdistill-iterate/artefacts.src"; mkdir -p "$ART"
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

echo; echo "=== v0 : champion distillé ==="
./build-prod/jass --dump-eval-features "$CLEAN" "$ART/champ.feat" 2>&1 | tail -1
python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$ART/champ.feat" \
  --target score --score-clip 5000 --score-drop 4900 --l2 1e-4 --max-iter 200 --scale 1000 \
  --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/v0.pjtw" 2>&1 | grep -E "val   :"
[ -f "$ART/v0.pjtw" ] || { echo "ABORT v0"; exit 7; }
bench(){ # $1=tag pjtw
  ./build-prod/jass --benchmark-scan-eval "$ART/$1.pjtw" "$V15" 9  6 1 0   "" 64 >"$ART/$1-v15d9.log" 2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/$1.pjtw" "$V15" 64 4 1 300 "" 64 >"$ART/$1-v15mt.log" 2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/$1.pjtw" hc    8  6 1 0   "" 64 >"$ART/$1-hc.log"   2>&1
  echo "  $1 : v15 d9=$(rate "$ART/$1-v15d9.log")  movetime=$(rate "$ART/$1-v15mt.log")  hc=$(rate "$ART/$1-hc.log")"
}
bench v0

PREV=v0
for IT in 1 2; do
  echo; echo "=== iter $IT : self-play($PREV) → distill score d12 ancré à $PREV ==="
  PER=$(( (200000 + NCPU - 1) / NCPU )); pids=(); files=(); t0=$(date +%s)
  for sh in $(seq 0 $((NCPU-1))); do
    f="$ART/sp$IT-$sh.jnnw"; files+=("$f")
    ( ./build-prod/jass --gen-data-wdl --nnue "$ART/$PREV.pjtw" "$PER" "$f" 12 4 200 $((IT*100+sh+1)) \
        > "$ART/gen$IT-$sh.log" 2>&1 ) & pids+=($!)
  done
  for p in "${pids[@]}"; do wait "$p" || echo "  (gen rc!=0)"; done
  SP="$ART/sp$IT.jnnw"
  python3 - "$SP" "${files[@]}" <<'PYEOF'
import struct,sys
from pathlib import Path
out=sys.argv[1]; shards=sys.argv[2:]; total=0
with open(out,'wb') as o:
    o.write(b"JNNW"); o.write(struct.pack("<I",0))
    for s in shards:
        r=Path(s).read_bytes(); n=struct.unpack_from('<I',r,4)[0]; o.write(r[8:8+n*38]); total+=n
    o.seek(4); o.write(struct.pack("<I",total))
print(f"  merged {total} self-play records")
PYEOF
  echo "  gen wall : $(( $(date +%s) - t0 ))s"
  ./build-prod/jass --dump-eval-features "$SP" "$ART/sp$IT.feat" 2>&1 | tail -1
  python3 pattern_jass/tools/train.py --data "$SP" --scan-eval --eval-features-file "$ART/sp$IT.feat" \
    --target score --score-clip 5000 --score-drop 4900 --l2 1e-4 --max-iter 200 --scale 1000 \
    --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 \
    --anchor-weights "$ART/$PREV.pjtw" --anchor-l2 1.0 --out "$ART/v$IT.pjtw" >"$ART/v$IT-train.log" 2>&1
  [ -f "$ART/v$IT.pjtw" ] || { echo "  ABORT v$IT"; break; }
  bench v$IT
  PREV=v$IT
done

echo; echo "=========================================================="
echo "        0183 SELF-DISTILLATION ITÉRÉE — VERDICT"
echo "  v0 (champion) : v15 d9=$(rate "$ART/v0-v15d9.log")  mt=$(rate "$ART/v0-v15mt.log")  hc=$(rate "$ART/v0-hc.log")"
for IT in 1 2; do
  [ -f "$ART/v$IT.pjtw" ] && echo "  v$IT (SD x$IT)   : v15 d9=$(rate "$ART/v$IT-v15d9.log")  mt=$(rate "$ART/v$IT-v15mt.log")  hc=$(rate "$ART/v$IT-hc.log")"
done
echo "  → mt monte across v0→v1→v2 = la self-distillation paie au temps réel (itérer)."
echo "  → mt plat/baisse = le gain d9 ne se convertit pas / plateau ; on s'arrête."
echo "=========================================================="
