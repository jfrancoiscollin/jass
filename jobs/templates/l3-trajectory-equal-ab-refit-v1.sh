#!/usr/bin/env bash
# L3 — TRAJ-EQUAL, M3 : poids uniforme par record contre masse égale par partie.
#
# Les deux fits lisent le MEME JNNW, le MEME JSM2, le MEME dump FEAT et le
# MEME split. Le traitement GAME donne à chaque game_id TRAIN une masse totale
# identique ; le contrôle ROW conserve le poids historique uniforme par ligne.
#
# Aucune promotion. La porte GAME vs ROW est un job séparé.
# Sizing HOME : <=7h40, ancré sur home-1314 (double fit 2 M : 7h36m28).
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${POOL_PREFIX:?}"; : "${POOL_JOB:?}"
: "${PARENT_PREFIX:?}"; : "${PARENT_JOB:?}"; : "${EXPECTED_PARENT_MODEL_SHA256:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"; mkdir -p "$W" "$IN" "$ART" "$GEOM"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: > "$RES"; : > "$PROG"; echo start > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "phase=$1"; }

TARGET_RECORDS="${TARGET_RECORDS:-2000000}"
SUBSAMPLE_SEED="${SUBSAMPLE_SEED:-3141592}"
SPLIT_SEED="${SPLIT_SEED:-577215}"
HOLDOUT_MOD="${HOLDOUT_MOD:-10}"
EXPECTED_EXTRAS="${EXPECTED_EXTRAS:-120}"
FOLD_FLAG="${FOLD_FLAG:---exact-fold}"
L2="${L2:-1e-5}"; LBFGS_GTOL="${LBFGS_GTOL:-1e-4}"
MAXIT="${MAXIT:-4000}"; CHUNK="${CHUNK:-20000}"; LBFGS_MAXCOR=20
FIT_TIMEOUT="${FIT_TIMEOUT:-21600}"
NUMERIC_STACK="${NUMERIC_STACK:-current}"
case "$NUMERIC_STACK" in historical|current) ;; *)
  die "NUMERIC_STACK doit être historical ou current (reçu: $NUMERIC_STACK)" ;; esac
# Raw GAME weights are 1 / retained records in the TRAIN game. A 260-ply game
# sampled at every ply would still be above 1/512; 1e-4 is a generous guard,
# never a clipping threshold. HOLDOUT rows are neutral at 1.
WEIGHT_MIN="${WEIGHT_MIN:-0.0001}"; WEIGHT_MAX="${WEIGHT_MAX:-1.0}"

MON=""
monitor(){ ( t0=$(date +%s); while true; do
    { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
      printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
      printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
      printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
      for a in row game; do [ -f "$W/fit-$a.log" ] &&
        printf '%s_fit_lines=%s\n' "$a" "$(wc -l < "$W/fit-$a.log")"; done
    } > "$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120
  done ) & MON="$!"; }
