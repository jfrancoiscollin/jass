#!/usr/bin/env bash
# id: 0180-deeper-teacher
# description: LEVIER 3 — TEACHER PLUS PROFOND. On distille des scores Scan-d10
# (prof shallow). Scan joue bien plus profond en partie ; nos labels sont donc
# un prof faible. Test CONTRÔLÉ de l'effet de la profondeur du teacher, isolé du
# dataset : on relabellise le MÊME sous-ensemble (250K) du master à d10 (control)
# ET d16 (treatment) — mêmes positions, même drop → seule la profondeur change.
# Distill champion sur chaque, bench vs v15 (d9 + movetime).
#
#   d16 > d10 vs v15 = un prof plus profond élève le plafond → scaler la prof.
#   d16 ≈ d10        = la profondeur du teacher n'est pas le levier ici.
#
# expected_duration: ~2-3 h (relabel d16 = le gros).
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0180-deeper-teacher/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo ABORT; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
./build-prod/jass_tests >"$ART/tests.log" 2>&1 && echo "tests OK" || { echo TESTS FAIL; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- Scan (shipped pre-built dans rhalbersma/scan) -------------------------
SCAN_DIR=/root/jass-scan; SCAN_BIN="$SCAN_DIR/scan_linux"
if [ ! -x "$SCAN_BIN" ]; then
    SRC=/root/jass-scan-src
    [ -d "$SRC" ] || git clone --depth 1 https://github.com/rhalbersma/scan "$SRC" || { echo "ABORT clone"; exit 4; }
    mkdir -p "$SCAN_DIR"; cp "$SRC/scan_linux" "$SCAN_BIN"; chmod +x "$SCAN_BIN"
    cp "$SRC/scan.ini" "$SCAN_DIR/" 2>/dev/null || true; cp -r "$SRC/data" "$SCAN_DIR/data" 2>/dev/null || true
fi
[ -x "$SCAN_BIN" ] || { echo "ABORT: scan bin absent"; exit 4; }

SUBSET=250000
relabel_at(){ # $1=depth  $2=outfile  — relabellise le MÊME sous-ensemble du master
  local depth="$1" out="$2"; local SHARD=$(( (SUBSET + NCPU - 1) / NCPU )); local pids=() files=()
  local t0=$(date +%s)
  for sh in $(seq 0 $((NCPU-1))); do
    local f="$ART/d${depth}-shard-${sh}.jnnw"; files+=("$f")
    ( python3 tools/relabel_with_scan.py --in "$CLEAN" --out "$f" --scan "$SCAN_BIN" \
        --depth "$depth" --start $(( sh*SHARD )) --max-records "$SHARD" \
        --timeout 60 --newgame-every 50 --progress-every 20000 \
        > "$ART/relabel-d${depth}-${sh}.log" 2>&1 ) & pids+=($!)
  done
  for p in "${pids[@]}"; do wait "$p" || echo "  (d$depth shard rc!=0)"; done
  python3 - "$out" "${files[@]}" <<'PYEOF'
import struct,sys
from pathlib import Path
out=sys.argv[1]; shards=sys.argv[2:]; total=0
with open(out,'wb') as o:
    o.write(b"JNNW"); o.write(struct.pack("<I",0))
    for s in shards:
        r=Path(s).read_bytes(); n=struct.unpack_from('<I',r,4)[0]; o.write(r[8:8+n*38]); total+=n
    o.seek(4); o.write(struct.pack("<I",total))
print(f"  merged {total} → {out}")
PYEOF
  echo "  relabel d$depth wall : $(( $(date +%s) - t0 ))s"
}

echo; echo "=== relabel sous-ensemble $SUBSET @ d10 (control) ==="
relabel_at 10 "$ART/sub-d10.jnnw"
echo; echo "=== relabel MÊME sous-ensemble @ d16 (treatment) ==="
relabel_at 16 "$ART/sub-d16.jnnw"
N10=$(python3 -c "import struct;print(struct.unpack_from('<I',open('$ART/sub-d10.jnnw','rb').read(8),4)[0])")
N16=$(python3 -c "import struct;print(struct.unpack_from('<I',open('$ART/sub-d16.jnnw','rb').read(8),4)[0])")
echo "  control d10 : $N10 records   treatment d16 : $N16 records"

rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }
distill_bench(){ # $1=tag $2=data
  local tag="$1" data="$2"
  ./build-prod/jass --dump-eval-features "$data" "$ART/$tag.feat" 2>&1 | tail -1
  python3 pattern_jass/tools/train.py --data "$data" --scan-eval --eval-features-file "$ART/$tag.feat" \
    --target score --score-clip 5000 --score-drop 4900 --l2 1e-4 --max-iter 200 --scale 1000 \
    --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/$tag.pjtw" >"$ART/$tag-train.log" 2>&1
  [ -f "$ART/$tag.pjtw" ] || { echo "  ABORT train $tag"; return; }
  ./build-prod/jass --benchmark-scan-eval "$ART/$tag.pjtw" "$V15" 9  8 1 0   "" 64 >"$ART/$tag-v15-d9.log" 2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/$tag.pjtw" "$V15" 64 4 1 300 "" 64 >"$ART/$tag-v15-mt.log" 2>&1
  echo "  $tag : vs v15 d9=$(rate "$ART/$tag-v15-d9.log")  movetime=$(rate "$ART/$tag-v15-mt.log")"
}

echo; echo "=== distill + bench : d10 vs d16 (même positions) ==="
distill_bench teacher-d10 "$ART/sub-d10.jnnw"
distill_bench teacher-d16 "$ART/sub-d16.jnnw"

echo; echo "=========================================================="
echo "        0180 TEACHER PLUS PROFOND — VERDICT"
echo "  control  d10 ($N10) : v15 d9=$(rate "$ART/teacher-d10-v15-d9.log")  mt=$(rate "$ART/teacher-d10-v15-mt.log")"
echo "  treatment d16 ($N16): v15 d9=$(rate "$ART/teacher-d16-v15-d9.log")  mt=$(rate "$ART/teacher-d16-v15-mt.log")"
echo "  (sous-ensemble 250K : rates absolus < champion 1.4M ; c'est le DELTA d10→d16 qui compte)"
echo "  → d16 > d10 = prof du teacher = levier (scaler vers d20+ / full master)."
echo "  → d16 ≈ d10 = pas le levier ici."
echo "=========================================================="
