#!/usr/bin/env bash
# L3 — atlas de points aveugles jugé par Scan, paramétré par modèle/géométrie.
#
# `home-1002` a établi que le résidu contre Scan est de la MARGE D'ÉVALUATION,
# pas de la vitesse. Ce qu'on n'a jamais su, c'est *sur quelles positions* elle
# se perd. Ce job le mesure : à chaque coup où Jass est au trait, Scan choisit
# depuis la même position ; en cas de désaccord Scan juge les deux enfants, et
# le coût est la différence de valeur du point de vue du joueur au trait.
#
# ⚠️ SIZING PAR BUDGET DE TEMPS, PAS PAR VOLUME. Le débit du collecteur sur
# cpx62 n'a jamais été mesuré, et transporter une ancre d'une box à l'autre est
# exactement la bourde 0665. Plutôt que de deviner un volume et de découvrir
# l'ETA après coup, chaque shard tourne `--time-budget-s` et s'arrête proprement
# en gardant ce qu'il a écrit : **la durée est le paramètre, le volume est le
# résultat**. L'agrégateur refuse déjà de classer un bucket sous son plancher,
# donc un rendement plus faible que prévu rend un atlas plus court, jamais un
# atlas faux.
#
# Deux valeurs seulement sont recevables :
#
#   --variant exact   champion EXACT, binaire 8cf
#   --variant gen2    témoin historique Gen2, binaire 32cf
#
# Les deux invocations gardent le même protocole Scan et les mêmes 120 extras.
# Le readout différentiel refuse toute dérive sur les autres dimensions.
# Aucun modèle entraîné, aucune porte, aucune promotion. Scan est JUGE.
set -Eeuo pipefail

usage(){ echo "usage: $0 --variant {exact|gen2}" >&2; exit 2; }
ATLAS_VARIANT=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --variant) [ "$#" -ge 2 ] || usage; ATLAS_VARIANT="$2"; shift 2 ;;
    --variant=*) ATLAS_VARIANT="${1#*=}"; shift ;;
    *) usage ;;
  esac
done
case "$ATLAS_VARIANT" in
  exact)
    MODEL_LABEL=EXACT
    PATTERN_VARIANT=8cf
    EXPECTED_NUM_PATTERNS=8
    EXPECTED_N_PAT=$((531441 * 8))
    ;;
  gen2)
    MODEL_LABEL=GEN2
    PATTERN_VARIANT=v4
    EXPECTED_NUM_PATTERNS=32
    EXPECTED_N_PAT=$((531441 * 32))
    ;;
  *) usage ;;
esac

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${SCAN_BIN:?}"; : "${EXPECTED_SCAN_SHA256:?}"; : "${EXPECTED_SCAN_EVAL_SHA256:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
IN="$JASS_RESULT_DIR/inputs"
ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
# Hors de l'arbre git : le runner resynchronise l'arbre à chaque tick et
# clobberait un RESULTS écrit dans le repo (règle 8ter).
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: > "$RES"; : > "$PROG"; echo start > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "phase=$1"; }

EXACT_REFIT_PREFIX="${EXACT_REFIT_PREFIX:-r2:jass-data/runs/cpx62-1117-l3-exact-fold-refit-v1/20260731T235446Z-970f14de}"
EXPECTED_EXACT_REFIT_JOB="${EXPECTED_EXACT_REFIT_JOB:-cpx62-1117-l3-exact-fold-refit-v1}"
EXACT_MODEL_SHA="d84a7fc7c3127d135d3cc150406055b9506daaa881af2959cd3721f6be66eb0a"
GEN2_INPUT_PREFIX="${GEN2_INPUT_PREFIX:-${JASS_OBJSTORE_REMOTE%/}/inputs/t1bis-adj-g1/v1}"
GEN2_GZ_SHA="01cc3ea59e9cc3ced1910d4d9054f88f92c1c4d9d220d5f28b0ebaaad33681a0"

BUDGET_S="${BUDGET_S:-1500}"          # budget par shard (25 min par défaut)
PLAY_DEPTH="${PLAY_DEPTH:-8}"
JUDGE_DEPTH="${JUDGE_DEPTH:-10}"
MAX_PLIES="${MAX_PLIES:-160}"
GAMES_CAP="${GAMES_CAP:-100000}"      # jamais atteint : le budget tranche avant
MIN_POSITIONS="${MIN_POSITIONS:-200}" # plancher de classement d'un bucket

