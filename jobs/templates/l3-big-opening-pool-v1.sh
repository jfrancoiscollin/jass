#!/usr/bin/env bash
# L3 — engendrer un pool d'ouvertures de 3000, disjoint des pools de porte.
#
# Toutes les portes de la campagne tournent à `n = 6000` parce que les pools
# font 1500 ouvertures : chacune est déjà jouée deux fois, couleurs inversées, et
# à profondeur fixe le moteur est DÉTERMINISTE — rejouer une ouverture rend la
# même partie. `n` est donc plafonné par la taille du pool, et augmenter
# `--pairs` ne fabriquerait que des doublons.
#
# Or on ne chasse plus des effets de 60 Elo mais de 10 : à `n=6000` l'erreur-type
# vaut ~4,4 Elo, soit ~56 % de puissance pour un effet de `+9`. Un pool de 3000
# porte `n = 12 000` et ~84 %. Écrit une fois, il sert toutes les portes futures.
#
# Aucune promotion, aucun chaînage automatique.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"
: > "$RES"; : > "$PROG"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ say "phase=$1"; }

NOPEN="${NOPEN:-3000}"
CANDIDATES="${CANDIDATES:-24000}"     # marge x8, comme le précédent (6000 pour 1500)
OPENING_SEED="${OPENING_SEED:-2718281}"
finalize(){ rc=$?; trap - EXIT ERR; set +e
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null
  rm -rf "$W/build" "$IN" 2>/dev/null; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"

stage build
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$(nproc)" --target jass > "$W/build.log" 2>&1
git checkout -- src/ pattern_jass/ 2>/dev/null || true
J="$W/build/jass"; [ -x "$J" ] || die "build sans binaire"

stage fetch-pools-to-exclude
# ⚠️ On exclut les pools RÉELLEMENT utilisés par les portes courantes. Le
# préflight de juillet en excluait seize ; ici deux suffisent pour l'usage visé,
# et c'est écrit plutôt que sous-entendu — un futur lecteur doit savoir que la
# disjonction n'est PAS prouvée contre toute la série historique.
python3 jobs/tools/fetch_result_files.py \
  --prefix "r2:jass-data/runs/home-1004-l3-pure-volume8m-preflight-v2/20260727T211936Z-90d3aad1" \
  --file artefacts/vol8m-eval-openings.fen=pool-vol8m.fen \
  --out-dir "$IN" --report "$ART/verified-pool-a.json" --expected-state completed \
  > "$W/fetch-a.log" 2>&1 || die "fetch pool vol8m KO"
python3 jobs/tools/fetch_result_files.py \
  --prefix "r2:jass-data/runs/home-0995-l3-pure-turnover-succession-preflight-v2/20260727T054246Z-f20e59d0" \
  --file artefacts/turnover-succession-openings.fen=pool-succession.fen \
  --out-dir "$IN" --report "$ART/verified-pool-b.json" --expected-state completed \
  > "$W/fetch-b.log" 2>&1 || die "fetch pool succession KO"
say "  2 pools de porte récupérés pour exclusion"

stage generate-and-select
# Deux passes identiques : un pool d'ouvertures non reproductible ne serait pas
# citable comme référence.
for p in a b; do
  "$J" --gen-opening-pool "$CANDIDATES" "$W/cand-$p.fen" 8 32 20 "$OPENING_SEED" \
    > "$W/cand-$p.log" 2>&1
done
cmp -s "$W/cand-a.fen" "$W/cand-b.fen" || die "candidats non déterministes"
NC=$(grep -c . "$W/cand-a.fen" || true); say "  candidats ✓ $NC (déterministes)"
[ "$NC" -ge "$NOPEN" ] || die "moins de candidats ($NC) que d'ouvertures visées ($NOPEN)"

sel(){ python3 jobs/tools/select_independent_opening_pool.py \
  --candidates "$1" --expected "$NOPEN" \
  --exclude "$IN/pool-vol8m.fen" --exclude "$IN/pool-succession.fen" \
  --generator-seed "$OPENING_SEED" --out "$2" --manifest "$3" > "$4" 2>&1; }
sel "$W/cand-a.fen" "$ART/big3000-openings.fen" "$ART/big3000-openings.json" "$W/sel-a.log" ||
  die "sélection KO — voir sel-a.log"
sel "$W/cand-b.fen" "$W/repeat.fen" "$W/repeat.json" "$W/sel-b.log" || die "sélection (répétition) KO"
cmp -s "$ART/big3000-openings.fen" "$W/repeat.fen" || die "sélection non reproductible"

stage verify
N=$(grep -c . "$ART/big3000-openings.fen" || true)
[ "$N" -eq "$NOPEN" ] || die "pool à $N ouvertures, attendu $NOPEN"
for f in pool-vol8m pool-succession; do
  COMMON=$(grep -Fx -f "$IN/$f.fen" "$ART/big3000-openings.fen" | grep -c . || true)
  [ "$COMMON" -eq 0 ] || die "chevauchement de $COMMON ouvertures avec $f"
done
python3 jobs/tools/validate_opening_pool.py --pool "$ART/big3000-openings.fen" \
  > "$W/validate.log" 2>&1 || die "pool invalide — voir validate.log"
SHA=$(sha256sum "$ART/big3000-openings.fen" | awk '{print $1}')
say "  pool ✓ $N ouvertures, disjoint des 2 pools de porte, sha256=$SHA"
say "  porte future : $N × 2 couleurs × 2 vues = $((N * 4)) parties"

stage report
python3 - "$ART/JASS_CONTROL_SUMMARY.json" "$N" "$SHA" <<'PY'
import json, sys
out, n, sha = sys.argv[1:4]
json.dump({"schema": 1, "verdict": f"BIG_OPENING_POOL_READY_{n}", "openings": int(n),
           "sha256": sha, "gate_n_at_two_views": int(n) * 4,
           "disjoint_from": ["home-1004 vol8m", "home-0995 succession"],
           "diagnostic_only": True, "promotion_authorized": False,
           "automatic_next_job": None}, open(out, "w"), indent=2, sort_keys=True)
open(out, "a").write("\n")
PY
: > "$ART/VERDICT__BIG_OPENING_POOL_READY_$N"
printf 'PROMOTION_AUTHORIZED__FALSE\n' > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'AUTOMATIC_NEXT_JOB__NULL\n'    > "$ART/AUTOMATIC_NEXT_JOB__NULL"
say "BIG_OPENING_POOL_READY_$N promotion=false automatic_next_job=null"
