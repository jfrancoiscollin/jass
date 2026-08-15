#!/usr/bin/env bash
# L3 — porte appariée GÉNÉRIQUE entre deux modèles, chacun désigné par son job
# d'origine et le nom de son artefact.
#
# Généralisée depuis la porte fold-exact, qui ne savait lire que deux modèles du
# MÊME job. Comparer une passe on-policy à son parent demande deux sources
# distinctes, et dupliquer le template aurait fait diverger deux copies de la
# même logique de lecture.
#
# Deux vues, comme les portes précédentes : `q00` à profondeur 9 fixe et `native`
# à movetime 0,1. Les compteurs BRUTS sont sommés — moyenner deux taux de n
# différents pondérerait mal et rendrait un intervalle faux.
#
# ⚠️ C'est la porte qui tranche, pas la perte en holdout. Ce projet a mesuré
# quatre fois que la perte ne prédit pas la force ; le holdout des deux bras est
# rapporté comme information, jamais comme verdict.
#
# Aucune promotion automatique. Un bras qui gagne devient un candidat à revue.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${A_PREFIX:?}"; : "${A_JOB:?}"; : "${A_FILE:?}"; : "${A_LABEL:?}"
: "${B_PREFIX:?}"; : "${B_JOB:?}"; : "${B_FILE:?}"; : "${B_LABEL:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART" "$ART/force"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: > "$RES"; : > "$PROG"; echo start > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "phase=$1"; }

PREFLIGHT_PREFIX="${PREFLIGHT_PREFIX:-r2:jass-data/runs/home-1004-l3-pure-volume8m-preflight-v2/20260727T211936Z-90d3aad1}"
# Le pool d'ouvertures est paramétré parce qu'une mesure répétée sur LE MÊME
# pool n'est pas une réplication indépendante : elle rejoue les mêmes positions
# de départ. Une confirmation sur un second pool disjoint demande donc de
# pointer un autre préflight, et son artefact ne porte pas le même nom.
PREFLIGHT_FILE="${PREFLIGHT_FILE:-vol8m-eval-openings.fen}"
EXPECTED_PREFLIGHT_JOB="${EXPECTED_PREFLIGHT_JOB:-home-1004-l3-pure-volume8m-preflight-v2}"
NSH_GATE="${NSH_GATE:-12}"; PAR_GATE="${PAR_GATE:-12}"
VIEWS="${VIEWS:-q00 native}"
PAIRED_BOOTSTRAP_SAMPLES="${PAIRED_BOOTSTRAP_SAMPLES:-0}"
PAIRED_BOOTSTRAP_SEED="${PAIRED_BOOTSTRAP_SEED:-20260816}"
# 1 = ancien comportement sans garde d'erreur explicite. Les protocoles causaux
# modernes fixent 0.02 et activent obligatoirement le bootstrap apparié, seul
# chemin qui conserve le nombre de parties rendues en erreur par le harness.
MAX_ERROR_RATE="${MAX_ERROR_RATE:-1}"
FORCE_DEPTH=9; MOVETIME=0.1; CACHE_MB=128
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"
# Parametres de recherche par bras. Defaut = Q00 des deux cotes, donc toutes
# les portes de modele restent inchangees ; un A/B de recherche pose le meme
# modele des deux cotes et fait varier CECI.
SEARCH_PARAMS_A="${SEARCH_PARAMS_A:-$Q00}"; SEARCH_PARAMS_B="${SEARCH_PARAMS_B:-$Q00}"

