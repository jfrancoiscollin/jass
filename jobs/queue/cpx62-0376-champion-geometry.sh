#!/usr/bin/env bash
# id: cpx62-0376-champion-geometry
# description: RECOVERY étage 2 (remplace 0369+0372). Lit la data d10 de 0373 (LOCALE cpx62) + tire la data d12 de
# 0375 (git), POOLE (volume d10 + qualité d12), fit le CHAMPION (full-fold), le committe GZIPPÉ (fix du cap 95Mo).
# Juge départage d10/d12 + champion vs chaque box. PUIS le TEST GÉOMÉTRIE propre : 32+color-fold (8,5M) vs 8+color-fold
# (2,1M) sur le MÊME pool, match cross-arch. Aucun Scan (pivot self). ABORT clair si data d10 locale recyclée.
# expected_duration: ~1.5 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-180}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0376-champion-geometry/artefacts"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"; SCALE=1000; GEOM=/root/jass-geom-lean8
SRC10=/root/jass/jobs/results/cpx62-0373-virtuous-loop-deep/artefacts.src
H0375=jobs/results/ccx33-0375-salvage-d12/artefacts
preflight_build 2; preflight_train 3000000 3; preflight_note "champion poolé + test géométrie 32 vs 8" 110; preflight_check

# --- data d10 LOCALE (0373) ---
[ -d "$SRC10" ] && [ -f "$SRC10/cumulative.jnnw" ] || { echo "ABORT-SALVAGE: data d10 (0373 local) recyclée → RÉGÉNÉRER"; exit 4; }
GEN10=$(ls "$SRC10"/gen*.pjtw 2>/dev/null | sort -V | tail -1); [ -n "$GEN10" ] || { echo "ABORT: pas d'éval d10"; exit 4; }
N10=$(python3 -c "import struct;print(struct.unpack('<I',open('$SRC10/cumulative.jnnw','rb').read(8)[4:8])[0])")
echo "  d10 (local) : ${N10} positions, éval=$(basename "$GEN10")"

# --- data d12 via git (0375) ---
echo "=== attente data d12 (0375) ==="
ok=0; for i in $(seq 1 120); do git fetch origin main >/dev/null 2>&1 || true
  git cat-file -e "origin/main:$H0375/d12-data.jnnw" 2>/dev/null && { ok=1; break; }; echo "  attente 0375 ($i)"; sleep 30; done