MON=""
monitor(){
  ( t0=$(date +%s)
    while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        # Somme des compteurs des shards : chaque collecteur écrit son propre
        # progress JSON, donc le rythme est LIVE et pas reconstruit après coup.
        python3 - "$W" <<'PY' 2>/dev/null || true
import glob, json, sys
g = p = d = j = 0
for f in glob.glob(sys.argv[1] + "/prog-s*.json"):
    try: r = json.load(open(f))
    except Exception: continue
    g += r.get("games_played", 0); p += r.get("positions", 0)
    d += r.get("disagreements", 0); j += r.get("judged", 0)
print(f"games={g}\npositions={p}\ndisagreements={d}\njudged={j}")
if p: print(f"disagreement_rate={d/p:.4f}")
PY
        # `ls` sur un motif sans correspondance sort en 2 et, sous `set -e`,
        # déclenche le trap ERR : 1114 a écrit six « ABORT line=72 » dans un
        # RESULTS de job RÉUSSI. Un abort mensonger dans un fichier de résultats
        # est pire qu'un compteur manquant — `find` ne peut pas échouer ainsi.
        printf 'shards_finished=%s\n' "$(find "$W" -maxdepth 1 -name 'done-s*' 2>/dev/null | wc -l)"
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 300
    done ) &
  MON="$!"
}
restore_src(){ git checkout -- src/ pattern_jass/ 2>/dev/null || true; }
finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" 2>/dev/null || true
  exit "$rc"
}
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
[ "${DFA:-0}" -gt 3000 ] || die "moins de 3 Go libres (${DFA} Mo)"
NCPU=$(nproc)
SHARDS="${SHARDS:-$NCPU}"
say "  nproc=$NCPU shards=$SHARDS libre=${DFA}Mo"

stage verify-pinned-scan-runtime
[ -x "$SCAN_BIN" ] || die "binaire Scan absent : $SCAN_BIN (cf cpx62-1112)"
[ "$(sha256sum "$SCAN_BIN" | awk '{print $1}')" = "$EXPECTED_SCAN_SHA256" ] ||
  die "hash du binaire Scan différent de l'épinglage"
SCAN_DIR="$(dirname "$(readlink -f "$SCAN_BIN")")"
[ "$(sha256sum "$SCAN_DIR/data/eval" | awk '{print $1}')" = "$EXPECTED_SCAN_EVAL_SHA256" ] ||
  die "hash de data/eval différent de l'épinglage"
say "  runtime Scan ✓ conforme à l'épinglage"

stage build
# Garde-fou archi (règle 11) : tirer explicitement de la SHA ÉPINGLÉE, jamais
# d'une ref mobile — `origin/develop` bouge sous les pieds d'un job en vol.
for f in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/movegen.cpp src/movegen.hpp; do
  git show "$EXPECTED_CODE_SHA:$f" > "$f" || die "cannot pull $f from $EXPECTED_CODE_SHA"
done
grep -q "g_emasks"        src/scan_eval.cpp || { restore_src; die "archi: scan_eval sans g_emasks"; }
grep -q "has_any_capture" src/search.cpp    || { restore_src; die "archi: search sans has_any_capture"; }
grep -q "has_any_capture" src/movegen.cpp   || { restore_src; die "archi: movegen sans has_any_capture"; }
grep -q "root_is_drawn"   src/search.cpp    || { restore_src; die "engine predates the drawn-root fix"; }
grep -q "warm_kings_endgame_bitbases" src/hub.cpp ||
  { restore_src; die "engine predates the movetime endgame bake (16f8c151)"; }
say "  garde-fou archi ✓"

# ⚠️ GÉOMÉTRIE DU PATTERN — la marche sur laquelle cpx62-1113 est tombé.
# Le build 32cf est le même que dans `l3-succession-guards-v1.sh` : `v4` produit
# 32 patterns. Le bras EXACT demande explicitement `8cf`. Le choix vient
# UNIQUEMENT de `--variant`, puis le header du modèle le vérifie après fetch.
python3 pattern_jass/tools/gen_patterns.py --emit --variant "$PATTERN_VARIANT" \
  > "$W/gen-patterns.log" 2>&1 ||
  { restore_src; die "génération des patterns $PATTERN_VARIANT en échec"; }
