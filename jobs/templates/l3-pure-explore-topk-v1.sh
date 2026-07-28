#!/usr/bin/env bash
# L3-PURE — self-play dont le bruit d'exploration tombe sur un coup PLAUSIBLE.
#
# Le self-play perturbe sa politique avec `--explore-eps 8 --explore-decay-plies
# 60` : à chaque ply, avec une probabilité qui décroît de 8 % à zéro au ply 60,
# le coup joué est tiré UNIFORMÉMENT parmi tous les coups légaux. Avec un
# facteur de branchement de 8-10, ce tirage est une gaffe neuf fois sur dix. La
# distribution d'états s'élargit donc vers des positions-après-erreur, que
# personne de fort ne rencontre — alors que le déficit de `−242 Elo` contre Scan
# se joue sur des lignes quasi optimales (`home-1002`).
#
# `--explore-topk 3 --explore-margin 50` tire parmi les trois meilleurs coups,
# et seulement parmi ceux qui tiennent dans un demi-pion du meilleur. Même dose
# de perturbation, sur des coups plausibles.
#
# UN SEUL BRAS (décision JFC, pas d'A/B). Ce job produit un modèle ; il ne
# mesure aucune force. La force se lit dans une porte séparée contre le parent.
#
# ⚠️ CONFONDS DÉCLARÉS — à lire avant d'interpréter la porte qui suivra. Ce
# corpus s'écarte de la recette du parent sur PLUSIEURS facteurs, pas seulement
# le top-k :
#   1. top-k + marge au lieu du tirage uniforme — le facteur sous test ;
#   2. volume `RECORDS` au lieu des 2 M du parent ;
#   3. corpus 100 % frais, aucune moitié mémoire (le parent avait 50/50) ;
#   4. `DEPTH_MIX` si elle vaut autre chose que `8:100`. Le défaut aligne la
#      profondeur sur celle du parent, justement pour ne PAS ajouter cet axe ;
#      tout mix demandé explicitement en rajoute un, et le certificat le déclare
#      comme tel au lieu de le taire.
# `home-1008` vient de montrer ce que coûte un corpus qui bouge sur quatre axes :
# son verdict nomme le volume alors qu'il ne l'isole pas. Une porte gagnante ici
# ne prouvera PAS que le top-k est la cause ; une porte perdante ne l'innocentera
# pas non plus.
#
# Aucun verdict de promotion. Aucune continuation automatique.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"
# Le parent est paramétré : TURNOVER aujourd'hui, un champion baké plus tard,
# sans réécrire le template.
: "${PARENT_TRAIN_PREFIX:?}"; : "${EXPECTED_PARENT_TRAIN_JOB:?}"
: "${PARENT_ARTEFACT:?}"; : "${PARENT_MODEL_SHA:?}"; : "${PARENT_NAME:?}"

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

# Hygiène disque : les jobs qui meurent laissent leur scratch derrière eux et le
# disque se remplit au fil des semaines (ccx33 saturé le 2026-07-11).
find "$JASS_RESULT_DIR/.." -maxdepth 1 -name 'cw-*' -type d -mmin +180 \
  ! -path "$W" -exec rm -rf {} + 2>/dev/null || true

RECORDS=${RECORDS:-4000000}
SHARDS=${SHARDS:-12}
LABEL_DEPTH=4
# DEPTH_MIX = `profondeur:pourcentage[,profondeur:pourcentage...]`, en part des
# RECORDS. `8:100` = monoprofondeur d8, alignée sur le parent. `8:80,9:20` =
# quatre cinquièmes du corpus joués à d8, un cinquième à d9.
#
# Les shards sont répartis entre profondeurs de façon à ce que TOUTES finissent
# en même temps : un d9 rend ~3,9x moins de positions par minute qu'un d8, donc
# lui donner sa part de shards au prorata des records le ferait traîner et le
# job entier attendrait dessus. La répartition se fait au prorata du TEMPS
# (records ÷ rate), pas des records.
DEPTH_MIX=${DEPTH_MIX:-8:100}
MAXPLIES=260
EXPLORE_EPS=8
EXPLORE_DECAY=60
TOPK=3
MARGIN=50
BASE_SEED=2718281
SPLIT_SEED=577215
HOLDOUT_MOD=10
# Rates MESURÉS par shard et par minute (home-1003/1004 : 117 647 et 30 223
# positions/min sur 12 shards, soit 9 804 et 2 519 par shard), puis pénalité
# top-k MESURÉE : 4000 records d9 en 52,2 s uniforme contre 63,0 s top-k sur la
# même box, bras en parallèle, soit +21 %. Le timeout par shard est le temps
# sain de SA profondeur x1,3 — un timeout global calibré sur le d8 culerait
# tous les shards d9 à zéro record, la bourde 0659.
RATE_D8=9804
RATE_D9=2519
FIT_TIMEOUT=${FIT_TIMEOUT:-7200}
L2=3e-5
MAXIT=1000
LBFGS_MAXCOR=20
LBFGS_GTOL=1e-3
CHUNK=20000
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