[ "$ok" = 1 ] || { echo "ABORT: data d12 (0375) absente"; exit 4; }
git show "origin/main:$H0375/d12-data.jnnw" > "$ART/d12-data.jnnw"
git show "origin/main:$H0375/d12-eval.pjtw.gz" > "$ART/d12-eval.pjtw.gz" 2>/dev/null && gunzip -f "$ART/d12-eval.pjtw.gz"
GEN12="$ART/d12-eval.pjtw"; [ -f "$GEN12" ] || { echo "ABORT: éval d12 non récupérée"; exit 4; }
N12=$(python3 -c "import struct;print(struct.unpack('<I',open('$ART/d12-data.jnnw','rb').read(8)[4:8])[0])")
echo "  d12 (git) : ${N12} positions"

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
cmake_jass(){ local B="$1"; cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$ART/cmake-$B.log" 2>&1
  grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake-$B.log" || { echo "ABORT: egdb off ($B)"; exit 6; }
  cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build-$B.log" 2>&1 || { echo "BUILD FAIL $B"; tail -8 "$ART/build-$B.log"; exit 6; }; }
echo "=== build 32-pat ==="; cmake_jass build-32; J="$PWD/build-32/jass"
direct(){ "$J" --benchmark-nnue-vs-nnue "$1" "$2" 9 6 1 0 >"$3" 2>&1 || true; grep -E 'score rate' "$3" | grep -oE '[0-9.]+' | head -1; }

echo "=== départage d10 vs d12 ==="; D=$(direct "$GEN10" "$GEN12" "$ART/d10_vs_d12.log"); echo "  d10 vs d12 = ${D}"

echo "=== POOL d10 ∪ d12 ==="
cp "$SRC10/cumulative.jnnw" "$ART/pooled.jnnw"
python3 - "$ART/d12-data.jnnw" "$ART/pooled.jnnw" <<'PY'
import struct,sys; REC=38
b=open(sys.argv[1],'rb').read(); n=(len(b)-8)//REC
raw=open(sys.argv[2],'rb').read(); old=struct.unpack('<I',raw[4:8])[0]
o=open(sys.argv[2],'r+b'); o.seek(0,2); o.write(b[8:8+n*REC]); o.seek(4); o.write(struct.pack('<I',old+n)); o.close()
print(f"  pool = {old} (d10) + {n} (d12) = {old+n}")
PY
"$J" --dump-eval-features "$ART/pooled.jnnw" "$ART/feat" >/dev/null 2>&1

fit(){ local extra="$1" out="$2" pdir="$3"
  ${pdir:+env JASS_PATTERNS_DIR=$pdir} python3 pattern_jass/tools/train.py --data "$ART/pooled.jnnw" --scan-eval \
    --eval-features-file "$ART/feat" --loss logistic --l2 1e-4 --max-iter 250 --scale "$SCALE" --prune --lowmem $extra \
    --out "$out" >"${out%.pjtw}-train.log" 2>&1; [ -f "$out" ] || { echo "TRAIN FAIL $out"; tail -8 "${out%.pjtw}-train.log"; exit 9; }; }

echo "=== CHAMPION (full-fold) sur le pool combiné ==="
fit "--full-fold" "$ART/champion.pjtw" ""
gzip -c "$ART/champion.pjtw" > "$ART/champion.pjtw.gz"; echo "  champion gzippé : $(( $(stat -c%s "$ART/champion.pjtw.gz")/1000000 )) Mo"
CD10=$(direct "$ART/champion.pjtw" "$GEN10" "$ART/champ_vs_d10.log"); CD12=$(direct "$ART/champion.pjtw" "$GEN12" "$ART/champ_vs_d12.log")
# pool durable gzippé (checkpoint) si sous le cap
gzip -c "$ART/pooled.jnnw" > "$ART/pooled.jnnw.gz"; PSZ=$(stat -c%s "$ART/pooled.jnnw.gz")
[ "$PSZ" -lt 94000000 ] && echo "  pool gzippé committé ($((PSZ/1000000)) Mo)" || { rm -f "$ART/pooled.jnnw.gz"; echo "  pool gzippé >94Mo → non committé (reste local)"; }

echo "=== TEST GÉOMÉTRIE : 32+color-fold vs 8+color-fold (MÊME pool) ==="
fit "--color-fold" "$ART/eval32cf.pjtw" ""
python3 pattern_jass/tools/gen_patterns.py --emit --drop diag_0,diag_1,diag_2,diag_3,diag_4,diag_5,diag_6,anti_0,anti_1,anti_2,anti_3,anti_4,anti_5,anti_6,anti_7,horiz_0,horiz_1,horiz_2,horiz_3,horiz_4,sq_0,sq_1,sq_2,sq_3 >"$ART/gen8.log" 2>&1
[ "$(grep -oE 'NUM_PATTERNS *= *[0-9]+' pattern_jass/src/pattern.hpp | grep -oE '[0-9]+' | head -1)" = "8" ] || { echo "ABORT drop8"; exit 7; }
cmake_jass build-8; J8="$PWD/build-8/jass"
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
fit "--color-fold" "$ART/eval8cf.pjtw" "$GEOM"
grep -qE "17M -> *8,503,072" "$ART/eval8cf-train.log" && { echo "ABORT: arm-8 flippé 32"; exit 8; }
python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$ART/eval32cf.pjtw" --jass-b "$J8" --pattern-b "$ART/eval8cf.pjtw" \
  --depth 9 --pairs 8 --max-plies 160 >"$ART/geo.log" 2>&1 || true
G=$(grep -E 'A score rate' "$ART/geo.log" | grep -oE '[0-9.]+' | head -1)

echo; echo "=========================================================="
echo "   cpx62-0376 — CHAMPION poolé + TEST GÉOMÉTRIE (pool=$((N10+N12)))"
echo "   départage d10 vs d12 = ${D}"
echo "   champion vs d10 = ${CD10}  |  champion vs d12 = ${CD12}   (>0.5 vs LES DEUX → pooler gagne)"
echo "   GÉOMÉTRIE  32+color-fold vs 8+color-fold = ${G}   (>0.55 → 32 enrichi gagne ; ~0.5 → 8 Scan-fidèle suffit)"
echo "=========================================================="