MON=""
monitor(){
  ( t0=$(date +%s)
    while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        printf 'views_done=%s\n' "$(find "$ART/force" -name '*.json' 2>/dev/null | wc -l)"
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 120
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
  rm -rf "$W"/build* "$IN" "$W"/gate-* 2>/dev/null || true
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
[ "${DFA:-0}" -gt 5000 ] || die "moins de 5 Go libres (${DFA} Mo)"
NCPU=$(nproc); say "  nproc=$NCPU libre=${DFA}Mo shards=$NSH_GATE"
monitor

stage fetch-models-and-openings
fetch_arm(){   # $1 lettre, $2 prefix, $3 job, $4 nom de l'artefact
  python3 jobs/tools/fetch_result_files.py --prefix "$2" \
    --file "artefacts/$4=$1.pjtw.gz" \
    --out-dir "$IN" --report "$ART/verified-$1.json" \
    --expected-state completed > "$W/fetch-$1.log" 2>&1 || die "fetch $1 en échec"
  python3 - "$ART/verified-$1.json" "$3" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
if r.get("job_id") != sys.argv[2] or r.get("result_state") != "completed":
    raise SystemExit("source identity/state mismatch")
PY
  gunzip -c "$IN/$1.pjtw.gz" > "$W/$1.pjtw"
}
fetch_arm A "$A_PREFIX" "$A_JOB" "$A_FILE"
fetch_arm B "$B_PREFIX" "$B_JOB" "$B_FILE"
# Deux bras STRICTEMENT identiques rendraient un verdict qui ne veut rien dire.
# ⚠️ Mais un A/B de PARAMETRES DE RECHERCHE pose deliberement le meme modele des
# deux cotes : la garde doit donc porter sur le couple (modele, parametres), pas
# sur le modele seul, sinon elle tue exactement le montage qu'elle devrait
# laisser passer.
if cmp -s "$W/A.pjtw" "$W/B.pjtw" &&
   [ "${SEARCH_PARAMS_A:-$Q00}" = "${SEARCH_PARAMS_B:-$Q00}" ]; then
  die "les deux bras sont le MÊME modèle ET les mêmes paramètres — porte sans objet"
fi
python3 jobs/tools/fetch_result_files.py --prefix "$PREFLIGHT_PREFIX" \
  --file "artefacts/$PREFLIGHT_FILE=open-eval.fen" \
  --out-dir "$IN" --report "$ART/verified-openings.json" \
  --expected-state completed > "$W/fetch-openings.log" 2>&1 || die "fetch des ouvertures en échec"
cp "$IN/open-eval.fen" "$W/open-eval.fen"
NOPEN=$(awk '{sub(/#.*/,""); gsub(/^[ \t]+|[ \t]+$/,""); if (length) n++} END {print n+0}' "$W/open-eval.fen")
[ "$NOPEN" -gt 0 ] || die "aucune ouverture"
GAMES_PER_VIEW=$((NOPEN * 2))
say "  A=$A_LABEL ($A_JOB)"
say "  B=$B_LABEL ($B_JOB)"
say "  $NOPEN ouvertures → $GAMES_PER_VIEW parties/vue, vues : $VIEWS"

stage build
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1 ||
  { restore_src; die "génération 8cf en échec"; }
grep -q "g_emasks"        src/scan_eval.cpp || { restore_src; die "archi: scan_eval sans g_emasks"; }
grep -q "has_any_capture" src/search.cpp    || { restore_src; die "archi: search sans has_any_capture"; }
grep -q "root_is_drawn"   src/search.cpp    || { restore_src; die "engine predates the drawn-root fix"; }
grep -q "warm_kings_endgame_bitbases" src/hub.cpp ||
  { restore_src; die "engine predates the movetime endgame bake"; }
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
# EGDB si la box l'a, sinon on s'en passe. Les DEUX bras partagent le binaire,
# donc la comparaison interne tient dans les deux cas ; seule la comparabilité
# avec les portes antérieures dépend de sa présence, et on l'écrit dans le rapport.
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
if [ -n "$EGDIR" ]; then
  [ -d /root/egdb_intl ] ||
    die "base EGDB trouvée ($EGDIR) mais la bibliothèque /root/egdb_intl manque"
  FLAGS="$FLAGS -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl"
  export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
  say "  EGDB présent ($EGDIR) — comparable aux portes antérieures"
elif [ "${REQUIRE_EGDB:-0}" = 1 ]; then
  # Une porte de succession DOIT tourner avec la base, sinon son Elo n'est pas
  # comparable aux portes de promotion antérieures et le chiffre ne peut pas
  # servir à ce pour quoi on l'a demandé. Échouer ici coûte deux minutes ;
  # découvrir l'absence dans le rapport coûte la porte entière — c'est ce qui
  # s'est passé sur cpx62-1118 et 1121.
  say "  chemins inspectés : /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted"
  die "REQUIRE_EGDB=1 mais aucune base trouvée sur $(hostname)"
else
  say "  ⚠️ EGDB ABSENT — comparaison interne valide, Elo non comparable aux portes antérieures"
fi
# Un build PAR BRAS quand les deux bras n'ont pas la même géométrie de features.
# Motif : un modèle `--king-patterns` exige un moteur compilé
# `-DJASS_KING_PATTERNS` (CMakeLists.txt), l'occupation devenant `men|kings`.
# Tant que les deux extras sont vides — le cas de TOUTES les portes antérieures —
# un SEUL build est produit et les deux bras partagent le binaire, exactement
# comme avant. `run_jass_gate_bounded.py` accepte déjà deux binaires distincts
# (`--jass-a` / `--jass-b`), donc rien à changer côté harnais.
ARM_A_CMAKE_EXTRA="${ARM_A_CMAKE_EXTRA:-}"; ARM_B_CMAKE_EXTRA="${ARM_B_CMAKE_EXTRA:-}"
build_engine(){   # $1 = suffixe de repertoire, $2... = flags supplementaires
  local tag="$1"; shift
  cmake -S . -B "$W/build$tag" $FLAGS "$@" > "$W/cmake$tag.log" 2>&1
  cmake --build "$W/build$tag" -j"$NCPU" --target jass > "$W/build$tag.log" 2>&1
  [ -x "$W/build$tag/jass" ] || { restore_src; die "build$tag sans binaire"; }
}
if [ "$ARM_A_CMAKE_EXTRA" = "$ARM_B_CMAKE_EXTRA" ]; then
  build_engine "" $ARM_A_CMAKE_EXTRA
  JA="$W/build/jass"; JB="$JA"
  say "  build unique partagé par les deux bras${ARM_A_CMAKE_EXTRA:+ ($ARM_A_CMAKE_EXTRA)}"
else
  build_engine "-A" $ARM_A_CMAKE_EXTRA
  build_engine "-B" $ARM_B_CMAKE_EXTRA
  JA="$W/build-A/jass"; JB="$W/build-B/jass"
  # ⚠️ Deux binaires = un second facteur POTENTIEL. Il n'est legitime que parce
  # que le modele d'un bras est INCHARGEABLE par le build de l'autre : le
  # chargeur refuse un modele dont le bit king de l'en-tete contredit le build
  # (scan_eval.cpp). C'est verifie juste en dessous, bras par bras.
  say "  builds PAR BRAS : A [$ARM_A_CMAKE_EXTRA] · B [$ARM_B_CMAKE_EXTRA]"
fi
restore_src
load_ok(){ printf 'hello\nquit\n' | timeout 60 "$1" --pattern "$2" > "$3" 2>&1; grep -q '^ready' "$3"; }
load_ok "$JA" "$W/A.pjtw" "$W/load-A.log" || die "le binaire du bras A ne charge pas le modèle A"
load_ok "$JB" "$W/B.pjtw" "$W/load-B.log" || die "le binaire du bras B ne charge pas le modèle B"
# Garde-fou du build par bras : si les deux builds differaient mais que chaque
# binaire chargeait AUSSI le modele de l'autre, c'est que la distinction annoncee
# n'existe pas dans les artefacts et que la porte mesurerait deux fois la meme
# geometrie sous deux binaires — un second facteur GRATUIT, donc illegitime.
if [ "$JA" != "$JB" ]; then
  if load_ok "$JA" "$W/B.pjtw" "$W/crossload-AB.log" &&
     load_ok "$JB" "$W/A.pjtw" "$W/crossload-BA.log"; then
    die "builds par bras demandés mais les deux modèles se chargent des deux côtés : la distinction n'est pas dans les modèles"
  fi
  say "  distinction par bras ✓ (chaque binaire refuse le modèle de l'autre)"
fi
say "  build ✓, modèles chargeables"

run_view(){
  local view="$1"; local args=()
  local bootstrap_args=()
  [ "$view" = q00 ] && args=(--depth "$FORCE_DEPTH") || args=(--movetime "$MOVETIME")
  if [ "$PAIRED_BOOTSTRAP_SAMPLES" -gt 0 ]; then
    bootstrap_args=(--paired-bootstrap-samples "$PAIRED_BOOTSTRAP_SAMPLES"
      --paired-bootstrap-seed "$PAIRED_BOOTSTRAP_SEED")
  fi
  timeout 10800 python3 jobs/tools/run_jass_gate_bounded.py \
    --jass-a "$JA" --jass-b "$JB" \
    --pattern-a "$W/A.pjtw" --pattern-b "$W/B.pjtw" \
    --search-params-a "$SEARCH_PARAMS_A" --search-params-b "$SEARCH_PARAMS_B" \
    --openings-file "$W/open-eval.fen" "${args[@]}" --pairs 1 \
    --max-plies 160 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout 9000 --game-timeout 180 \
    "${bootstrap_args[@]}" \
    --work-dir "$W/gate-$view" \
    --out "$ART/force/$view-A-vs-B.json" \
    > "$W/gate-$view.log" 2>&1
}

# Les vues jouees. Defaut = les deux, comme toutes les portes anterieures.
# ⚠️ A/B DE PARAMETRES DE RECHERCHE : mettre VIEWS="native". La vue `q00` est a
# PROFONDEUR FIXE, donc un bras qui elague moins y explore plus d'arbre pour la
# meme profondeur nominale — il gagne presque par construction, et l'estimateur
# somme melangerait cette vue biaisee a la seule qui mesure le compromis reel.
stage play-both-views
# Une vue qui tombe ne tue pas le job : le bloc de lecture rend INCONCLUANT sur
# vue manquante, et ce verdict vaut mieux qu'un abort muet.
for view in $VIEWS; do
  stage "view-$view"
  if run_view "$view"; then say "  vue $view jouée"; else say "  vue $view ÉCHOUÉE (rc=$?)"; fi
done

# ⛓️ PRIOR CHAINE (facultatif) — le posterieur d'une porte ANTERIEURE sur un
# SECOND POOL DISJOINT devient le prior de celle-ci. Demande par JFC le 5 aout :
# deux verdicts separes qu'il faut recoller a la main valent moins qu'un P(>0)
# courant. Les compteurs BRUTS de la porte precedente sont relus et recombines
# par precision ; on ne fait pas confiance aux arrondis stockes.
PRIOR_GATE_PREFIX="${PRIOR_GATE_PREFIX:-}"
PRIOR_GATE_JOB="${PRIOR_GATE_JOB:-}"
PRIOR_JSON=""
if [ -n "$PRIOR_GATE_PREFIX" ]; then
  stage fetch-prior-gate
  : "${PRIOR_GATE_JOB:?PRIOR_GATE_PREFIX fourni sans PRIOR_GATE_JOB}"
  python3 jobs/tools/fetch_result_files.py --prefix "$PRIOR_GATE_PREFIX" \
    --file "artefacts/JASS_CONTROL_SUMMARY.json=prior-gate.json" \
    --out-dir "$IN" --report "$ART/verified-prior-gate.json" \
    --expected-state completed > "$W/fetch-prior.log" 2>&1 ||
    die "fetch de la porte anterieure en echec"
  python3 - "$ART/verified-prior-gate.json" "$PRIOR_GATE_JOB" <<'PYP'
import json, sys
r = json.load(open(sys.argv[1]))
if r.get("job_id") != sys.argv[2] or r.get("result_state") != "completed":
    raise SystemExit("identite/etat de la porte anterieure non conforme")
PYP
  PRIOR_JSON="$IN/prior-gate.json"
  cp "$PRIOR_JSON" "$ART/prior-gate.json"
  say "  prior chaine ✓ : $PRIOR_GATE_JOB"
fi

stage readout
python3 - "$ART" "$GAMES_PER_VIEW" "$EXPECTED_CODE_SHA" "$A_LABEL" "$B_LABEL" "$VIEWS" \
  "$PREFLIGHT_PREFIX" "$PRIOR_JSON" "${PRIOR_OPENINGS_PREFIX:-}" \
  "$MAX_ERROR_RATE" "$PAIRED_BOOTSTRAP_SAMPLES" "$PAIRED_BOOTSTRAP_SEED" <<'PY' | tee -a "$RES"
import json, math, pathlib, sys
art = pathlib.Path(sys.argv[1]); per_view = int(sys.argv[2])
code_sha = sys.argv[3]; A_LABEL, B_LABEL = sys.argv[4], sys.argv[5]
openings_prefix = sys.argv[7]
prior_path = sys.argv[8] if len(sys.argv) > 8 and sys.argv[8] else None
legacy_prior_openings = sys.argv[9] if len(sys.argv) > 9 and sys.argv[9] else None
max_error_rate = float(sys.argv[10]); paired_samples = int(sys.argv[11]); paired_seed = int(sys.argv[12])
if not 0 <= max_error_rate <= 1:
    raise SystemExit(f"MAX_ERROR_RATE hors [0,1] : {max_error_rate}")
views = {}
for v in sys.argv[6].split():
    p = art / "force" / f"{v}-A-vs-B.json"
    views[v] = json.load(open(p)) if p.exists() else None
missing = [v for v, d in views.items() if d is None]
short = [v for v, d in views.items() if d and d.get("n", 0) < int(0.9 * per_view)]
paired_missing = [v for v,d in views.items() if d and paired_samples > 0 and not d.get("paired_opening")]
error_rows = {v:(d.get("paired_opening") or {}).get("error_draws")
              for v,d in views.items() if d}
error_guard_unobservable = bool(max_error_rate < 1 and paired_samples <= 0)
excess_errors = [v for v,e in error_rows.items()
                 if max_error_rate < 1 and (e is None or e > max_error_rate * per_view)]
# Compteurs BRUTS sommés : moyenner deux taux de n différents pondérerait mal.
wins = sum(d["wins_a"] for d in views.values() if d)
draws = sum(d["draws"] for d in views.values() if d)
losses = sum(d["wins_b"] for d in views.values() if d)
n = wins + draws + losses
rate = se = lo = hi = None
if n:
    rate = (wins + 0.5 * draws) / n
    var = max(0.0, (wins + 0.25 * draws) / n - rate * rate)
    se = math.sqrt(var / n)
    lo, hi = max(0.0, rate - 1.96 * se), min(1.0, rate + 1.96 * se)
def elo(r):
    return -400 * math.log10(1 / r - 1) if r and 0 < r < 1 else None
def rate_of_elo(e):
    return 1.0 / (1.0 + 10 ** (-e / 400.0))
def _phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
# Lecture BAYESIENNE, demandee par JFC le 5 aout et c'est la bonne demande :
# « la borne basse contient zero » jette l'information que porte la POSITION de
# la masse. Avec un prior plat sur le taux, la vraisemblance normale donne
# directement P(Elo > seuil), qui est ce qu'on veut vraiment savoir. Rapporte
# EN PLUS de l'IC, jamais a la place : le verdict reste frequentiste pour ne pas
# casser la comparabilite avec toutes les portes anterieures.
POSTERIOR_THRESHOLDS = (0, 3, 5, 10, 17)
def posterior_of(mu, sd):
    return {f"p_elo_gt_{e}": round(1.0 - _phi((rate_of_elo(e) - mu) / sd), 4)
            for e in POSTERIOR_THRESHOLDS}
posterior = posterior_of(rate, se) if (n and se and se > 0) else None

# ⛓️ Chainage. Les deux portes mesurent LE MEME estimand — l'effet de
# l'intervention — sur des pools d'ouvertures DISJOINTS. On recombine par
# precision, ce qui revient a une mise a jour bayesienne sequentielle avec prior
# plat au depart.
# ⚠️ CE QUE LE CHAINAGE SUPPOSE, et il faut le dire : que l'effet est LE MEME
# dans les deux pools. Avec deux replicats on ne peut pas estimer la variance
# inter-pool ; si les deux portes se contredisent franchement, c'est cette
# hypothese-la qui casse, et le DESACCORD est alors le resultat, pas la moyenne.
chained = None
if prior_path and posterior:
    prior = json.load(open(prior_path))
    pv = prior.get("views_summed") or {}
    if prior.get("matchup") != f"{A_LABEL} vs {B_LABEL}":
        raise SystemExit(f"prior d'un autre appariement : {prior.get('matchup')!r}")
    # ⛔ FAIL-CLOSED. Les portes anterieures a 2026-08-05 n'ecrivaient pas
    # `openings_prefix` : sans ce garde-fou, chainer l'une d'elles SAUTERAIT
    # silencieusement le seul controle qui distingue une replication d'un
    # doublon. Un prior sans le champ exige donc que l'operateur declare son
    # pool via PRIOR_OPENINGS_PREFIX, et le declarer faux se voit dans le job.
    prior_openings = prior.get("openings_prefix") or legacy_prior_openings
    if not prior_openings:
        raise SystemExit(
            "le prior ne declare pas son pool d'ouvertures (porte anterieure au "
            "5 aout) : passer PRIOR_OPENINGS_PREFIX pour l'attester, sinon la "
            "disjonction des pools n'est pas verifiable et le chainage est refuse")
    if prior_openings == openings_prefix:
        raise SystemExit("le prior vient du MEME pool d'ouvertures : ce n'est pas "
                         "une replication independante, chainage refuse")
    pw, pd, pl = pv.get("wins_a"), pv.get("draws"), pv.get("wins_b")
    if None in (pw, pd, pl):
        raise SystemExit("compteurs bruts absents du prior")
    pn = pw + pd + pl
    if pn <= 0:
        raise SystemExit("prior a n=0")
    # Recalcul depuis les compteurs BRUTS : on ne reprend pas les arrondis.
    prate = (pw + 0.5 * pd) / pn
    pvar = max(0.0, (pw + 0.25 * pd) / pn - prate * prate)
    pse = math.sqrt(pvar / pn)
    if pse <= 0:
        raise SystemExit("prior de variance nulle")
    wp, wl = 1.0 / (pse * pse), 1.0 / (se * se)
    cmu = (prate * wp + rate * wl) / (wp + wl)
    csd = math.sqrt(1.0 / (wp + wl))
    # ⚠️ GARDE D'HETEROGENEITE. Le chainage suppose le MEME effet dans les deux
    # pools. Sans ce test, un pool a +8 et un pool a -2 peuvent rendre un
    # P(>0) confortable alors que le DESACCORD est le vrai resultat. On teste
    # donc la difference des deux taux avant de combiner quoi que ce soit.
    dz = (rate - prate) / math.sqrt(se * se + pse * pse)
    # ⚠️ CORRECTION DU 6 AOUT. La garde testait AUSSI que les deux pools soient
    # de meme signe. C'etait trop agressif et le message qui en sortait etait
    # faux : home-1315 a rendu +3,04 et -1,01 avec |z| = 0,93, donc des pools
    # parfaitement COMPATIBLES, et la garde imprimait « se contredisent
    # (z=-0.928) ». Un effet vrai proche de zero produit des signes opposes une
    # fois sur deux ; refuser le chainage sur ce motif, c'est refuser
    # precisement quand la bonne reponse est « l'effet est nul ».
    # Le desaccord se teste STATISTIQUEMENT, pas au signe. Le signe reste
    # rapporte, comme information, jamais comme critere.
    pools_agree = bool(abs(dz) < 1.96)
    chained = {
        "prior_job": prior.get("job_id") or prior.get("code_sha"),
        "prior_openings_prefix": prior_openings,
        "prior_openings_attested_by_operator": not prior.get("openings_prefix"),
        "between_pool_z": round(dz, 3),
        "pools_agree": pools_agree,
        "same_sign": bool((rate - 0.5) * (prate - 0.5) >= 0),
        "prior_n": pn, "prior_rate": round(prate, 6),
        "prior_elo": round(elo(prate), 2) if elo(prate) is not None else None,
        "combined_n": pn + n, "combined_rate": round(cmu, 6),
        "combined_elo": round(elo(cmu), 2) if elo(cmu) is not None else None,
        "combined_ci95": [round(elo(max(1e-9, cmu - 1.96 * csd)), 1),
                          round(elo(min(1 - 1e-9, cmu + 1.96 * csd)), 1)],
        "posterior": posterior_of(cmu, csd),
        "assumes_same_effect_in_both_pools": True,
    }

# ⚖️ CRITERE DE BAKE — fixe par JFC le 5 aout 2026 :
#   P(Elo > 0) > 95 % SUR POOLS CHAINES.
# C'est une PRE-CONDITION, jamais une autorisation : un bake reste une decision
# explicite de JFC. Le drapeau ci-dessous ne fait que dire si la condition est
# remplie, et il exige DEUX pools disjoints qui ne se contredisent pas.
BAKE_P_THRESHOLD = 0.95
bake = {"criterion": "P(elo>0) > 0.95 sur pools chaines",
        "threshold": BAKE_P_THRESHOLD, "met": False, "why": None}
if missing or short or paired_missing or error_guard_unobservable or excess_errors or not n:
    bake["why"] = ("gate incomplet ou garde d'erreur/bootstrap non satisfaite: "
                   f"missing={missing} short={short} paired_missing={paired_missing} "
                   f"error_guard_unobservable={error_guard_unobservable} "
                   f"excess_errors={excess_errors}")
elif chained is None:
    bake["why"] = "un seul pool : le critere exige un chainage sur deux pools disjoints"
elif not chained["pools_agree"]:
    bake["why"] = (f"les deux pools se contredisent STATISTIQUEMENT "
                   f"(|z|={abs(chained['between_pool_z'])} >= 1.96) : "
                   "le desaccord est le resultat, pas la moyenne")
elif chained["posterior"]["p_elo_gt_0"] <= BAKE_P_THRESHOLD:
    bake["why"] = f"P(elo>0)={chained['posterior']['p_elo_gt_0']} <= {BAKE_P_THRESHOLD}"
else:
    bake["met"] = True
    bake["why"] = f"P(elo>0)={chained['posterior']['p_elo_gt_0']} sur n={chained['combined_n']}"
if missing or short or paired_missing or error_guard_unobservable or excess_errors or not n:
    verdict = "L3_MODEL_GATE_INCONCLUSIVE"
elif lo > 0.5:
    verdict = "A_BEATS_B_HUMAN_REVIEW"
elif hi < 0.5:
    verdict = "A_BELOW_B"
else:
    verdict = "A_FLAT_VS_B_NO_ESTABLISHED_GAIN"
payload = {
    "schema": 1, "verdict": verdict, "code_sha": code_sha,
    "matchup": f"{A_LABEL} vs {B_LABEL}",
    "views_summed": {
        "wins_a": wins, "draws": draws, "wins_b": losses, "n": n,
        "rate": round(rate, 6) if rate else None,
        "ci95": [round(lo, 6), round(hi, 6)] if rate else None,
        "elo": round(elo(rate), 2) if elo(rate) is not None else None,
        "elo_ci95": ([round(elo(lo), 1), round(elo(hi), 1)]
                     if elo(lo) is not None and elo(hi) is not None else None),
        "posterior_flat_prior": posterior},
    "openings_prefix": openings_prefix,
    "paired_bootstrap": {"samples": paired_samples, "seed": paired_seed,
                         "per_view": True, "error_draws": error_rows},
    "max_error_rate": max_error_rate,
    "error_guard_passed": not error_guard_unobservable and not excess_errors,
    "chained_with_prior_gate": chained,
    "bake_criterion": bake,
    "per_view": {v: d for v, d in views.items()},
    "arms": {"a": A_LABEL, "b": B_LABEL},
    "holdout_is_not_the_arbiter": (
        "This project has measured four times that holdout loss does not "
        "predict strength. The gate decides; the loglosses are context."),
    "diagnostic_only": True, "gate_authorized": True,
    "promotion_authorized": False, "automatic_next_job": None,
}
(art / "JASS_CONTROL_SUMMARY.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n")
print(f"  n={n}  {A_LABEL} {wins}W {draws}D {losses}L contre {B_LABEL}")
if rate:
    print(f"  taux={rate:.4f}  IC95=[{lo:.4f} ; {hi:.4f}]")
    print(f"  Elo={elo(rate):+.2f}  IC95=[{elo(lo):+.1f} ; {elo(hi):+.1f}]")
if posterior:
    print("  posterieur (prior plat) : " + "  ".join(
        f"P(Elo>{e})={100*posterior[f'p_elo_gt_{e}']:.1f}%" for e in POSTERIOR_THRESHOLDS))
if chained:
    c = chained
    print(f"  ⛓️ chaine avec {c['prior_job']} : prior n={c['prior_n']} Elo={c['prior_elo']:+.2f}")
    print(f"     combine n={c['combined_n']}  Elo={c['combined_elo']:+.2f}"
          f"  IC95=[{c['combined_ci95'][0]:+.1f} ; {c['combined_ci95'][1]:+.1f}]")
    print(f"     accord des pools : z={c['between_pool_z']:+.2f} -> "
          f"{'COMPATIBLES' if c['pools_agree'] else 'CONTRADICTOIRES'}"
          f"{'' if c['same_sign'] else '  (signes opposes, ce qui est ATTENDU pres de zero)'}")
    print("     posterieur combine : " + "  ".join(
        f"P(Elo>{e})={100*c['posterior'][f'p_elo_gt_{e}']:.1f}%" for e in POSTERIOR_THRESHOLDS))
print(f"  critere de bake (P(Elo>0)>95 % sur pools chaines) : "
      f"{'REMPLI' if bake['met'] else 'NON REMPLI'} — {bake['why']}")
if paired_samples:
    print(f"  bootstrap apparie/ouverture={paired_samples} seed={paired_seed} "
          f"erreurs={error_rows} plafond={100*max_error_rate:.2f}%")
print(f"  VERDICT {verdict}")
PY
VERDICT="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")"
: > "$ART/VERDICT__$VERDICT"
printf 'PROMOTION_AUTHORIZED__FALSE\n' > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'AUTOMATIC_NEXT_JOB__NULL\n'    > "$ART/AUTOMATIC_NEXT_JOB__NULL"
say "$VERDICT promotion=false automatic_next_job=null"
