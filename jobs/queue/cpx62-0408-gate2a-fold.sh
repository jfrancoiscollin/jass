#!/usr/bin/env bash
# id: cpx62-0408-gate2a-fold
# description: GATE 2a — axe REPLI (fold) a gros volume. La 32cf (color-fold) est l'archi de prod ; on teste si
# MOINS replier paie au scale (BIAIS_FIT_VOLUME #2/#5 : invariance/partage CONFONDUS par le fit ≤2M). 3 fits
# train_stream sur le corpus accumule (men-only, meme binaire 32-pat) : color-fold (BASELINE = archi prod),
# no-fold (17M plein, zero partage), full-fold (la "mauvaise invariance" translation, CONTROLE qui doit PERDRE).
# Les 3 .pjtw s'expandent au MEME layout 17M men-only -> UN SEUL build juge les 3 (jass_vs_jass_arch). 2 juges
# cross vs baseline. Hors-tree (/root/cw-gate2a), transport gzip. Aucun Scan. S'enchaine apres 0405 (cpx62 libre).
# NB king-patterns: PAS ici (train_stream code king=False/men-only -> test ON/OFF serait un faux null ; gate dediee
# apres extension train_stream). expected_duration: ~6 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-480}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0408-gate2a-fold/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"
W=/root/cw-gate2a; rm -rf "$W"; mkdir -p "$W"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
GEOM32=/root/jass-geom32-2a; MAXIT=25; CHUNK=1000000
say(){ echo "$@" | tee -a "$RES"; }

preflight_build 1; preflight_train 31000000 1; preflight_note "assemble corpus + dump feat + 3 fits fold + 2 juges" 200; preflight_check

cmake_jass(){ cmake -S . -B "$1" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
  grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb"; exit 6; }
  cmake --build "$1" -j"$(mem_safe_jobs)" --target jass >"$W/bd.log" 2>&1 || { echo "BUILD FAIL"; tail -8 "$W/bd.log"; exit 6; }; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1

echo "=== build 32-pat (defaut men-only) ==="
cmake_jass "$W/build-32"; J32="$W/build-32/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
NP32=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP32" = 32 ] || { echo "ABORT: attendait 32 patterns, a $NP32"; exit 7; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"
say "# build OK : 32-pat men-only ($J32)"

echo "=== assemble le corpus depuis les shards committes ==="
tools/corpus_manifest.sh assemble "$W/big.jnnw" 2>"$W/assemble.log" || { echo "ABORT assemble"; tail "$W/assemble.log"; exit 8; }
NBIG=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/big.jnnw','rb').read(8)[4:8])[0])")
say "# corpus assemble : ${NBIG} positions"
[ "$NBIG" -ge 25000000 ] || { echo "ABORT: corpus ${NBIG} < 25M (shards manquants ?)"; exit 8; }

echo "=== dump FEAT (extras, arch-independant) ==="
"$J32" --dump-eval-features "$W/big.jnnw" "$W/feat.full" >"$W/feat.log" 2>&1 || { echo "ABORT dump feat"; tail "$W/feat.log"; exit 8; }

fit(){ # $1=foldflag $2=out $3=tag
  echo "  [fit $3] train_stream '$1' logistic maxit=$MAXIT"
  env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/big.jnnw" --feat "$W/feat.full" \
      $1 --tempo-stage --loss logistic --l2 1e-4 --max-iter "$MAXIT" --chunk "$CHUNK" --out "$2" \
      >"${2%.pjtw}.log" 2>&1 || { echo "TRAIN FAIL $3"; tail -12 "${2%.pjtw}.log"; exit 9; }
  grep -iE "fold :|train_loss|wrote" "${2%.pjtw}.log" | tail -3 | sed 's/^/    /'; }

say "# --- FITS (axe fold, meme corpus ${NBIG}, meme maxit) ---"
fit "--color-fold" "$W/cf.pjtw" "color-fold(baseline)"
fit ""             "$W/nf.pjtw" "no-fold"
fit "--full-fold"  "$W/ff.pjtw" "full-fold"
gzip -c "$W/cf.pjtw" > "$ART/w32-color-fold.pjtw.gz" 2>/dev/null || true
gzip -c "$W/nf.pjtw" > "$ART/w32-no-fold.pjtw.gz"    2>/dev/null || true
say "# fits OK (color-fold + no-fold gzippes en artefacts)"

judge(){ # $1=PA $2=PB ; score A vs B
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py \
     --jass-a "$J32" --pattern-a "$1" --jass-b "$J32" --pattern-b "$2" \
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
say "# --- JUGES (score = A vs baseline color-fold, >0.5 => A gagne) ---"
say "NF  32 no-fold   vs 32 color-fold = $(judge "$W/nf.pjtw" "$W/cf.pjtw")   [moins replier paie-t-il au scale ?]"
say "FF  32 full-fold vs 32 color-fold = $(judge "$W/ff.pjtw" "$W/cf.pjtw")   [controle : la mauvaise invariance doit PERDRE]"

say ""
say "================= LECTURE ================="
say "  NF > 0.55  => MOINS replier paie au scale (no-fold > color-fold) -> candidate archi de prod."
say "  NF ~ 0.5   => color-fold suffit a ${NBIG} (no-fold ~1.7 visite/poids, encore affame -> retester a 100M)."
say "  FF < 0.5   => full-fold (invariance par translation) confirme PERDANT (controle attendu)."
say "==========================================="