restore_src(){ git checkout -- src/ pattern_jass/ 2>/dev/null || true; }
pin_arch_src(){
  local f tmp
  for f in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/movegen.cpp src/movegen.hpp; do
    tmp="$W/$(basename "$f").pinned"
    git show "$EXPECTED_CODE_SHA:$f" > "$tmp" || { restore_src; die "source épinglée absente: $f"; }
    mv "$tmp" "$f"
  done
}
arch_assert(){
  grep -q "g_emasks"        src/scan_eval.cpp || { restore_src; die "archi: scan_eval sans g_emasks"; }
  grep -q "has_any_capture" src/search.cpp    || { restore_src; die "archi: search sans has_any_capture"; }
  grep -q "has_any_capture" src/movegen.cpp   || { restore_src; die "archi: movegen sans has_any_capture"; }
  grep -q "root_is_drawn"   src/search.cpp    || { restore_src; die "engine avant correctif racine nulle"; }
  say "  sources critiques épinglées à ${EXPECTED_CODE_SHA:0:12}, gardes architecture ✓"
}
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt"; [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W"/build* "$W/venv" "$IN" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat "$W"/*.npy 2>/dev/null || true
  exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"

stage disk-guard
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 15000 ] || die "moins de 15 Go libres (${DFA} Mo)"
NCPU=$(nproc); say "  nproc=$NCPU libre=${DFA}Mo"
PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-540}"
source jobs/lib/preflight.sh
{ preflight_note "double fit 2 M, ancre HOME home-1314" 460
  preflight_check; } | tee -a "$RES"
monitor

stage fetch-inputs
python3 jobs/tools/fetch_result_files.py --prefix "$POOL_PREFIX" \
  --file artefacts/vol8m.jnnw.gz=pool.jnnw.gz \
  --file artefacts/vol8m.jsm.gz=pool.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-pool.json" --expected-state completed \
  > "$W/fetch-pool.log" 2>&1 || die "fetch du pool en échec"
python3 - "$ART/verified-pool.json" "$POOL_JOB" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
if r.get("job_id") != sys.argv[2] or r.get("result_state") != "completed":
    raise SystemExit("identité/état du pool non conforme")
PY
python3 jobs/tools/fetch_result_files.py --prefix "$PARENT_PREFIX" \
  --file work/parent-f2m.pjtw=parent.pjtw \
  --out-dir "$IN" --report "$ART/verified-parent.json" --expected-state completed \
  > "$W/fetch-parent.log" 2>&1 || die "fetch du parent en échec"
python3 - "$ART/verified-parent.json" "$PARENT_JOB" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
if r.get("job_id") != sys.argv[2] or r.get("result_state") != "completed":
    raise SystemExit("identité/état du parent non conforme")
PY
[ "$(sha256sum "$IN/parent.pjtw" | awk '{print $1}')" = "$EXPECTED_PARENT_MODEL_SHA256" ] ||
  die "hash du parent non conforme"
gunzip -c "$IN/pool.jnnw.gz" > "$W/pool.jnnw"
gunzip -c "$IN/pool.jsm.gz"  > "$W/pool.jsm"
[ "$(head -c4 "$W/pool.jsm")" = "JSM2" ] || die "pool sans contexte JSM2"
say "  pool JSM2 ✓ + parent ✓ hash conforme"

stage retain-and-split
python3 tools/selfplay_frontier.py mix \
  --source POOL "$W/pool.jnnw" "$W/pool.jsm" 1 \
  --target-records "$TARGET_RECORDS" --seed "$SUBSAMPLE_SEED" \
  --out-data "$W/sub.jnnw" --out-meta "$W/sub.jsm" \
  --manifest "$ART/subsample.json" > "$W/mix.log" 2>&1 || die "sous-échantillonnage en échec"
python3 tools/selfplay_frontier.py split \
  --data "$W/sub.jnnw" --meta "$W/sub.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --out-data "$W/corpus.jnnw" --out-meta "$W/corpus.jsm" \
  --manifest "$ART/split.json" > "$W/split.log" 2>&1 || die "split en échec"
RECORDS=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["records"])' "$ART/split.json")
HOLDOUT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["holdout_records"])' "$ART/split.json")
[ "$RECORDS" = "$TARGET_RECORDS" ] || die "records=$RECORDS attendu $TARGET_RECORDS"
[ "${HOLDOUT:-0}" -gt 0 ] && [ "$HOLDOUT" -lt "$RECORDS" ] || die "holdout invalide"
say "  corpus commun ✓ : $RECORDS records, holdout $HOLDOUT par ouverture"

stage build-engine
pin_arch_src
arch_assert
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1 ||
  { restore_src; die "génération 8cf en échec"; }
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] ||
  { restore_src; die "8cf mismatch"; }
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$(mem_safe_jobs)" --target jass > "$W/build.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || { restore_src; die "build sans binaire"; }
restore_src
say "  8cf ✓ TOTAL_BUCKETS=4251528, gardes architecture ✓"

stage python-runtime
python3 -m venv "$W/venv"
pip_hist(){ "$W/venv/bin/python" -m pip install --disable-pip-version-check \
  --only-binary=:all: numpy==1.26.4 scipy==1.14.1 >> "$W/pip.log" 2>&1; }
pip_curr(){ "$W/venv/bin/python" -m pip install --disable-pip-version-check \
  --only-binary=:all: numpy scipy >> "$W/pip.log" 2>&1; }
: > "$W/pip.log"
case "$NUMERIC_STACK" in
  historical) pip_hist || die "pile historical exigée mais indisponible — voir pip.log"
              PINSTACK=historical ;;
  current)    pip_curr || die "pile current exigée mais indisponible — voir pip.log"
              PINSTACK=current ;;
esac
[ "$PINSTACK" = "$NUMERIC_STACK" ] || die "pile résolue $PINSTACK != $NUMERIC_STACK exigée"
NPV=$("$W/venv/bin/python" -c 'import numpy,scipy;print(numpy.__version__,scipy.__version__)')
say "  pile numérique : $PINSTACK (numpy/scipy $NPV) — partagée"
printf '{"stack":"%s","numpy_scipy":"%s"}\n' "$PINSTACK" "$NPV" > "$ART/numeric-stack.json"

stage dump-shared-features
"$J" --dump-eval-features "$W/corpus.jnnw" "$W/corpus.feat" > "$W/features.log" 2>&1 ||
  die "dump-eval-features en échec"
K=$(python3 -c 'import struct,sys;f=open(sys.argv[1],"rb");assert f.read(4)==b"FEAT";print(struct.unpack("<II",f.read(8))[1])' "$W/corpus.feat")
[ "$K" = "$EXPECTED_EXTRAS" ] || die "extras K=$K attendu $EXPECTED_EXTRAS"
say "  dump FEAT partagé ✓ K=$K"

stage trajectory-report-and-weights
env PYTHONPATH="tools" PYTHONUNBUFFERED=1 "$W/venv/bin/python" \
  jobs/tools/l3_trajectory_equal_weights.py \
    --data "$W/corpus.jnnw" --meta "$W/corpus.jsm" --holdout-count "$HOLDOUT" \
    --out-row-weights "$W/row-weights.npy" --out-game-weights "$W/game-weights.npy" \
    --out-report "$ART/trajectory-report.json" \
    > "$W/trajectory.log" 2>&1 || die "construction des poids trajectoire en échec"
[ -s "$W/row-weights.npy" ] && [ -s "$W/game-weights.npy" ] &&
  [ -s "$ART/trajectory-report.json" ] || die "poids/rapport absents"
python3 - "$ART/trajectory-report.json" "$RECORDS" "$HOLDOUT" "$WEIGHT_MIN" "$WEIGHT_MAX" <<'PY' | tee -a "$RES"
import json, sys
r = json.load(open(sys.argv[1]))
records, holdout = int(sys.argv[2]), int(sys.argv[3])
lo, hi = float(sys.argv[4]), float(sys.argv[5])
s, t = r["split"], r["trajectory_equal_treatment"]
if r.get("schema") != 1 or r.get("operation") != "l3_trajectory_equal_weights":
    raise SystemExit("schéma de rapport trajectoire inattendu")
if s["records"] != records or s["holdout_records"] != holdout:
    raise SystemExit("comptes du rapport trajectoire incohérents")
if s["games_crossing_boundary"] or s["openings_crossing_boundary"]:
    raise SystemExit("groupe traversant la frontière train/holdout")
if r["alignment"]["records_pov_checked_without_tb_relabel"] != records:
    raise SystemExit("alignement JNNW/JSM2 non vérifié sur tous les records")
if not (lo <= t["raw_train_weight_min"] <= t["raw_train_weight_max"] <= hi):
    raise SystemExit(f"poids bruts hors garde [{lo},{hi}]")
if abs(t["normalized_train_weight_mean"] - 1.0) > 1e-12:
    raise SystemExit("moyenne normalisée != 1")
s0 = r["row_equal_control"]["retained_train_records_per_game"]
print(f"  parties TRAIN={s['train_games']:,}, ouvertures={s['train_openings']:,}")
print(f"  alignement POV JNNW/JSM2 vérifié sur {records:,} records")
print(f"  records/partie retenus : moyenne={s0['mean']:.3f} médiane={s0['quantiles']['p50']:.3f} max={s0['max']}")
print(f"  10 % parties les plus longues : {100*r['row_equal_control']['longest_10_percent_games_record_share']:.2f} % de la loss ROW")
print(f"  poids GAME bruts=[{t['raw_train_weight_min']:.6f},{t['raw_train_weight_max']:.6f}] facteur={t['normalization_factor']:.6f}")
print(f"  masse/partie={t['equal_total_mass_per_game']:.6f} erreur_max={t['max_abs_game_mass_error']:.3e}")
PY

fit_arm(){  # $1 = row|game
  local arm="$1"; shift
  stage "fit-$arm"
  set +e
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" PYTHONUNBUFFERED=1 \
    timeout "$FIT_TIMEOUT" "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
      --data "$W/corpus.jnnw" --feat "$W/corpus.feat" --out "$W/$arm.pjtw" \
      --target wdl --loss logistic "$FOLD_FLAG" --tempo-stage \
      --prior-mean "$IN/parent.pjtw" --prior-decay 0 \
      --holdout-count "$HOLDOUT" --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
      --lbfgs-maxcor "$LBFGS_MAXCOR" --lbfgs-gtol "$LBFGS_GTOL" --prune \
      "$@" --optimizer-report "$ART/$arm-optimizer.json" \
      > "$W/fit-$arm.log" 2> "$W/fit-$arm-time.log"
  local rc=$?
  set -e
  [ "$rc" -eq 0 ] || die "fit $arm rc=$rc — voir fit-$arm.log"
  [ -s "$W/$arm.pjtw" ] || die "fit $arm sans modèle"
  # ALLOW_NON_PGTOL_STOP (défaut 0, donc aucun job existant ne change) dégrade
  # l'arrêt non-gradient en AVERTISSEMENT CONSIGNÉ au lieu de tuer le job.
  # Motif : home-1317 a perdu 9h55 ET les deux modèles parce que le bras `game`
  # n'a pas convergé. Or « le bras game ne converge pas en N itérations » EST un
  # résultat — mais seulement si on garde le modèle et le compte d'itérations
  # pour le lire. `success=False` reste FATAL dans tous les cas.
  # ⚠️ Tolérer l'arrêt N'AUTORISE PAS à gater un bras sous-convergé contre un
  # bras convergé : ce serait une cellule à deux facteurs (cf. la leçon
  # PRIORTIGHT). La porte est un job séparé, décidé après lecture.
  local stopchk; stopchk=0
  python3 - "$ART/$arm-optimizer.json" "$arm" <<'PYCHK' || stopchk=$?
import json, sys
d = json.load(open(sys.argv[1]))
if not d.get("success"):
    raise SystemExit(2)                       # 2 = fatal partout
if "PGTOL" not in str(d.get("message", "")).upper():
    print(f"{sys.argv[2]}: arrêt sur {d.get('message')!r}, pas PGTOL")
    raise SystemExit(3)                       # 3 = tolérable si opt-in
PYCHK
  case "$stopchk" in
    0) ;;
    3) if [ "${ALLOW_NON_PGTOL_STOP:-0}" = "1" ]; then
         say "  ⚠️ $arm : arrêt NON-gradient TOLÉRÉ (ALLOW_NON_PGTOL_STOP=1) — bras SOUS-CONVERGÉ, ne pas gater tel quel"
       else die "fit $arm : arrêt non concluant"; fi ;;
    *) die "fit $arm : arrêt non concluant (success=False)" ;;
  esac
  gzip -n -c "$W/$arm.pjtw" > "$ART/$arm.pjtw.gz"
  local ll it
  ll=$(grep -o 'HOLDOUT_LOGLOSS[= ][0-9.]*' "$W/fit-$arm.log" | tail -1)
  it=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["iterations"])' "$ART/$arm-optimizer.json")
  if [ "$stopchk" = 3 ]; then
    say "  $arm : SOUS-CONVERGÉ (arrêt non-gradient), $it itérations, ${ll:-holdout n/a}"
  else say "  $arm : convergé, $it itérations, ${ll:-holdout n/a}"; fi
}

say "  facteur unique : ROW poids 1 ; GAME poids 1/m_g, moyenne TRAIN renormalisée à 1"
say "  recette commune : $FOLD_FLAG, prior parent, decay 0, gtol $LBFGS_GTOL, l2 $L2"
fit_arm row \
  --sample-weights "$W/row-weights.npy" \
  --weight-normalization mean-train-1 \
  --weight-min "$WEIGHT_MIN" --weight-max "$WEIGHT_MAX" \
  --weights-report "$ART/row-trainer-weights.json"
fit_arm game \
  --sample-weights "$W/game-weights.npy" \
  --weight-normalization mean-train-1 \
  --weight-min "$WEIGHT_MIN" --weight-max "$WEIGHT_MAX" \
  --weights-report "$ART/game-trainer-weights.json"

stage verify-single-factor-output
cmp -s "$W/row.pjtw" "$W/game.pjtw" &&
  die "modèles byte-identiques — la pondération n'a rien changé au fit"
python3 - "$ART/trajectory-report.json" "$ART/row-trainer-weights.json" \
  "$ART/game-trainer-weights.json" <<'PY' | tee -a "$RES"
import json, sys
a, row, game = (json.load(open(path)) for path in sys.argv[1:])
if a["output"]["row_weights"]["sha256"] != row["source"]["sha256"]:
    raise SystemExit("le trainer ROW n'a pas lu son vecteur authentifié")
if a["output"]["game_weights"]["sha256"] != game["source"]["sha256"]:
    raise SystemExit("le trainer GAME n'a pas lu son vecteur authentifié")
if row["split"]["holdout_weighted"] or game["split"]["holdout_weighted"]:
    raise SystemExit("le holdout a été pondéré")
for name, payload in (("ROW", row), ("GAME", game)):
    if abs(payload["normalization"]["normalized_train_mean"] - 1.0) > 1e-12:
        raise SystemExit(f"normalisation {name} incohérente")
if not row["optimizer"]["uniform_after_normalization"] or row["optimizer"]["sw_all_used"]:
    raise SystemExit("ROW n'a pas reproduit le chemin historique non pondéré")
if game["optimizer"]["uniform_after_normalization"] or not game["optimizer"]["sw_all_used"]:
    raise SystemExit("GAME n'a pas activé la pondération non uniforme")
print("  facteur prouvé : vecteurs ROW/GAME authentifiés, ROW legacy exact, holdout non pondéré")
PY

stage report
say "L3_TRAJECTORY_EQUAL_AB_REFIT_READY records=$RECORDS promotion=false automatic_next_job=null"
: > "$ART/PROMOTION_AUTHORIZED__FALSE"
: > "$ART/AUTOMATIC_NEXT_JOB__NULL"
: > "$ART/VERDICT__L3_TRAJECTORY_EQUAL_AB_REFIT_READY"
stage complete