MON=""
monitor(){
  (
    local t0; t0=$(date +%s)
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
        awk '/MemAvailable:/{printf "mem_available_mb=%d\n",$2/1024}' /proc/meminfo
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        # `gen-data-wdl` imprime « X / Y positions » ; on somme les shards et on
        # extrapole le restant sur le rythme observé depuis le début.
        awk -v el="$(( ($(date +%s) - t0) / 60 ))" '
          /positions$/ { d[FILENAME] = $4; t[FILENAME] = $6 }
          END {
            for (k in d) { s += d[k]; u += t[k] }
            if (u > 0) {
              printf "gen_positions=%d/%d (%.1f%%)\n", s, u, 100 * s / u
              if (s > 0 && el > 0)
                printf "gen_eta_remaining_min=%d\n", el * (u - s) / s
            }
          }' "$W"/gen-s*.log 2>/dev/null || true
        [ -f "$W/fit.log" ] && printf 'fit_lines=%s\n' "$(wc -l < "$W/fit.log")"
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"
      cp "$PROG" "$ART/PROGRESS.txt"
      sleep 60
    done
  ) &
  MON="$!"
}
restore_src(){ git checkout -- src/ 2>/dev/null || true; }
finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$W/venv" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat 2>/dev/null || true
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
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
NCPU=$(nproc)
[ "$NCPU" -ge 12 ] || die "HOME requires 12 logical CPUs, got $NCPU"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -ge 20000 ] || die "need 20 GiB free, got ${DFA}M"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"

# Plan de génération : une ligne par profondeur, `depth shards records_par_shard
# records_totaux timeout_s minutes_saines`. Calculé ici plutôt qu'en bash pour
# que l'équilibrage des temps soit lisible et testable.
python3 - "$DEPTH_MIX" "$RECORDS" "$SHARDS" "$RATE_D8" "$RATE_D9" \
  > "$W/plan.txt" <<'PY' || die "DEPTH_MIX invalide : $DEPTH_MIX"
import sys

mix_spec, records, shards, rate_d8, rate_d9 = sys.argv[1:6]
records, shards = int(records), int(shards)
rates = {8: int(rate_d8), 9: int(rate_d9)}

mix = []
for part in mix_spec.split(","):
    depth_s, _, pct_s = part.partition(":")
    depth, pct = int(depth_s), float(pct_s)
    if depth not in rates:
        raise SystemExit(f"profondeur {depth} sans rate mesuré — mesurer avant d'utiliser")
    if pct <= 0:
        raise SystemExit(f"part nulle ou négative pour d{depth}")
    mix.append((depth, pct))
total_pct = sum(p for _, p in mix)
if abs(total_pct - 100.0) > 1e-6:
    raise SystemExit(f"les parts font {total_pct}, pas 100")
if len(mix) > shards:
    raise SystemExit("plus de profondeurs que de shards")

# Records par profondeur, le reste allant à la première pour tomber juste.
recs = {d: int(records * p / 100.0) for d, p in mix}
recs[mix[0][0]] += records - sum(recs.values())

# Shards répartis pour que toutes les profondeurs finissent ENSEMBLE, sinon le
# job attend la plus lente. Un prorata arrondi suffit mal sur 12 shards (il
# laissait 27 min d'écart sur un 50/50) : on alloue gloutonnement, en donnant
# chaque shard suivant à la profondeur dont le temps courant est le pire.
cost = {d: recs[d] / rates[d] for d, _ in mix}          # minutes-shard totales
alloc = {d: 1 for d, _ in mix}
for _ in range(shards - len(mix)):
    alloc[max(alloc, key=lambda d: cost[d] / alloc[d])] += 1

