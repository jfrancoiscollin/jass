#!/usr/bin/env bash
# L3-PURE — axe VOLUME : fit du corpus 12 M produit par le préflight.
#
# Recette TURNOVER conservée : logistic WDL, color-fold, tempo-stage,
# L2=3e-5, warm-start TURNOVER, split par ouverture. Le seul facteur sous test
# est le VOLUME (12 M au lieu de 2 M) ; le ratio 67/33 et la profondeur d9 sont
# des écarts déclarés, hérités du certificat du préflight.
#
# Le corpus n'est pas re-généré : il est récupéré, authentifié par empreinte, et
# le split est REJOUÉ puis comparé au manifeste publié. L'optimiseur DOIT
# converger — un fit tronqué n'est pas un résultat faible, c'est un échec.
#
# Aucun verdict de promotion. Aucune continuation automatique.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"
: "${PREFLIGHT_PREFIX:?}"; : "${EXPECTED_PREFLIGHT_JOB:?}"
: "${TURNOVER_TRAIN_PREFIX:?}"; : "${EXPECTED_TURNOVER_TRAIN_JOB:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
IN="$JASS_RESULT_DIR/inputs"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART" "$IN" "$GEOM"
RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
STAGE="$W/stage.txt"
: > "$RES"
echo preflight > "$STAGE"

say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
phase(){ echo "$1" > "$STAGE"; say "phase=$1"; }
MON=""
monitor(){
  (
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        awk '/MemAvailable:/{printf "mem_available_mb=%d\n",$2/1024}' /proc/meminfo
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        # L-BFGS logge une ligne par itération : c'est la seule progression
        # observable d'un fit de plusieurs heures. Ne jamais tourner dans le
        # noir (leçon de home-1003).
        if [ -f "$W/fit.log" ]; then
          printf 'fit_lines=%s\n' "$(wc -l < "$W/fit.log")"
          tail -1 "$W/fit.log" 2>/dev/null | sed 's/^/fit_last=/'
        fi
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"
      cp "$PROG" "$ART/PROGRESS.txt"
      sleep 60
    done
  ) &
  MON="$!"
}
finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$W/test-build" "$W/venv" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

TOTAL_RECORDS=12000000
HOLDOUT_MOD=10
SPLIT_SEED=577215
# Recette du fit, parametree le 4 aout. Defauts = la recette de juillet a
# l'identique, donc home-1006 reproduit au bit pres. Motif : le verdict
# VOL8M (-14,95 Elo) a ete rendu sous CETTE recette, dont on a depuis mesure
# qu'elle vaut ~45 Elo de moins que celle du champion (fold exact, prior centre
# sur le parent, gtol 1e-4, l2 1e-5). Un corpus 6x plus dense juge par un fit
# mal specifie pour cause de famine de donnees ne tranche pas l'axe volume.
L2="${L2:-3e-5}"
MAXIT="${MAXIT:-1000}"
LBFGS_MAXCOR=20
LBFGS_GTOL="${LBFGS_GTOL:-1e-3}"
FOLD_FLAG="${FOLD_FLAG:---color-fold}"
# `warm` = warm-start depuis TURNOVER (juillet) ; `prior` = ridge centre sur le
# parent F2M, la recette du champion L2LOW. Le parent doit etre le MEME que
# celui de L2LOW, sinon la porte compare deux choses a la fois.
CONT_MODE="${CONT_MODE:-warm}"
PARENT_MODEL_SHA="be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
CHUNK=20000
FIT_TIMEOUT="${FIT_TIMEOUT:-36000}"
TURNOVER_MODEL_SHA="b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -ge 30000 ] ||
  die "need 30 GiB free"
[ "$(awk '/MemAvailable:/{print int($2/1024)}' /proc/meminfo)" -ge 4000 ] ||
  die "need 4 GiB available RAM"
monitor

phase fetch-and-authenticate-preflight
python3 jobs/tools/fetch_result_files.py --prefix "$PREFLIGHT_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=preflight.json \
  --file artefacts/vol8m.jnnw.gz=vol8m.jnnw.gz \
  --file artefacts/vol8m.jsm.gz=vol8m.jsm.gz \
  --file artefacts/vol8m-split.json=vol8m-split.json \
  --file artefacts/vol8m-coverage.json=vol8m-coverage.json \
  --out-dir "$IN" --report "$ART/verified-preflight.json" \
  > "$W/fetch-preflight.log" 2>&1
PARENT_FETCH=()
[ "$CONT_MODE" = prior ] && PARENT_FETCH=(--file work/parent-f2m.pjtw=parent.pjtw)
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_TRAIN_PREFIX" \
  ${PARENT_FETCH[@]+"${PARENT_FETCH[@]}"} \
  --file artefacts/turnover1to1.pjtw.gz=TURNOVER.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-turnover.json" \
  > "$W/fetch-turnover.log" 2>&1