grep -Eq "NUM_PATTERNS[[:space:]]*=[[:space:]]*$EXPECTED_NUM_PATTERNS;" \
  pattern_jass/src/pattern.hpp ||
  { restore_src; die "pattern.hpp n'est pas en $EXPECTED_NUM_PATTERNS patterns"; }
say "  patterns $PATTERN_VARIANT régénérés ✓ (TOTAL_BUCKETS = 531441×$EXPECTED_NUM_PATTERNS)"

# Mêmes extras que les portes de la campagne : ENDGAME_FEATURES(110) + KING_
# MOBILITY(+4) + SCAN_PARITY(+6) = 120, exactement le `n_ext` des .pjtw L3.
# TEMPO_STAGE change le mélange de phase, donc l'éval elle-même.
# EGDB reste OFF, délibérément : Scan tourne à `bb-size=0`, et donner une base
# de finales au seul Jass ferait mesurer « nous avons une table » au lieu de
# « notre éval juge bien », précisément dans les buckets de finale que l'atlas
# est censé éclairer.
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass > "$W/build.log" 2>&1
JASS="$W/build/jass"
[ -x "$JASS" ] || die "build sans binaire"
restore_src

stage fetch-model
if [ "$ATLAS_VARIANT" = exact ]; then
  python3 jobs/tools/fetch_result_files.py --prefix "$EXACT_REFIT_PREFIX" \
    --file artefacts/exact.pjtw.gz=MODEL.pjtw.gz \
    --out-dir "$IN" --report "$ART/verified-model.json" \
    --expected-state completed > "$W/fetch-model.log" 2>&1 ||
    die "fetch du champion EXACT en échec"
  python3 - "$ART/verified-model.json" "$EXPECTED_EXACT_REFIT_JOB" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
if r.get("job_id") != sys.argv[2] or r.get("result_state") != "completed":
    raise SystemExit("EXACT source identity/state mismatch")
PY
  MODEL_SOURCE_PREFIX="$EXACT_REFIT_PREFIX"
  EXPECTED_MODEL_JOB="$EXPECTED_EXACT_REFIT_JOB"
else
  # Réutilise le bundle figé et vérifié qui sert déjà Gen2 aux gardes de
  # succession. Il télécharge plus que le seul modèle, mais protège manifeste,
  # inventaire, checksums et identité de source sans nouveau chemin ad hoc.
  python3 jobs/tools/fetch_t1bis_inputs.py --remote-prefix "$GEN2_INPUT_PREFIX" \
    --out-dir "$IN" --report "$ART/verified-model.json" \
    > "$W/fetch-model.log" 2>&1 || die "fetch du témoin Gen2 en échec"
  cp "$IN/gen2.pjtw.gz" "$IN/MODEL.pjtw.gz"
  [ "$(sha256sum "$IN/MODEL.pjtw.gz" | awk '{print $1}')" = "$GEN2_GZ_SHA" ] ||
    die "Gen2 gzip hash drift"
  MODEL_SOURCE_PREFIX="$GEN2_INPUT_PREFIX"
  EXPECTED_MODEL_JOB="frozen-t1bis-gen2"
fi
gunzip -c "$IN/MODEL.pjtw.gz" > "$W/MODEL.pjtw"
MODEL_SHA="$(sha256sum "$W/MODEL.pjtw" | awk '{print $1}')"
MODEL_GZ_SHA="$(sha256sum "$IN/MODEL.pjtw.gz" | awk '{print $1}')"
if [ "$ATLAS_VARIANT" = exact ] && [ "$MODEL_SHA" != "$EXACT_MODEL_SHA" ]; then
  die "EXACT model hash drift"
fi

# Le modèle et le binaire doivent décrire la géométrie demandée, et les extras
# doivent être strictement identiques. C'est le contrat scientifique du témoin :
# n_ext=120 des deux côtés, seul n_pat passe de 8cf à 32cf.
python3 - "$W/MODEL.pjtw" "$EXPECTED_N_PAT" "$MODEL_LABEL" <<'PY' | tee -a "$RES"
import os, struct, sys
path, want, label = sys.argv[1], int(sys.argv[2]), sys.argv[3]
with open(path, "rb") as fh:
    magic, version, scale, n_pat, n_ext = struct.unpack("<5I", fh.read(20))
