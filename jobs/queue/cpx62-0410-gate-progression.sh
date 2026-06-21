#!/usr/bin/env bash
# id: cpx62-0410-gate-progression
# description: GATE PROGRESSION — mesure le gain de volume au DOUBLEMENT (la vraie progression, pas les +0,8M/round
# qui sont sous le bruit). Baseline FIGE = w32_full (32cf@29M, archive par 0401). Challenger = 32cf REFIT sur le corpus
# accumule courant. AUTO-GARDE : si le corpus < THRESH (doublement pas atteint), no-op propre (exit 0) -> a re-deployer
# quand le volume est la. Sinon : build 32-pat, assemble, dump FEAT, fit 32cf challenger (meme config que 0401), juge
# challenger vs baseline. >0.55 => la 32cf PROGRESSE encore avec le volume (prediction 0401 : avantage croit vers 100M).
# Meme build/fold/extras des 2 cotes => isole l'effet VOLUME. Hors-tree (/root/cw-prog), gzip. Aucun Scan.
# expected_duration: ~3 h (au-dela du seuil ; quasi-instantane si no-op)
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-300}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0410-gate-progression/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"
W=/root/cw-prog; rm -rf "$W"; mkdir -p "$W"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
GEOM=/root/jass-geom32-prog; MAXIT=25; CHUNK=1000000
BASE_VOL=29010792                       # volume du baseline w32_full (0401)
THRESH=55000000                         # seuil "doublement" (~1.9x le baseline) ; sinon no-op
BASE_GZ=jobs/results/cpx62-0401-gate-matrix-2x2/artefacts/w32_full.pjtw.gz
say(){ echo "$@" | tee -a "$RES"; }

# ---------- AUTO-GARDE : assemble d'abord, no-op si sous le seuil ----------
echo "=== assemble le corpus accumule (tous les shards committes) ==="
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
tools/corpus_manifest.sh assemble "$W/big.jnnw" 2>"$W/assemble.log" || { echo "ABORT assemble"; tail "$W/assemble.log"; exit 8; }
NBIG=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/big.jnnw','rb').read(8)[4:8])[0])")
RATIO=$(python3 -c "print(f'{$NBIG/$BASE_VOL:.2f}')")
say "# corpus courant : ${NBIG} positions  (x${RATIO} le baseline ${BASE_VOL})"
if [ "$NBIG" -lt "$THRESH" ]; then
  say "# NO-OP : ${NBIG} < seuil ${THRESH} (doublement pas atteint). Re-deployer ce gate quand le corpus aura double."
  say "# (rien gaspille : aucun build ni fit lance.)"
  exit 0
fi

# ---------- au-dela du seuil : on mesure la progression ----------
preflight_build 1; preflight_train "$NBIG" 1; preflight_note "gate progression : fit 32cf challenger + juge vs baseline 29M" 120; preflight_check

echo "=== build 32-pat (memes flags que 0401) ==="
cmake -S . -B "$W/build-32" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb"; exit 6; }
cmake --build "$W/build-32" -j"$(mem_safe_jobs)" --target jass >"$W/bd.log" 2>&1 || { echo "BUILD FAIL"; tail -8 "$W/bd.log"; exit 6; }
J32="$W/build-32/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { echo "ABORT: attendait 32 patterns, a $NP"; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
say "# build OK : 32-pat ($J32)"

echo "=== recupere + decompresse le baseline w32_full (0401) ==="
git cat-file -e "origin/main:$BASE_GZ" 2>/dev/null || { echo "ABORT: baseline $BASE_GZ absent"; exit 4; }
git show "origin/main:$BASE_GZ" | gunzip > "$W/baseline.pjtw" || { echo "ABORT gunzip baseline"; exit 4; }

echo "=== dump FEAT + fit 32cf challenger sur ${NBIG} ==="
"$J32" --dump-eval-features "$W/big.jnnw" "$W/feat.full" >"$W/feat.log" 2>&1 || { echo "ABORT dump feat"; tail "$W/feat.log"; exit 8; }
env JASS_PATTERNS_DIR="$GEOM" python3 pattern_jass/tools/train_stream.py --data "$W/big.jnnw" --feat "$W/feat.full" \
    --color-fold --tempo-stage --loss logistic --l2 1e-4 --max-iter "$MAXIT" --chunk "$CHUNK" --out "$W/chal.pjtw" \
    >"$W/chal.log" 2>&1 || { echo "TRAIN FAIL challenger"; tail -12 "$W/chal.log"; exit 9; }
grep -iE "fold :|train_loss|wrote" "$W/chal.log" | tail -3 | sed 's/^/    /'
gzip -c "$W/chal.pjtw" > "$ART/w32-challenger-${NBIG}.pjtw.gz" 2>/dev/null || true
say "# challenger fit OK (32cf@${NBIG}, gzippe en artefact)"

echo "=== juge challenger@${NBIG} vs baseline@${BASE_VOL} ==="
for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py \
   --jass-a "$J32" --pattern-a "$W/chal.pjtw" --jass-b "$J32" --pattern-b "$W/baseline.pjtw" \
   --depth 9 --pairs 28 --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet >"$W/j.$s" 2>"$W/je.$s" & done; wait
SCORE=$(python3 - "$W"/j.* <<'PY'
import sys; a=d=b=0
for f in sys.argv[1:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x); d+=int(y); b+=int(z)
  except: pass
g=a+d+b; print(f"{(a+0.5*d)/g:.4f} (N={g})" if g else "NA")
PY
)
say "# --- VERDICT PROGRESSION ---"
say "P  32cf@${NBIG} (x${RATIO}) vs 32cf@${BASE_VOL} baseline = ${SCORE}   [le volume paie-t-il encore au doublement ?]"
say ""
say "================= LECTURE ================="
say "  P > 0.55  => la 32cf PROGRESSE encore avec le volume (prediction 0401 confirmee, viser 100M)."
say "  P ~ 0.50  => debut de plateau du fit-volume a ce palier (re-tester au doublement suivant avant conclure)."
say "  P < 0.45  => regression (sur-ajustement/data bruitee ?) -> diagnostiquer la qualite de la gen."
say "==========================================="