for depth, _ in mix:
    n = alloc[depth]
    per = -(-recs[depth] // n)                          # plafond
    healthy = max(1, int(per * 1.21 / rates[depth]))    # minutes, pénalité top-k
    print(f"{depth} {n} {per} {recs[depth]} {healthy * 78} {healthy}")
PY
say "  sizing : nproc=$NCPU shards=$SHARDS records=$RECORDS mix=$DEPTH_MIX"
while read -r d n per tot to healthy; do
  say "  sizing : d$d -> $n shards x $per records ($tot au total), ~${healthy} min sain, timeout ${to}s"
done < "$W/plan.txt"
cp "$W/plan.txt" "$ART/generation-plan.txt"
monitor

phase pull-and-assert-perf-critical-sources
# Ne jamais faire confiance à l'arbre de base du runner pour les fichiers
# perf-critiques : ils peuvent être silencieusement stale.
#
# On tire de la SHA ÉPINGLÉE, pas de `origin/develop`. La règle gravée dit « une
# ref connue » ; une branche n'en est pas une, elle bouge. Un push sur develop
# pendant que le job vole lui ferait compiler autre chose que ce qu'il déclare —
# c'est la famille de bourdes qui a tué home-1005, et le job asserte déjà
# HEAD == EXPECTED_CODE_SHA juste au-dessus, donc tirer de cette SHA ne fait que
# garantir que l'ARBRE correspond au commit, ce qui est tout l'objet du pull.
for f in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp \
         src/movegen.cpp src/movegen.hpp src/main.cpp; do
  git show "$EXPECTED_CODE_SHA:$f" > "$f" ||
    die "cannot pull $f from $EXPECTED_CODE_SHA"
done
grep -q "g_emasks"        src/scan_eval.cpp || { restore_src; die "archi: scan_eval sans g_emasks"; }
grep -q "has_any_capture" src/search.cpp    || { restore_src; die "archi: search sans has_any_capture"; }
grep -q "has_any_capture" src/movegen.cpp   || { restore_src; die "archi: movegen sans has_any_capture"; }
grep -q "root_is_drawn"   src/search.cpp    || { restore_src; die "engine predates the drawn-root fix"; }
# Sans ces deux options le job retomberait silencieusement sur le tirage
# uniforme et produirait un corpus qui n'a rien à voir avec ce qu'on croit.
grep -q "explore_topk"   src/main.cpp || { restore_src; die "engine has no --explore-topk"; }
grep -q "explore_margin" src/main.cpp || { restore_src; die "engine has no --explore-margin"; }
grep -q "split_selfplay_rngs" src/main.cpp ||
  { restore_src; die "engine has no --split-selfplay-rngs (PR 384)"; }
# Les invariants top-k vivent dans un helper testé (PR 384) : classement de
# l'enfant à play_depth-1, historique de répétition transmis, coups
# sémantiquement égaux dédupliqués. Le job refuse de tourner sur un binaire qui
# les aurait perdus — la profondeur EFFECTIVE est re-vérifiée après génération
# sur ce que le moteur a réellement imprimé, pas sur la présence du fichier.
git show "$EXPECTED_CODE_SHA:src/selfplay_exploration.hpp" > src/selfplay_exploration.hpp ||
  { restore_src; die "selfplay_exploration.hpp absent du commit épinglé"; }
grep -q "select_topk_exploration_move" src/main.cpp ||
  { restore_src; die "main.cpp n'utilise pas le helper top-k (PR 384)"; }
say "  garde-fou archi ✓ : g_emasks + has_any_capture + root_is_drawn + topk/margin à profondeur de jeu"

phase fetch-and-authenticate-parent
python3 jobs/tools/fetch_result_files.py --prefix "$PARENT_TRAIN_PREFIX" \
  --file "artefacts/$PARENT_ARTEFACT=PARENT.pjtw.gz" \
  --out-dir "$IN" --report "$ART/verified-parent.json" \
  > "$W/fetch-parent.log" 2>&1
python3 - "$ART/verified-parent.json" "$EXPECTED_PARENT_TRAIN_JOB" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
if report.get("job_id") != sys.argv[2] or report.get("result_state") != "completed":
    raise SystemExit(f"{sys.argv[1]}: source identity/state mismatch")
PY
gunzip -c "$IN/PARENT.pjtw.gz" > "$W/PARENT.pjtw"
[ "$(sha256sum "$W/PARENT.pjtw" | awk '{print $1}')" = "$PARENT_MODEL_SHA" ] ||
  die "parent model hash drift"
say "  parent ✓ : $PARENT_NAME"

phase build-engine-and-runtime
python3 -m venv "$W/venv"
"$W/venv/bin/python" -m pip install --disable-pip-version-check \
  --only-binary=:all: numpy==1.26.4 scipy==1.14.1 > "$W/pip.log" 2>&1
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests > "$W/build.log" 2>&1
ctest --test-dir "$W/build" --output-on-failure > "$W/ctest.log" 2>&1
J="$W/build/jass"
[ "$("$J" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "king-capture witness failed"
say "  moteur ✓ : 8cf"

phase generate-fresh-corpus
# Un timeout PAR SHARD : un shard bloqué ne doit jamais geler le job. Les PID
# sont collectés explicitement — un `wait` nu attendrait aussi le monitor et
# bloquerait le job pour toujours.
pids=()
shard=0
# Chaque shard porte SA profondeur et SON timeout, lus du plan. Les index de
# shard restent globalement uniques : ils fondent les graines et les noms de
# fichier, deux shards de profondeurs différentes ne doivent pas se recouvrir.
while read -r pd pn pper ptot pto phealthy; do
  for _ in $(seq 1 "$pn"); do
    echo "$shard $pd" >> "$W/shard-depths.txt"
    # `< /dev/null` : sans ça un enfant lancé en fond hérite du stdin de la
    # boucle — c'est-à-dire du plan lui-même — et peut le consommer.
    timeout "$pto" "$J" --gen-data-wdl "$pper" \
      "$W/gen-s$shard.jnnw" "$LABEL_DEPTH" "$pd" "$MAXPLIES" \
      $((BASE_SEED + shard)) \
      --nnue "$W/PARENT.pjtw" --search-params-play "$Q00" --wdl-zero-score \
      --random-open-plies 8 --explore-eps "$EXPLORE_EPS" \
      --explore-decay-plies "$EXPLORE_DECAY" \
      --explore-topk "$TOPK" --explore-margin "$MARGIN" \
      --split-selfplay-rngs \
      --pair-openings --drop-plycap --sample-meta-out "$W/gen-s$shard.jsm" \
      < /dev/null > "$W/gen-s$shard.log" 2>&1 &
    pids+=("$!")
    shard=$((shard + 1))
  done
done < "$W/plan.txt"
[ "$shard" -eq "$SHARDS" ] || die "plan incohérent : $shard shards lancés pour $SHARDS"
cp "$W/shard-depths.txt" "$ART/shard-depths.txt"
failed=0
for pid in "${pids[@]}"; do wait "$pid" || failed=$((failed + 1)); done
[ "$failed" -eq 0 ] || die "generation: $failed producer failures"
for log in "$W"/gen-s*.log; do
  grep -q 'label_score_searches=0' "$log" || die "score-label search in $log"
done

# La perturbation a-t-elle réellement tiré, et à quelle dose ? Un job qui
# sortirait topk_ranked_plies=0 aurait produit un corpus uniforme sans le dire.
cat "$W"/gen-s*.log | grep '^EXPLORATION' > "$ART/exploration.txt"
sum_key(){ awk -v k="$1" '{for(i=1;i<=NF;i++) if ($i ~ "^"k"=") {split($i,a,"="); s+=a[2]}} END {print s+0}' "$ART/exploration.txt"; }
TOPK_PLIES=$(sum_key topk_ranked_plies)
EPS_EVENTS=$(sum_key eps_events)
[ "$TOPK_PLIES" -gt 0 ] || die "no ply ranked — the top-k flag did not fire"
[ "$EPS_EVENTS" -gt 0 ] || die "no exploration event — eps did not fire"
# Profondeur de classement EFFECTIVE, relue de ce que le moteur a imprimé. Le
# contrat est play_depth-1 ; c'est la seule des trois corrections de PR 384 qui
# soit observable de l'extérieur, donc c'est celle qu'on asserte.
RANK_DEPTHS=$(awk '{for(i=1;i<=NF;i++) if ($i ~ /^topk_rank_depth=/) {split($i,a,"="); print a[2]}}' \
  "$ART/exploration.txt" | sort -u | tr '\n' ' ')
SPLIT_RNG=$(awk '{for(i=1;i<=NF;i++) if ($i ~ /^split_selfplay_rngs=/) {split($i,a,"="); print a[2]}}' \
  "$ART/exploration.txt" | sort -u | tr -d ' \n')
[ "$SPLIT_RNG" = "1" ] || die "les flux RNG séparés ne sont pas actifs (=$SPLIT_RNG)"
while read -r pd pn pper ptot pto phealthy; do
  grep -qw "$((pd - 1))" <<<"$RANK_DEPTHS" ||
    die "profondeur de classement attendue $((pd - 1)) pour d$pd, observées : $RANK_DEPTHS"
done < "$W/plan.txt"
say "  invariants top-k ✓ : classement à {$RANK_DEPTHS}, RNG séparés"

# Le mix RÉALISÉ, compté sur les fichiers écrits — pas celui du plan. Un shard
# tué par son timeout rend moins de records que prévu, et le corpus glisse vers
# la profondeur rapide sans que rien ne le dise. Tolérance 2 points.
python3 - "$W" "$DEPTH_MIX" "$ART/depth-mix.json" <<'PY' || die "mix de profondeur réalisé hors tolérance"
import json
import pathlib
import struct
import sys

w, mix_spec, out = pathlib.Path(sys.argv[1]), sys.argv[2], pathlib.Path(sys.argv[3])
wanted = {int(p.split(":")[0]): float(p.split(":")[1]) for p in mix_spec.split(",")}
by_depth = {}
for line in (w / "shard-depths.txt").read_text().split("\n"):
    if not line.strip():
        continue
    shard, depth = line.split()
    blob = (w / f"gen-s{shard}.jnnw").read_bytes()[:8]
    n = struct.unpack_from("<I", blob, 4)[0]
    by_depth[int(depth)] = by_depth.get(int(depth), 0) + n
total = sum(by_depth.values())
if total == 0:
    raise SystemExit("zéro record produit")
realised = {d: round(100.0 * n / total, 3) for d, n in sorted(by_depth.items())}
drift = {d: round(realised.get(d, 0.0) - pct, 3) for d, pct in wanted.items()}
worst = max(abs(v) for v in drift.values())
report = {"schema": 1, "requested_pct": wanted, "realised_pct": realised,
          "records_by_depth": {str(d): n for d, n in sorted(by_depth.items())},
          "total_records": total, "drift_pp": drift,
          "worst_drift_pp": worst, "tolerance_pp": 2.0, "ok": worst <= 2.0}
out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
print("  mix réalisé : " + "  ".join(f"d{d}={p}%" for d, p in realised.items())
      + f"  (dérive max {worst} pt)")
if worst > 2.0:
    raise SystemExit(f"dérive {worst} pt au-dessus de la tolérance de 2 pt")
PY
say "  génération ✓ : $EPS_EVENTS tirages eps, $TOPK_PLIES plies classées"

phase merge-split-and-fit
pairs=()
for shard in $(seq 0 $((SHARDS - 1))); do
  pairs+=(--pair "$W/gen-s$shard.jnnw" "$W/gen-s$shard.jsm")
done
python3 tools/selfplay_frontier.py merge "${pairs[@]}" --renamespace-nested \
  --out-data "$W/topk.raw.jnnw" --out-meta "$W/topk.raw.jsm" \
  --manifest "$ART/merge.json" > "$W/merge.log" 2>&1
python3 tools/selfplay_frontier.py split \
  --data "$W/topk.raw.jnnw" --meta "$W/topk.raw.jsm" \
  --out-data "$W/topk.fit.jnnw" --out-meta "$W/topk.fit.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$ART/split.json" > "$W/split.log" 2>&1
env PYTHONPATH="$GEOM:pattern_jass/tools" \
  python3 jobs/tools/l3_bucket_visits.py --data "$W/topk.raw.jnnw" \
  --out "$ART/topk-coverage.json" > "$W/coverage.log" 2>&1
# Canari sur les DONNÉES, pas sur le code. Les gardes `grep root_is_drawn`
# n'auraient jamais vu le défaut de racine nulle si la cause avait été autre :
# elles vérifient une cause connue. Celle-ci vérifie le SYMPTÔME — un corpus
# d'où les nulles ont disparu — et attrape donc aussi la prochaine cause.
# Repères mesurés à d8, même graine et même parent : moteur cassé 4,8 % de
# nulles, moteur réparé 20,3 %.
python3 jobs/tools/assert_corpus_wdl.py --data "$W/topk.raw.jnnw" \
  --out "$ART/corpus-wdl.json" > "$W/corpus-wdl.log" 2>&1 ||
  die "corpus WDL aberrant — voir $ART/corpus-wdl.json"
WDL_SHARES=$(python3 - "$ART/corpus-wdl.json" <<'PY'
import json
import sys
s = json.load(open(sys.argv[1]))["shares"]
print(f"{s['loss']:.3f} L / {s['draw']:.3f} N / {s['win']:.3f} W")
PY
)
say "  canari WDL ✓ : $WDL_SHARES"
gzip -n -c "$W/topk.raw.jnnw" > "$ART/topk4m.jnnw.gz"
gzip -n -c "$W/topk.raw.jsm"  > "$ART/topk4m.jsm.gz"

HOLD=$("$W/venv/bin/python" -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["holdout_records"])' \
  "$ART/split.json")
[ "$HOLD" -gt 0 ] || die "holdout missing"
"$J" --dump-eval-features "$W/topk.fit.jnnw" "$W/topk.feat" \
  > "$W/features.log" 2>&1
set +e
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
  timeout "$FIT_TIMEOUT" \
  "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
  --data "$W/topk.fit.jnnw" --feat "$W/topk.feat" --out "$W/topk4m.pjtw" \
  --target wdl --loss logistic --color-fold --tempo-stage \
  --warm-start "$W/PARENT.pjtw" --holdout-count "$HOLD" \
  --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
  --lbfgs-maxcor "$LBFGS_MAXCOR" --lbfgs-gtol "$LBFGS_GTOL" \
  --optimizer-report "$ART/topk4m-optimizer.json" \
  > "$W/fit.log" 2>&1
FIT_RC=$?
set -e
# Le checkpoint part AVANT la porte de convergence : un fit non convergé reste
# une donnée, et le perdre coûterait tout le temps de génération.
[ -s "$W/topk4m.pjtw" ] && gzip -n -c "$W/topk4m.pjtw" > "$ART/topk4m.pjtw.gz"
[ "$FIT_RC" -eq 0 ] || die "fit failed rc=$FIT_RC; checkpoint preserved"
"$W/venv/bin/python" - "$ART/topk4m-optimizer.json" <<'PY' ||
import json
import sys
if not json.load(open(sys.argv[1])).get("success"):
    raise SystemExit(1)
PY
  die "optimiser did not converge"
say "  fit ✓ convergé"

phase publish-certificate
"$W/venv/bin/python" - "$W" "$ART" "$EXPECTED_CODE_SHA" "$RECORDS" \
  "$EXPLORE_EPS" "$EXPLORE_DECAY" "$TOPK" "$MARGIN" \
  "$PARENT_NAME" "$DEPTH_MIX" <<'PY'
import hashlib
import json
import pathlib
import re
import sys

w, art = map(pathlib.Path, sys.argv[1:3])
code_sha = sys.argv[3]
records, eps, decay, topk, margin = (int(x) for x in sys.argv[4:9])
parent, depth_mix = sys.argv[9], sys.argv[10]
depth_report = json.load(open(art / "depth-mix.json"))

keys = ("eps_events", "eps_changed_best", "play_plies", "games",
        "topk_ranked_plies", "margin_singleton_plies",
        "topk_duplicate_candidates")
counts = {k: 0 for k in keys}
for line in (art / "exploration.txt").read_text().splitlines():
    for tok in line.split():
        k, _, v = tok.partition("=")
        if k in counts:
            counts[k] += int(v)
counts["eps_rate_pct"] = (round(100.0 * counts["eps_events"] / counts["play_plies"], 3)
                          if counts["play_plies"] else None)
counts["changed_best_share"] = (round(counts["eps_changed_best"] / counts["eps_events"], 3)
                                if counts["eps_events"] else None)
counts["margin_singleton_share"] = (
    round(counts["margin_singleton_plies"] / counts["topk_ranked_plies"], 3)
    if counts["topk_ranked_plies"] else None)

cov = json.load(open(art / "topk-coverage.json"))
opt = json.load(open(art / "topk4m-optimizer.json"))
log = (w / "fit.log").read_text(errors="replace")
m = re.search(r"HOLDOUT_LOGLOSS[ =:]+([0-9.]+)", log)

payload = {
    "schema": 1,
    "verdict": "L3_PURE_EXPLORE_TOPK_MODEL_READY",
    "code_sha": code_sha,
    "question": "does self-play whose exploration noise lands on plausible "
                "moves produce a stronger model than the parent",
    "model": {
        "name": "TOPK4M",
        "geometry": "8cf",
        "parent": f"{parent} (warm start)",
        "sha256": hashlib.sha256((w / "topk4m.pjtw").read_bytes()).hexdigest(),
    },
    "design": {
        "single_arm": True,
        "records": records,
        "fresh_share_pct": 100.0,
        "depth_mix_requested": depth_mix,
        "depth_mix_realised_pct": depth_report["realised_pct"],
        "records_by_depth": depth_report["records_by_depth"],
        "explore_eps": eps,
        "explore_decay_plies": decay,
        "explore_topk": topk,
        "explore_margin": margin,
        "ranking_depth": "play_depth - 1 (PR 384 invariant, asserted on the "
                         "engine's own topk_rank_depth counter)",
        "split_selfplay_rngs": True,
    },
    "exploration": counts,
    "coverage": {
        "visited_buckets": cov["coverage"]["visited_buckets"],
        "visited_pct": round(100.0 * cov["coverage"]["coverage_fraction"], 3),
        "gini": cov["concentration"]["gini"],
        "buckets_ge_100": cov["coverage"]["buckets_with_at_least"]["ge_100"],
    },
    "fit": {
        "iterations": opt.get("nit"),
        "converged": opt.get("success"),
        "holdout_logloss": float(m.group(1)) if m else None,
    },
    "confounds_declared": [
        "explore-topk + margin instead of uniform noise — the factor under test",
        f"volume {records} instead of the parent's 2M",
        f"play depth mix {depth_mix} instead of the parent's uniform d8"
        if depth_mix != "8:100" else
        "play depth d8, aligned on the parent — not a confound",
        "100% fresh, no replay memory — the parent was 50/50",
    ],
    "confound_warning": (
        "This corpus moves on three axes at once, so a gate result will not "
        "attribute to top-k on its own. home-1008 is the cautionary case: its "
        "preregistered verdict names the volume axis while changing four "
        "factors, one of which was a mislabelled third of the corpus."
    ),
    "holdout_loss_is_a_diagnostic_not_a_selection_criterion": True,
    "readout_required": (
        f"TOPK4M vs {parent}, both views, views summed, n=6000 on a fresh "
        "opening pool — this job produces a model, it does not measure strength"
    ),
    "promotion_authorized": False,
    "automatic_next_job": None,
}
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
(art / "topk4m-certificate.json").write_text(serialized)
(art / "JASS_CONTROL_SUMMARY.json").write_text(serialized)
(art / "VERDICT__L3_PURE_EXPLORE_TOPK_MODEL_READY").write_text(
    "L3_PURE_EXPLORE_TOPK_MODEL_READY\n")
(art / "PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")

c, cv, f = counts, payload["coverage"], payload["fit"]
print(f"  eps {c['eps_rate_pct']}% sur {c['play_plies']} plies, "
      f"{c['games']} parties")
print(f"  classées {c['topk_ranked_plies']}, singletons de marge "
      f"{c['margin_singleton_share']}, coup changé {c['changed_best_share']}")
print(f"  couverture {cv['visited_pct']}% gini {cv['gini']} "
      f"| fit {f['iterations']} it, holdout {f['holdout_logloss']}")
PY
phase complete
say "L3_PURE_EXPLORE_TOPK_MODEL_READY promotion=false automatic_next_job=null"