if magic != 0x57544A50 or (version & 0xFF) != 3:
    raise SystemExit(f"{label}: header PJTW non supporté")
if n_pat != want:
    raise SystemExit(f"{label}: n_pat={n_pat}, attendu {want}")
if n_ext != 120:
    raise SystemExit(f"{label}: n_ext={n_ext}, attendu 120")
expected_size = 20 + 4 * 2 * (n_pat + n_ext)
if os.path.getsize(path) != expected_size:
    raise SystemExit(f"{label}: taille PJTW incohérente")
print(f"  {label} ✓ n_pat={n_pat:,} n_ext={n_ext} version={version} scale={scale}")
PY
say "  modèle $MODEL_LABEL ✓ sha256=$MODEL_SHA"

# Le binaire sait-il seulement LIRE ce champion ? Deux secondes ici valent mieux
# qu'un « collecteur en échec » cinq minutes plus loin : c'est exactement le
# message qu'a rendu cpx62-1113, et il ne disait pas que la géométrie du pattern
# était en cause.
printf 'hello\nquit\n' | timeout 60 "$JASS" --pattern "$W/MODEL.pjtw" \
  > "$W/pattern-load.log" 2>&1
grep -q '^ready' "$W/pattern-load.log" ||
  die "le binaire ne charge pas $MODEL_LABEL : $(head -1 "$W/pattern-load.log")"
say "  chargement de $MODEL_LABEL par le binaire ✓"

# Contrat machine-lisible consommé par le readout différentiel. Les deux atlas
# sont descriptifs et suivent des trajectoires différentes ; on exige néanmoins
# que l'instrument, le budget et la génération des seeds soient identiques.
python3 - "$ART/protocol.json" "$ATLAS_VARIANT" "$MODEL_LABEL" \
  "$MODEL_SHA" "$MODEL_GZ_SHA" "$MODEL_SOURCE_PREFIX" "$EXPECTED_MODEL_JOB" \
  "$EXPECTED_CODE_SHA" "$EXPECTED_N_PAT" "$EXPECTED_NUM_PATTERNS" \
  "$EXPECTED_SCAN_SHA256" "$EXPECTED_SCAN_EVAL_SHA256" "$BUDGET_S" \
  "$PLAY_DEPTH" "$JUDGE_DEPTH" "$MAX_PLIES" "$GAMES_CAP" \
  "$MIN_POSITIONS" "$SHARDS" <<'PY'
import json, sys
(out, variant, label, model_sha, model_gz_sha, source_prefix, source_job,
 code_sha, n_pat, num_patterns, scan_sha, scan_eval_sha, budget_s, play_depth,
 judge_depth, max_plies, games_cap, min_positions, shards) = sys.argv[1:20]
payload = {
    "schema": "l3_scan_blind_spot_atlas_protocol",
    "version": 1,
    "variant": variant,
    "model": {
        "label": label,
        "sha256": model_sha,
        "gzip_sha256": model_gz_sha,
        "source_prefix": source_prefix,
        "source_job": source_job,
        "n_pat": int(n_pat),
        "n_ext": 120,
        "num_patterns": int(num_patterns),
    },
    "engine": {
        "code_sha": code_sha,
        "cmake_flags": ["JASS_ENDGAME_FEATURES=ON", "JASS_KING_MOBILITY=ON",
                         "JASS_SCAN_PARITY=ON", "JASS_TEMPO_STAGE=ON"],
        "egdb": False,
    },
    "scan": {"binary_sha256": scan_sha, "eval_sha256": scan_eval_sha,
             "bb_size": 0, "book": False},
    "collection": {
        "budget_s_per_shard": int(budget_s),
        "play_depth": int(play_depth),
        "judge_depth": int(judge_depth),
        "max_plies": int(max_plies),
        "games_cap": int(games_cap),
        "min_positions": int(min_positions),
        "shards": int(shards),
        "seed_policy": "one_based_shard_index",
        "seeds": list(range(1, int(shards) + 1)),
    },
    "diagnostic_only": True,
    "promotion_authorized": False,
    "automatic_next_job": None,
}
with open(out, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2, sort_keys=True)
    fh.write("\n")
PY

