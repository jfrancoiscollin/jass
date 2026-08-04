#!/usr/bin/env bash
# L3 — AUDIT D'ÉTIQUETAGE contre la tablebase. Lecture seule, aucun modèle.
#
# Le corpus WDL étiquette chaque position par le RÉSULTAT DE LA PARTIE. Sur les
# positions où la tablebase sait (≤ 7 pièces), ce résultat peut être FAUX : une
# position théoriquement nulle, gagnée par une bourde ultérieure, porte
# l'étiquette « gain ». Le taux de désaccord est donc une mesure DIRECTE et
# ABSOLUE du bruit d'étiquetage — pas un proxy, pas une perte de holdout.
#
# ⚠️ Il ne couvre que les finales, là où le résultat de partie est justement le
# PLUS fiable : le chiffre rendu est une BORNE OPTIMISTE du bruit réel.
#
# Aucune promotion, aucun modèle produit, aucune continuation.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"; : "${AUDIT_SPECS:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom"; mkdir -p "$W" "$IN" "$ART" "$GEOM"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: > "$RES"; : > "$PROG"; echo start > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "phase=$1"; }
CACHE_MB="${CACHE_MB:-2048}"
PER_CORPUS_TIMEOUT="${PER_CORPUS_TIMEOUT:-2700s}"

MON=""
monitor(){ ( t0=$(date +%s); while true; do
    { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
      printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
      printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
    } > "$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120
  done ) & MON="$!"; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt"; [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W"/build* "$IN" "$W"/*.jnnw 2>/dev/null || true
  exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"

stage disk-guard
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 8000 ] || die "moins de 8 Go libres (${DFA} Mo)"
say "  nproc=$(nproc) libre=${DFA}Mo"
monitor

stage build-with-egdb
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "aucune base EGDB sur $(hostname) — cet audit n'a aucun sens sans elle"
[ -d /root/egdb_intl ] || die "base EGDB trouvée ($EGDIR) mais la bibliothèque /root/egdb_intl manque"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$(nproc)" --target jass > "$W/build.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "build sans binaire"
say "  build ✓ avec EGDB ($EGDIR)"

stage audit
# AUDIT_SPECS : une ligne par corpus, "label|prefix_r2|chemin_distant".
n_ok=0
while IFS='|' read -r LBL PFX PATHR; do
  [ -n "${LBL:-}" ] || continue
  stage "audit-$LBL"
  base=$(basename "$PATHR")
  python3 jobs/tools/fetch_result_files.py --prefix "$PFX" \
    --file "$PATHR=$base" --out-dir "$IN" --report "$ART/verified-$LBL.json" \
    --expected-state completed > "$W/fetch-$LBL.log" 2>&1 || die "fetch $LBL en échec"
  src="$IN/$base"
  case "$base" in *.gz) gunzip -c "$src" > "$W/$LBL.jnnw"; src="$W/$LBL.jnnw";; esac
  say "  --- corpus $LBL ---"
  # Point 5 de la check-list : un corpus qui traîne ne doit JAMAIS geler le job.
  # Un dépassement est rapporté INCOMPLET et on passe au suivant ; le compte
  # `n_ok` ne monte que sur un audit qui a rendu ses compteurs (point 10).
  t0=$(date +%s); arc=0
  timeout -k 60s "$PER_CORPUS_TIMEOUT" \
    "$J" --egdb-audit "$src" "$EGDIR" "$CACHE_MB" > "$W/audit-$LBL.log" 2>&1 || arc=$?
  dt=$(( $(date +%s) - t0 ))
  cp "$W/audit-$LBL.log" "$ART/audit-$LBL.txt"
  rm -f "$W/$LBL.jnnw" "$IN/$base"
  if [ "$arc" -eq 124 ] || [ "$arc" -eq 137 ]; then
    say "  ⚠️ $LBL INCOMPLET : timeout après ${dt}s (PER_CORPUS_TIMEOUT=$PER_CORPUS_TIMEOUT)"
    continue
  fi
  [ "$arc" -eq 0 ] || { say "  ⚠️ $LBL ÉCHEC rc=$arc — voir audit-$LBL.txt"; continue; }
  line=$(grep -m1 '^EGDBAUDIT' "$W/audit-$LBL.log" || true)
  [ -n "$line" ] || { say "  ⚠️ $LBL SANS COMPTEURS — voir audit-$LBL.txt"; continue; }
  inr=$(sed -n 's/.*\bin_range=\([0-9]\+\).*/\1/p' <<< "$line")
  # n=0 est un ÉCHEC, pas un « neutre » (point 10) : un corpus sans une seule
  # position dans la portée de la base ne mesure rien du tout.
  [ "${inr:-0}" -gt 0 ] || { say "  ⚠️ $LBL in_range=0 — RIEN MESURÉ, cellule rejetée"; continue; }
  grep -E '^EGDBAUDIT|^EGDBCONF' "$W/audit-$LBL.log" | sed 's/^/  /' | tee -a "$RES"
  say "  $LBL ✓ en ${dt}s"
  n_ok=$((n_ok + 1))
done <<< "$AUDIT_SPECS"
[ "$n_ok" -gt 0 ] || die "aucun corpus audité avec des compteurs exploitables"

stage report
say "EGDB_LABEL_AUDIT_READY corpus=$n_ok promotion=false automatic_next_job=null"
: > "$ART/PROMOTION_AUTHORIZED__FALSE"
: > "$ART/AUTOMATIC_NEXT_JOB__NULL"
: > "$ART/VERDICT__EGDB_LABEL_AUDIT_READY"
stage complete