for spec in "verified-preflight.json:$EXPECTED_PREFLIGHT_JOB" \
            "verified-turnover.json:$EXPECTED_TURNOVER_TRAIN_JOB"; do
  python3 - "$ART/${spec%%:*}" "${spec#*:}" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
if report.get("job_id") != sys.argv[2] or report.get("result_state") != "completed":
    raise SystemExit(f"{sys.argv[1]}: source identity/state mismatch")
PY
done
# Le certificat s'authentifie lui-même : verdict, autorisation, empreinte du
# corpus. Rien n'est ré-épinglé à la main dans ce job.
python3 - "$IN/preflight.json" "$IN/vol8m.jnnw.gz" "$TOTAL_RECORDS" <<'PY'
import hashlib
import json
import sys
cert = json.load(open(sys.argv[1]))
if cert.get("verdict") != "L3_PURE_VOLUME8M_PREFLIGHT_READY":
    raise SystemExit("preflight verdict mismatch")
if cert.get("train_authorized") is not True:
    raise SystemExit("preflight does not authorise the fit")
corpus = cert.get("corpus", {})
if corpus.get("total_records") != int(sys.argv[3]):
    raise SystemExit("record count drift")
got = hashlib.sha256(open(sys.argv[2], "rb").read()).hexdigest()
if got != corpus.get("data_sha256"):
    raise SystemExit("corpus hash drift")
PY
gunzip -c "$IN/vol8m.jnnw.gz" > "$W/vol8m.raw.jnnw"
gunzip -c "$IN/vol8m.jsm.gz"  > "$W/vol8m.raw.jsm"
gunzip -c "$IN/TURNOVER.pjtw.gz" > "$W/TURNOVER.pjtw"
CONT_ARGS=(--warm-start "$W/TURNOVER.pjtw")
if [ "$CONT_MODE" = prior ]; then
  cp "$IN/parent.pjtw" "$W/parent.pjtw"
  [ "$(sha256sum "$W/parent.pjtw" | awk '{print $1}')" = "$PARENT_MODEL_SHA" ] ||
    die "parent F2M hash drift"
  CONT_ARGS=(--prior-mean "$W/parent.pjtw" --prior-decay 0)
  say "  continuation : prior centre sur F2M (recette L2LOW)"
else
  say "  continuation : warm-start TURNOVER (recette juillet)"
fi
say "  fold=$FOLD_FLAG  l2=$L2  gtol=$LBFGS_GTOL  max_iter=$MAXIT"
[ "$(sha256sum "$W/TURNOVER.pjtw" | awk '{print $1}')" = "$TURNOVER_MODEL_SHA" ] ||
  die "TURNOVER model hash drift"
say "  corpus ✓ : $TOTAL_RECORDS records authentifiés par le certificat"

phase isolated-runtime-and-architecture-guard
python3 -m venv "$W/venv"
"$W/venv/bin/python" -m pip install --disable-pip-version-check \
  --only-binary=:all: numpy==1.26.4 scipy==1.14.1 > "$W/pip.log" 2>&1
for source in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp \
  src/movegen.cpp src/movegen.hpp; do
  git show "${EXPECTED_CODE_SHA}:$source" > "$source"
done
grep -q "g_emasks" src/scan_eval.cpp || die "8cf build lacks g_emasks"
grep -q "has_any_capture" src/search.cpp || die "search lacks capture guard"
grep -q "has_any_capture" src/movegen.cpp || die "movegen lacks capture guard"
grep -q "root_is_drawn" src/search.cpp || die "engine predates the drawn-root fix"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf \
  > "$W/gen-patterns.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" \
  -eq 4251528 ] || die "8cf geometry mismatch"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests > "$W/build.log" 2>&1