stage smoke-test-round-trip
# Règle 3/9 : le parser doit lire ce que le job écrit, vérifié sur un
# échantillon minuscule AVANT d'engager le budget complet. Un round-trip cassé
# découvert au finalize, c'est le budget entier perdu.
python3 -m unittest jobs.tests.test_scan_blind_spot_collector \
                    jobs.tests.test_scan_blind_spot_atlas \
  > "$W/selftest.log" 2>&1 || die "auto-tests en échec — voir selftest.log"
timeout 600 python3 jobs/tools/scan_blind_spot_collector.py \
  --jass "$JASS" --scan "$SCAN_BIN" --pattern "$W/MODEL.pjtw" \
  --games 2 --play-depth 4 --judge-depth 6 --max-plies 40 --seed 999 \
  --out "$W/smoke.jsonl" --summary "$W/smoke-summary.json" \
  > "$W/smoke.log" 2>&1 || die "collecteur en échec au smoke — voir smoke.log"
python3 jobs/tools/scan_blind_spot_atlas.py --samples "$W/smoke.jsonl" \
  --out "$W/smoke-atlas.json" --min-positions 1 > "$W/smoke-atlas.log" 2>&1 ||
  die "l'agrégateur ne relit pas ce que le collecteur écrit — round-trip cassé"
say "  round-trip écriture→lecture ✓ ($(wc -l < "$W/smoke.jsonl") positions de test)"

monitor
stage collect
say "  variant=$ATLAS_VARIANT modèle=$MODEL_LABEL budget=${BUDGET_S}s/shard  play_depth=$PLAY_DEPTH  judge_depth=$JUDGE_DEPTH"
# timeout par shard = budget + 10 min (règle 6). PAS un facteur multiplicatif :
# le collecteur ne teste son budget qu'ENTRE deux parties, donc il dépasse
# toujours d'au plus une partie. Un ×1.3 laisse 30 % du budget en marge, ce qui
# est confortable à 1500 s mais absurde à 20 s — un essai à budget court a fait
# tuer les deux shards par `timeout`, et un shard tué n'écrit jamais son résumé.
# Une marge ABSOLUE dimensionne la vraie grandeur : la durée d'une partie.
SHARD_TIMEOUT=$(( BUDGET_S + 600 ))
pids=()
for s in $(seq 1 "$SHARDS"); do
  (
  timeout -k 60s "${SHARD_TIMEOUT}s" python3 jobs/tools/scan_blind_spot_collector.py \
    --jass "$JASS" --scan "$SCAN_BIN" --pattern "$W/MODEL.pjtw" \
    --games "$GAMES_CAP" --play-depth "$PLAY_DEPTH" --judge-depth "$JUDGE_DEPTH" \
    --max-plies "$MAX_PLIES" --seed "$s" --time-budget-s "$BUDGET_S" \
    --out "$W/samples-s$s.jsonl" --summary "$W/summary-s$s.json" \
    --progress "$W/prog-s$s.json" \
    > "$W/collect-s$s.log" 2>&1 < /dev/null
  # Un shard qui meurt ne doit pas emporter le job : on note et on continue.
  echo "$?" > "$W/done-s$s"
  ) &
  pids+=("$!")
done
# ⚠️ JAMAIS `wait` NU quand un monitor tourne : il attendrait AUSSI le monitor,
# qui boucle jusqu'au finalize → interblocage circulaire (bug 0665/0666/0668).
wait "${pids[@]}"
say "  shards terminés : $(ls "$W"/done-s* 2>/dev/null | wc -l)/$SHARDS"

