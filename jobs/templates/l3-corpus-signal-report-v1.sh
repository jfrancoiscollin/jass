#!/usr/bin/env bash
# L3 — FICHE SIGNALÉTIQUE DE CORPUS (jalon M1 de l'usine à signal).
#
# Lecture seule : aucun modèle produit, aucun corpus réécrit, aucune promotion.
#
# Rend, pour un couple (JNNW, JSM2) authentifié, le JSON unique des quatre
# familles de la charte : structure, contamination post-epsilon, ply-cap,
# couverture exacte, et — si la box a une base — le désaccord tablebase.
#
# ⛔ JSM2 EST OBLIGATOIRE. `corpus_signal_report.py` refuse un JSM1 parce que
# les champs de contexte (ply, game_plies, last_eps_ply, game_result POV BLANC,
# flags) n'y existent pas et ne s'y reconstituent pas. Ce template le vérifie
# AVANT de dépenser quoi que ce soit : le magic réel du sidecar est lu, pas
# supposé.
#
# ⚠️ FISHER EST HORS PÉRIMÈTRE PAR DÉFAUT (`WITH_FISHER=0`). p(1−p) exige un
# dump FEAT aligné sur le corpus ENTIER, produit par le même chemin que le fit —
# une ré-implémentation ne mesurerait pas le modèle qu'on entraîne. C'est
# plusieurs dizaines de minutes sur 12 M ; on l'active explicitement, avec un
# modèle, quand on en veut le prix.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${CORPUS_PREFIX:?}"; : "${CORPUS_JOB:?}"
: "${CORPUS_DATA_FILE:?}"; : "${CORPUS_META_FILE:?}"; : "${CORPUS_LABEL:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"; mkdir -p "$W" "$IN" "$ART" "$GEOM"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: > "$RES"; : > "$PROG"; echo start > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "phase=$1"; }
CACHE_MB="${CACHE_MB:-4096}"
WITH_FISHER="${WITH_FISHER:-0}"
REPORT_TIMEOUT="${REPORT_TIMEOUT:-3600s}"

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
  rm -rf "$W"/build* "$IN" "$W"/*.jnnw "$W"/*.jsm 2>/dev/null || true
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

stage fetch-corpus
python3 jobs/tools/fetch_result_files.py --prefix "$CORPUS_PREFIX" \
  --file "$CORPUS_DATA_FILE=corpus.jnnw.gz" \
  --file "$CORPUS_META_FILE=corpus.jsm.gz" \
  --out-dir "$IN" --report "$ART/verified-corpus.json" \
  --expected-state completed > "$W/fetch.log" 2>&1 || die "fetch du corpus en échec"
gunzip -c "$IN/corpus.jnnw.gz" > "$W/corpus.jnnw"
gunzip -c "$IN/corpus.jsm.gz"  > "$W/corpus.jsm"
say "  corpus ✓ : $CORPUS_LABEL depuis $CORPUS_JOB"

stage assert-jsm2
# Le magic est LU, pas suppose. Un JSM1 ici ferait echouer le rapport apres le
# build de la geometrie ; on le refuse avant de depenser quoi que ce soit.
MAGIC=$(head -c4 "$W/corpus.jsm")
[ "$MAGIC" = "JSM2" ] ||
  die "sidecar en '$MAGIC' : M1 exige JSM2 (les champs de contexte n'existent pas en JSM1)"
NREC=$(python3 -c "
import struct,sys
d=open('$W/corpus.jsm','rb').read(8); print(struct.unpack_from('<I',d,4)[0])")
NDAT=$(python3 -c "
import struct,os
p='$W/corpus.jnnw'; d=open(p,'rb').read(8)
assert d[:4]==b'JNNW', d[:4]
print(struct.unpack_from('<I',d,4)[0])")
[ "$NREC" = "$NDAT" ] || die "JNNW ($NDAT) et JSM2 ($NREC) desalignes"
[ "${NREC:-0}" -gt 0 ] || die "corpus vide : aucun signal a mesurer"
say "  sidecar ✓ : JSM2, $NREC records alignes sur le JNNW"

stage build-8cf-geometry
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
say "  géométrie 8cf ✓"

stage egdb-probe
# La base est un BONUS, pas un prerequis : sans elle le rapport rend tout sauf
# le desaccord tablebase. Avec elle il faut un binaire compile EGDB=ON.
EGDB_ARGS=()
EGDIR=""
for cand in /root/egdb_extracted/app /root/egdb/app /root/egdb_extracted /root/egdb; do
  [ -d "$cand" ] && { EGDIR="$cand"; break; }
done
if [ -n "$EGDIR" ] && [ -d /root/egdb_intl ]; then
  FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl"
  cmake -S . -B "$W/build" $FLAGS > "$W/cmake.log" 2>&1
  cmake --build "$W/build" -j"$(nproc)" --target jass > "$W/build.log" 2>&1
  [ -x "$W/build/jass" ] || die "build EGDB sans binaire"
  EGDB_ARGS=(--egdb "$EGDIR" --jass "$W/build/jass" --egdb-cache-mb "$CACHE_MB")
  say "  EGDB ✓ ($EGDIR) — le désaccord tablebase sera mesuré"
else
  say "  ⚠️ EGDB absent — rapport sans le désaccord tablebase"
fi

stage signal-report
FISHER_ARGS=()
if [ "$WITH_FISHER" = 1 ]; then
  : "${MODEL_PATH:?WITH_FISHER=1 exige MODEL_PATH}"
  : "${FEATURES_PATH:?WITH_FISHER=1 exige FEATURES_PATH (dump FEAT aligné)}"
  FISHER_ARGS=(--model "$MODEL_PATH" --features "$FEATURES_PATH")
  say "  Fisher activé sur $MODEL_PATH"
else
  say "  Fisher ⊘ (WITH_FISHER=0 : exige un dump FEAT aligné sur les $NREC records)"
fi
env PYTHONPATH="$GEOM:pattern_jass/tools" \
  timeout "$REPORT_TIMEOUT" python3 jobs/tools/corpus_signal_report.py \
    --data "$W/corpus.jnnw" --meta "$W/corpus.jsm" \
    ${EGDB_ARGS[@]+"${EGDB_ARGS[@]}"} ${FISHER_ARGS[@]+"${FISHER_ARGS[@]}"} \
    --out "$ART/signal-report.json" > "$W/report.log" 2>&1 ||
  die "corpus_signal_report en échec — voir report.log"
[ -s "$ART/signal-report.json" ] || die "fiche vide"

stage read-back
# Round-trip ecriture->lecture (regle 9) : on RELIT ce que le rapport a ecrit
# et on affiche les chiffres qui comptent, plutot que de supposer qu'ils y sont.
python3 - "$ART/signal-report.json" "$NREC" "${EGDIR:-}" "$WITH_FISHER" <<'PY' | tee -a "$RES"
import json, sys
rep = json.load(open(sys.argv[1]))
expected, egdir, with_fisher = int(sys.argv[2]), sys.argv[3], sys.argv[4] == "1"
# Les blocs de la fiche sont a la RACINE (build_report fait **base) ; la
# couverture est sous la cle FRANCAISE "couverture". Un bloc absent est une
# ERREUR, pas un silence : c'est tout l'objet du round-trip.
missing = [k for k in ("records", "games", "wdl", "contamination", "plycap",
                       "sign_convention", "couverture") if k not in rep]
if missing:
    raise SystemExit(f"fiche incomplete, cles absentes : {missing}")
if rep["records"] != expected:
    raise SystemExit(f"fiche: {rep['records']} records != {expected} attendus")
print(f"  records={rep['records']}  parties={rep['games']}")
print("  wdl : " + "  ".join(
    f"{k}={v['count']} ({100*v['share']:.2f} %)" for k, v in rep["wdl"].items()))
c = rep["contamination"]
print(f"  contamination : {c['positions']} ({100*c['share']:.2f} %)"
      f"  denominateur={c.get('denominator', '?')}")
p = rep["plycap"]
print(f"  ply-cap : {p['games']} parties ({100*p['game_share']:.2f} %),"
      f" {p['positions']} positions ({100*p['position_share']:.2f} %)")
print(f"  signe POV verifie sur {rep['sign_convention']['records_checked_without_tb_relabel']} records")
cov = rep["couverture"]
print(f"  couverture : {cov['visited_buckets']} buckets ({100*cov['coverage_fraction']:.3f} %)"
      f"  obs/parametre libre={cov['observations_per_free_parameter']:.2f}")
if egdir and "egdb" not in rep:
    raise SystemExit("EGDB fourni mais absent de la fiche")
if "egdb" in rep:
    e = rep["egdb"]
    print(f"  tablebase : in_range={e['in_range']}  desaccord={e['disagree']}"
          f" ({100*e['disagree_share']:.2f} %)  inversions={e['inverted']}")
if with_fisher and "fisher" not in rep:
    raise SystemExit("WITH_FISHER=1 mais aucun bloc fisher")
if "fisher" in rep:
    print(f"  fisher p(1-p) : moyenne={rep['fisher']['mean']:.6f}")
PY

stage report
say "L3_CORPUS_SIGNAL_REPORT_READY corpus=$CORPUS_LABEL promotion=false automatic_next_job=null"
: > "$ART/PROMOTION_AUTHORIZED__FALSE"
: > "$ART/AUTOMATIC_NEXT_JOB__NULL"
: > "$ART/VERDICT__L3_CORPUS_SIGNAL_REPORT_READY"
stage complete
