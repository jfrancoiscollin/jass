#!/usr/bin/env bash
# id: cpx62-0369-merge-champion
# description: ÉTAGE 2 de l'orchestration distribuée (capitalisation des 2 runs). Lit la data 0366 (d10, LOCALE cpx62)
# + tire la data 0367 (d12) committée par 0368, DÉPARTAGE les 2 évals en DIRECT, POOLE les deux corpus WDL (volume
# d10 + qualité d12 = « les deux d'un coup »), et RE-FIT l'archi sur le pool combiné → champion. Juge champion vs
# chaque box EN DIRECT : pooler bat-il les 2 ? Committe le champion (réutilisable comme pilote du prochain tour =
# amorce de la boucle distribuée poolée). DÉPLOYER après 0368 (qui dépend de la fin de 0367). Aucun Scan (pivot self).
# expected_duration: ~45 min
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-90}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0369-merge-champion/artefacts"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"; SCALE=1000
SRC66=/root/jass/jobs/results/cpx62-0366-virtuous-loop-deep/artefacts.src
H0368=jobs/results/ccx33-0368-harvest-0367/artefacts
preflight_build 1; preflight_train 1500000 1; preflight_note "merge + champion + DIRECT" 30; preflight_check

[ -d "$SRC66" ] && [ -f "$SRC66/cumulative.jnnw" ] || { echo "ABORT: data 0366 (locale cpx62) introuvable (container recyclé ?)"; exit 4; }
GEN66=$(ls "$SRC66"/gen*.pjtw 2>/dev/null | sort -V | tail -1); [ -n "$GEN66" ] || { echo "ABORT: pas d'éval 0366"; exit 4; }
echo "  0366 (d10) : data=$SRC66/cumulative.jnnw  éval=$GEN66"

echo "=== attente de la data 0367 committée par 0368 ==="
ok=0; for i in $(seq 1 30); do
  git fetch origin main >/dev/null 2>&1 || true
  if git cat-file -e "origin/main:$H0368/0367-cumulative.jnnw" 2>/dev/null; then ok=1; break; fi
  echo "  ...0368 pas encore committé ($i/30)"; sleep 30
done
[ "$ok" = 1 ] || { echo "ABORT: data 0367 absente après attente (0368 a échoué ?)"; exit 4; }
git show "origin/main:$H0368/0367-cumulative.jnnw" > "$ART/0367-cumulative.jnnw"
for p in $(git ls-tree --name-only "origin/main" "$H0368/" | grep -E '0367-gen.*\.pjtw'); do
  git show "origin/main:$p" > "$ART/$(basename "$p")"; done
GEN67=$(ls "$ART"/0367-gen*.pjtw 2>/dev/null | sort -V | tail -1); [ -n "$GEN67" ] || { echo "ABORT: pas d'éval 0367 récupérée"; exit 4; }
echo "  0367 (d12) : data=$ART/0367-cumulative.jnnw  éval=$GEN67"

echo "=== build (même archi 32-pat que les boucles) ==="
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
B=build-prod; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -8 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"
direct(){ "$JASS" --benchmark-nnue-vs-nnue "$1" "$2" 9 6 1 0 >"$3" 2>&1 || true; grep -E 'score rate' "$3" | grep -oE '[0-9.]+' | head -1; }

echo "=== DÉPARTAGE : 0366(d10) vs 0367(d12) en DIRECT ==="
D_6667=$(direct "$GEN66" "$GEN67" "$ART/d10_vs_d12.log")
echo "  d10 vs d12 = ${D_6667}  (>0.5 → d10 plus fort ; <0.5 → d12 plus fort)"

echo "=== POOL des 2 corpus WDL (volume d10 + qualité d12) ==="
cp "$SRC66/cumulative.jnnw" "$ART/pooled.jnnw"
python3 - "$ART/0367-cumulative.jnnw" "$ART/pooled.jnnw" <<'PY'
import struct,sys
src,pool=sys.argv[1],sys.argv[2]; REC=38
b=open(src,'rb').read(); n=(len(b)-8)//REC; body=b[8:8+n*REC]
raw=open(pool,'rb').read(); old=struct.unpack('<I',raw[4:8])[0]
o=open(pool,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+n)); o.close()
print(f"  pool = {old} (d10) + {n} (d12) = {old+n} positions")
PY

echo "=== RE-FIT du champion sur le pool combiné (logistique, full-fold) ==="
"$JASS" --dump-eval-features "$ART/pooled.jnnw" "$ART/pooled.feat" >/dev/null 2>&1
python3 pattern_jass/tools/train.py --data "$ART/pooled.jnnw" --scan-eval --eval-features-file "$ART/pooled.feat" \
  --loss logistic --l2 1e-4 --max-iter 250 --scale "$SCALE" --prune --lowmem --full-fold \
  --out "$ART/champion.pjtw" >"$ART/champion-train.log" 2>&1
[ -f "$ART/champion.pjtw" ] || { echo "TRAIN FAIL"; tail -8 "$ART/champion-train.log"; exit 9; }

echo "=== le champion poolé bat-il chaque box ? (DIRECT) ==="
C_VS_66=$(direct "$ART/champion.pjtw" "$GEN66" "$ART/champ_vs_d10.log")
C_VS_67=$(direct "$ART/champion.pjtw" "$GEN67" "$ART/champ_vs_d12.log")

echo; echo "=========================================================="
echo "   cpx62-0369 — CAPITALISATION : champion poolé (d10 ∪ d12)"
echo "----------------------------------------------------------"
echo "   départage  : d10 vs d12 = ${D_6667}"
echo "   champion vs d10 = ${C_VS_66}   |   champion vs d12 = ${C_VS_67}"
echo "----------------------------------------------------------"
echo "   champion > 0.5 vs LES DEUX → pooler (volume+qualité) bat chaque box seule → la capitalisation MARCHE."
echo "   → champion.pjtw committé = pilote du prochain tour (boucle distribuée poolée : générer→pooler→refit→...)."
echo "=========================================================="