stage merge-and-aggregate
cat "$W"/samples-s*.jsonl > "$W/samples.jsonl" 2>/dev/null || true
NPOS=$(wc -l < "$W/samples.jsonl")
[ "$NPOS" -gt 0 ] || die "zéro position collectée — échec, pas un atlas vide"
say "  $NPOS positions collectées"
# Garde-fou de signe. Un signe inversé rendrait un atlas exactement à l'envers,
# sans rien casser de visible : c'est le seul défaut ici qui produit une
# conclusion fausse sans symptôme.
#
# ⚠️ Il se calcule sur les ÉCHANTILLONS, pas sur les résumés des shards. Un shard
# tué par `timeout` n'écrit jamais son résumé, mais son JSONL est flushé à chaque
# partie et survit : lire les résumés faisait passer le garde-fou à VIDE (0/0)
# pendant que les positions du shard mort, elles, partaient bien à l'agrégation.
# Un garde-fou qui se tait quand les données manquent est pire que pas de
# garde-fou — il donne l'air vérifié à ce qui ne l'est pas.
python3 - "$W/samples.jsonl" "$SHARDS" "$W" <<'PY' | tee -a "$RES" || die "convention de signe suspecte ou corpus injugeable — voir ci-dessus"
import glob, json, sys
path, shards, wdir = sys.argv[1], int(sys.argv[2]), sys.argv[3]
neg = judged = positions = 0
for line in open(path, encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    positions += 1
    cost = json.loads(line).get("cost")
    if cost is None:
        continue
    judged += 1
    neg += (cost < 0)
finished = len(glob.glob(wdir + "/summary-s*.json"))
print(f"  shards ayant écrit leur résumé : {finished}/{shards}")
if finished < shards:
    print(f"  ⚠️ {shards - finished} shard(s) tué(s) ou plantés — leurs positions "
          "restent comptées, elles ont été écrites au fil de l'eau")
share = neg / judged if judged else 0.0
print(f"  coûts négatifs = {neg}/{judged} jugés ({share:.1%}) sur {positions} positions")
if judged == 0:
    print("  ABORT: aucun désaccord jugé — la convention de signe n'a pas pu être "
          "vérifiée, l'atlas serait publié sans contrôle")
    raise SystemExit(1)
if share >= 0.40:
    print("  ABORT: part de coûts négatifs incompatible avec la convention de signe")
    raise SystemExit(1)
PY
python3 jobs/tools/scan_blind_spot_atlas.py --samples "$W/samples.jsonl" \
  --min-positions "$MIN_POSITIONS" --out "$ART/atlas.json" \
  > "$W/atlas.log" 2>&1 || die "agrégation en échec (rc=$?) — voir atlas.log"
# Enrichissement sans recalcul : l'atlas reste au schéma v2, avec le contrat de
# run ajouté pour qu'un lecteur isolé sache quel modèle et quelle géométrie il
# décrit. `protocol.json` reste publié séparément pour le readout fail-closed.
python3 - "$ART/atlas.json" "$ART/protocol.json" <<'PY'
import json, sys
atlas = json.load(open(sys.argv[1], encoding="utf-8"))
protocol = json.load(open(sys.argv[2], encoding="utf-8"))
atlas["run_protocol"] = protocol
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(atlas, fh, indent=2, sort_keys=True, ensure_ascii=False)
    fh.write("\n")
PY
gzip -c "$W/samples.jsonl" > "$ART/samples.jsonl.gz"

stage report
python3 - "$ART/atlas.json" <<'PY' | tee -a "$RES"
import json, sys
d = json.load(open(sys.argv[1]))
print(f"  positions={d['positions_seen']} accords={d['moves_agreed']} "
      f"jugés={d['disagreements_judged']} conversions={d['conversion_positions']} "
      f"écrêtés={d['costs_clipped']}")
print("  CLASSEMENT COÛT (famille ordinaire, coût/position) :")
for b in d["buckets_ranked"][:10]:
    print(f"    {b['cost_per_position']:>7.3f}  n={b['ordinary_positions']:>5} "
          f"désacc={b['disagreement_rate']:.3f}  {b['bucket']}")
if d["conversion_family"]:
    print("  FAMILLE CONVERSION (taux de gain non pris) :")
    for c in d["conversion_family"][:5]:
        print(f"    {c['miss_rate_over_positions']:>6.3f}  n={c['positions']:>4} "
              f"ratées={c['misses']}  {c['bucket']}")
print(f"  buckets sous le plancher (non classés) : {len(d['buckets_below_floor'])}")
PY
cp "$ART/atlas.json" "$ART/JASS_CONTROL_SUMMARY.json"
VERDICT="L3_SCAN_BLIND_SPOT_ATLAS_${MODEL_LABEL}_MEASURED"
: > "$ART/VERDICT__$VERDICT"
printf 'PROMOTION_AUTHORIZED__FALSE\n' > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'AUTOMATIC_NEXT_JOB__NULL\n'    > "$ART/AUTOMATIC_NEXT_JOB__NULL"
say "$VERDICT variant=$ATLAS_VARIANT positions=$NPOS promotion=false automatic_next_job=null"