ctest --test-dir "$W/build" --output-on-failure > "$W/ctest.log" 2>&1
J="$W/build/jass"
[ "$("$J" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "king-capture witness failed"
say "  runtime ✓ : 8cf, garde-fou archi vert, correctif racine-nulle présent"

phase reproduce-split-by-opening
python3 tools/selfplay_frontier.py split \
  --data "$W/vol8m.raw.jnnw" --meta "$W/vol8m.raw.jsm" \
  --out-data "$W/vol8m.fit.jnnw" --out-meta "$W/vol8m.fit.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$W/vol8m-split-here.json" > "$W/split.log" 2>&1
python3 - "$W/vol8m-split-here.json" "$IN/vol8m-split.json" <<'PY'
import json
import sys
here, there = (json.load(open(p)) for p in sys.argv[1:3])
if here != there:
    raise SystemExit("split manifest drift against the preflight")
PY
cp "$IN/vol8m-split.json" "$ART/vol8m-split.json"
HOLDOUT="$("$W/venv/bin/python" -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["holdout_records"])' \
  "$ART/vol8m-split.json")"
[ "$HOLDOUT" -gt 0 ] || die "holdout missing"
say "  split ✓ rejoué à l'identique, holdout = $HOLDOUT records"

phase full-feature-dump-and-converged-fit
"$J" --dump-eval-features "$W/vol8m.fit.jnnw" "$W/vol8m.feat" \
  > "$W/features.log" 2>&1
set +e
# PYTHONUNBUFFERED : cpx62-1167 a brule 4h30 et rendu un log de 0 octet parce
# que la sortie etait bufferisee et que SIGTERM ne flushe pas. Un fit de cette
# longueur DOIT dire ou il en est s'il est tue.
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
  PYTHONUNBUFFERED=1 \
  timeout "$FIT_TIMEOUT" \
  "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
  --data "$W/vol8m.fit.jnnw" --feat "$W/vol8m.feat" \
  --out "$W/vol8m.pjtw" \
  --target wdl --loss logistic "$FOLD_FLAG" --tempo-stage \
  "${CONT_ARGS[@]}" --holdout-count "$HOLDOUT" \
  --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
  --lbfgs-maxcor "$LBFGS_MAXCOR" --lbfgs-gtol "$LBFGS_GTOL" \
  --optimizer-report "$ART/vol8m-optimizer.json" \
  > "$W/fit.log" 2>&1
FIT_RC=$?
set -e
# Le checkpoint part à l'object store AVANT tout verdict : un fit de plusieurs
# heures ne doit jamais être perdu parce que l'étape d'après échoue.
if [ -s "$W/vol8m.pjtw" ]; then
  gzip -n -c "$W/vol8m.pjtw" > "$ART/vol8m-checkpoint.pjtw.gz"
fi
[ "$FIT_RC" -eq 0 ] || die "fit failed rc=$FIT_RC; checkpoint preserved"
[ -s "$W/vol8m.pjtw" ] || die "model missing"
grep -q 'HOLDOUT_LOGLOSS' "$W/fit.log" || die "holdout result missing"
"$W/venv/bin/python" - "$ART/vol8m-optimizer.json" <<'PY' ||
import json
import sys
if not json.load(open(sys.argv[1])).get("success"):
    raise SystemExit(1)
PY
  die "optimiser did not converge — a truncated fit is a failure, not a weak result"
cp "$ART/vol8m-checkpoint.pjtw.gz" "$ART/vol8m.pjtw.gz"
say "  fit ✓ convergé"

phase publish-training-screen
"$W/venv/bin/python" - "$W" "$ART" "$IN/preflight.json" "$EXPECTED_CODE_SHA" \
  "$TOTAL_RECORDS" "$L2" <<'PY'
import hashlib
import json
import pathlib
import re
import sys

w, art = map(pathlib.Path, sys.argv[1:3])
cert = json.load(open(sys.argv[3]))
code_sha, total, l2 = sys.argv[4], int(sys.argv[5]), sys.argv[6]

fit_log = (w / "fit.log").read_text(errors="replace")
m = re.search(r"HOLDOUT_LOGLOSS[ =:]+([0-9.]+)", fit_log)
holdout_loss = float(m.group(1)) if m else None
opt = json.load(open(art / "vol8m-optimizer.json"))
cov = json.load(open(sys.argv[3]))["coverage"]

payload = {
    "schema": 1,
    "verdict": "L3_PURE_VOLUME8M_FIT_CONVERGED",
    "code_sha": code_sha,
    "model": {
        "name": "VOL8M",
        "sha256": hashlib.sha256(
            (w / "vol8m.pjtw").read_bytes()).hexdigest(),
        "geometry": "8cf",
        "parent": "TURNOVER (warm start)",
    },
    "training": {
        "records": total,
        "l2": l2,
        "iterations": opt.get("nit"),
        "converged": opt.get("success"),
        "holdout_logloss": holdout_loss,
        "turnover_reference_holdout_logloss": 0.444060,
    },
    "coverage_from_preflight": cov,
    "corpus_deviations": cert.get(
        "declared_deviations_from_the_turnover_recipe", []),
    # Rappel explicite : trois confirmations dans ce projet que la loss holdout
    # ne prédit PAS la force. Elle est publiée comme diagnostic, jamais comme
    # critère de sélection.
    "holdout_loss_is_a_diagnostic_not_a_selection_criterion": True,
    "promotion_authorized": False,
    "automatic_next_job": None,
}
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
(art / "JASS_CONTROL_SUMMARY.json").write_text(serialized)
(art / "VERDICT__L3_PURE_VOLUME8M_FIT_CONVERGED").write_text(
    "L3_PURE_VOLUME8M_FIT_CONVERGED\n")
(art / "PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")
print(f"  itérations : {opt.get('nit')}  convergé : {opt.get('success')}")
print(f"  holdout logloss : {holdout_loss} (TURNOVER : 0,444060)")
print(f"  couverture : {cov.get('visited_pct')} % , "
      f"{cov.get('observations_per_free_parameter')} obs/paramètre")
PY
phase complete
say "L3_PURE_VOLUME8M_FIT_CONVERGED promotion=false automatic_next_job=null"
