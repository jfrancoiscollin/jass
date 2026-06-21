#!/usr/bin/env bash
# id: cpx62-0409-gate2b-king
# description: GATE 2b — ROIS DANS LES PATTERNS a gros volume (BIAIS_FIT_VOLUME #6 : king-patterns CONDAMNES a ~2M,
# 0240/0360). Debloque par l'extension train_stream --king-patterns (occupancy men|kings, byte-compat C++ valide).
# 2 builds : men-only (defaut = BASELINE archi prod 32cf) et king-aware (-DJASS_KING_PATTERNS). 2 fits color-fold sur
# le corpus accumule (le fit king ajoute --king-patterns). 1 juge cross : king (king-build+king-pjtw) vs men. Chaque
# build joue SON pjtw (le marqueur king rejette un mauvais appariement). Hors-tree (/root/cw-gate2b), gzip. Aucun Scan.
# Meme fold (color) des 2 cotes => isole l'effet ROIS. S'enchaine apres 0408. expected_duration: ~5 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-420}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0409-gate2b-king/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"
W=/root/cw-gate2b; rm -rf "$W"; mkdir -p "$W"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
GEOM=/root/jass-geom32-2b; MAXIT=25; CHUNK=1000000
say(){ echo "$@" | tee -a "$RES"; }

preflight_build 2; preflight_train 31000000 1; preflight_note "2 builds + assemble + dump feat + 2 fits + 1 juge" 200; preflight_check

cmake_jass(){ # $1=builddir  $2=extra cmake flag (ex -DJASS_KING_PATTERNS=ON)
  cmake -S . -B "$1" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON $2 \
      >"$W/cmake-$(basename "$1").log" 2>&1
  grep -q "EXTERNAL EGDB ENABLED" "$W/cmake-$(basename "$1").log" || { echo "ABORT egdb $1"; exit 6; }
  cmake --build "$1" -j"$(mem_safe_jobs)" --target jass >"$W/bd-$(basename "$1").log" 2>&1 || { echo "BUILD FAIL $1"; tail -8 "$W/bd-$(basename "$1").log"; exit 6; }; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1

echo "=== build men-only (defaut) + king-aware (-DJASS_KING_PATTERNS=ON) ==="
cmake_jass "$W/build-men"  ""
cmake_jass "$W/build-king" "-DJASS_KING_PATTERNS=ON"
JMEN="$W/build-men/jass"; JKING="$W/build-king/jass"
[ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { echo "ABORT: attendait 32 patterns, a $NP"; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
# garde-fou : le build king doit reellement etre king-aware (sinon test faux-null)
grep -q "JASS_KING_PATTERNS" "$W/cmake-build-king.log" || echo "WARN: JASS_KING_PATTERNS absent du cmake king ?"
say "# builds OK : men-only ($JMEN) + king-aware ($JKING)"

echo "=== assemble le corpus depuis les shards committes ==="
tools/corpus_manifest.sh assemble "$W/big.jnnw" 2>"$W/assemble.log" || { echo "ABORT assemble"; tail "$W/assemble.log"; exit 8; }
NBIG=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/big.jnnw','rb').read(8)[4:8])[0])")
say "# corpus assemble : ${NBIG} positions"
[ "$NBIG" -ge 25000000 ] || { echo "ABORT: corpus ${NBIG} < 25M"; exit 8; }

echo "=== dump FEAT (extras identiques men/king, dump via build men-only) ==="
"$JMEN" --dump-eval-features "$W/big.jnnw" "$W/feat.full" >"$W/feat.log" 2>&1 || { echo "ABORT dump feat"; tail "$W/feat.log"; exit 8; }

fit(){ # $1=extraflag $2=out $3=tag
  echo "  [fit $3] train_stream color-fold $1 logistic maxit=$MAXIT"
  env JASS_PATTERNS_DIR="$GEOM" python3 pattern_jass/tools/train_stream.py --data "$W/big.jnnw" --feat "$W/feat.full" \
      --color-fold --tempo-stage $1 --loss logistic --l2 1e-4 --max-iter "$MAXIT" --chunk "$CHUNK" --out "$2" \
      >"${2%.pjtw}.log" 2>&1 || { echo "TRAIN FAIL $3"; tail -12 "${2%.pjtw}.log"; exit 9; }
  grep -iE "occupancy|fold :|train_loss|wrote" "${2%.pjtw}.log" | tail -4 | sed 's/^/    /'; }

say "# --- FITS (color-fold, meme corpus ${NBIG} ; men vs king) ---"
fit ""                "$W/men.pjtw"  "men-only(baseline)"
fit "--king-patterns" "$W/king.pjtw" "king-aware"
gzip -c "$W/men.pjtw"  > "$ART/w32-men.pjtw.gz"  2>/dev/null || true
gzip -c "$W/king.pjtw" > "$ART/w32-king.pjtw.gz" 2>/dev/null || true
say "# fits OK (men + king gzippes en artefacts)"

# juge : chaque build joue SON pjtw (marqueur king rejette un mauvais appariement)
judge_king_vs_men(){
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py \
     --jass-a "$JKING" --pattern-a "$W/king.pjtw" --jass-b "$JMEN" --pattern-b "$W/men.pjtw" \
     --depth 9 --pairs 14 --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet >"$W/j.$s" 2>"$W/je.$s" & done; wait
  python3 - "$W"/j.* <<'PY'
import sys; a=d=b=0
for f in sys.argv[1:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x); d+=int(y); b+=int(z)
  except: pass
g=a+d+b; print(f"{(a+0.5*d)/g:.4f} (N={g})" if g else "NA")
PY
}
say "# --- JUGE (score = king-aware vs men-only baseline, >0.5 => les ROIS aident) ---"
say "K  32cf king-aware vs 32cf men-only = $(judge_king_vs_men)   [les rois dans les patterns paient-ils au scale ?]"

say ""
say "================= LECTURE ================="
say "  K > 0.55  => les ROIS dans les patterns paient au scale (etaient CONFONDUS par le fit ~2M) -> archi candidate."
say "  K ~ 0.5   => neutre a ${NBIG} (rois ~OK mais pas decisifs ; retester a 100M)."
say "  K < 0.45  => men-only confirme meilleur (les buckets king diluent ; verdict 0240/0360 tient au scale)."
say "==========================================="
