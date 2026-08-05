#!/usr/bin/env bash
# L3-PURE — axe VOLUME : 8 M frais depuis TURNOVER + toute la mémoire disponible.
#
# Le seul levier jamais testé qui ne change pas la classe du modèle. Tout le
# reste est clos : profondeur (d8 plateau, d10 plateau, d12 régression), dose de
# replay (optimum intérieur à 50 %), régularisation (L2 clos sur 3e-5). Les
# générations, elles, ne déplacent PAS la couverture — elles reremplissent les
# mêmes buckets chauds — donc si la couverture est le facteur limitant, itérer
# est le mauvais axe. À ~9,8 % de buckets visités et 4,3 observations par
# paramètre libre, elle l'est probablement.
#
# Recette de TURNOVER conservée : parent TURNOVER, labels WDL terminaux,
# géométrie 8cf, Q00, L2=3e-5, split par ouverture. Deux facteurs bougent, et
# ils sont déclarés :
#   - VOLUME : 12 M records au lieu de 2 M ;
#   - RATIO  : 67/33 frais/mémoire au lieu de 50/50, parce que la mémoire est
#     PLAFONNÉE par ce qui existe (4 M distincts) et que dupliquer ne visite
#     aucun bucket de plus. Choix explicite de JFC.
#
# ⚠️ La mémoire porte des labels produits par le moteur AVANT le correctif de la
# racine nulle (`9c1d1e8e`) : les parties atteignant une nulle par répétition y
# ont été comptées PERDUES. La moitié fraîche, elle, est générée par le moteur
# réparé. C'est une raison de plus de ne pas sur-pondérer la mémoire, et ça doit
# être lu comme un facteur du run, pas comme un détail.
#
# Aucun verdict de promotion. Aucune continuation automatique.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"
: "${TURNOVER_TRAIN_PREFIX:?}"; : "${EXPECTED_TURNOVER_TRAIN_JOB:?}"
# M1/M2 ne servent qu'a la moitie memoire : requis seulement si elle existe.
if [ "${MEMORY_RECORDS:-4000000}" -gt 0 ]; then
  : "${M1_PREFIX:?}"; : "${EXPECTED_M1_JOB:?}"
  : "${M2_PREFIX:?}"; : "${EXPECTED_M2_JOB:?}"
fi
EXPECTED_PLAYER_JOB="${EXPECTED_PLAYER_JOB:-$EXPECTED_TURNOVER_TRAIN_JOB}"

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
        # Progression réelle : chaque shard logge « X / Y positions ». On
        # somme, on sort le pourcentage et l'ETA. Compter les octets ne disait
        # pas combien il restait — home-1003 est mort après 2 h 30 sans qu'on
        # sache qu'il était à 57 %.
        awk '
          /positions$/ { done_[FILENAME] = $4; tot[FILENAME] = $6 }
          END {
            for (k in done_) { d += done_[k]; t += tot[k] }
            if (t > 0) {
              printf "positions=%d/%d\n", d, t
              printf "percent=%.1f\n", 100 * d / t
            }
          }' "$W"/fresh-s*.log 2>/dev/null || true
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
  rm -rf "$W/build" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

# Sizing parametre le 4 aout. Defauts = le corpus de juillet a l'identique.
# MEMORY_RECORDS=0 produit un corpus 100 % FRAIS : la moitie mémoire de la
# recette TURNOVER date d'avant le prior centre sur le parent, qui est devenu le
# mecanisme de memoire (+11 Elo) — et cette moitie est justement celle qui porte
# l'etiquetage casse des nulles.
FRESH_RECORDS="${FRESH_RECORDS:-8000000}"
MEMORY_RECORDS="${MEMORY_RECORDS:-4000000}"
TOTAL_RECORDS="${TOTAL_RECORDS:-12000000}"
FRESH_WEIGHT=2
MEMORY_WEIGHT=1
PRODUCERS="${PRODUCERS:-12}"
# Schéma du sidecar. JSM1 = défaut historique, byte-compatible avec tous les
# corpus existants. JSM2 = contexte de partie (ply, game_plies, last_eps_ply,
# game_result POV BLANC, flags) — INDISPENSABLE à corpus_signal_report.py, qui
# refuse explicitement un JSM1 parce que ces champs ne s'y reconstituent pas.
# ⚠️ merge/mix REFUSENT de mélanger les deux schémas : un pool destiné à M1/M2/M3
# doit être 100 % JSM2, donc 100 % frais (aucune mémoire, qui est en JSM1).
SAMPLE_META_FORMAT="${SAMPLE_META_FORMAT:-jsm1}"
case "$SAMPLE_META_FORMAT" in
  jsm1) META_FMT_ARGS=() ;;
  jsm2) META_FMT_ARGS=(--sample-meta-format jsm2)
        [ "${MEMORY_RECORDS:-0}" -eq 0 ] ||
          die "SAMPLE_META_FORMAT=jsm2 exige MEMORY_RECORDS=0 : la moitié mémoire est en JSM1 et le mix refuse les schémas mélangés" ;;
  *)    die "SAMPLE_META_FORMAT doit valoir jsm1 ou jsm2 (reçu: $SAMPLE_META_FORMAT)" ;;
esac
LABEL_DEPTH="${LABEL_DEPTH:-4}"
PLAY_DEPTH="${PLAY_DEPTH:-9}"
MAXPLIES=260
BASE_SEED="${BASE_SEED:-6180339}"
MIX_SEED=1732050
SPLIT_SEED=577215
HOLDOUT_MOD=10
NOPEN=1500
OPENING_CANDIDATES=6000
# ⛔ CODE EN DUR JUSQU'AU 5 AOUT, ET CA A FABRIQUE QUATRE POOLS IDENTIQUES.
# home-1004, home-1310, home-1311 et home-1312 ont chacun publie un pool
# d'evaluation « independant » de 1500 ouvertures : les quatre fichiers sont
# BYTE-IDENTIQUES (sha256 94cb6a15e278deeb...), parce que la graine ne bougeait
# pas. Un second pool cense repliquer rejouait donc les memes positions de
# depart. Parametre : toute generation qui veut un pool NEUF doit passer une
# graine neuve, et le chainage bayesien des portes refuse deux pools identiques.
OPENING_SEED="${OPENING_SEED:-2236068}"
# Taux MESURÉ sur cette box en home-1003 : 2 519 positions/min/shard à d9
# (le shard 0 avait produit 377 782 positions en 9 000 s avant d'être tué).
# Un shard sain doit donc écrire ses 666 667 positions en ~265 min ; plafond à
# 350 min, soit 1,3× la durée saine. Le 9 000 s précédent venait d'une
# extrapolation à 1,6× le coût de d8, alors que d9 coûte 3,9× d8.
GEN_TIMEOUT=21000
CACHE_MB=128
TURNOVER_MODEL_SHA="b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -ge 20000 ] ||
  die "need 20 GiB free"
[ "$(awk '/MemAvailable:/{print int($2/1024)}' /proc/meminfo)" -ge 3500 ] ||
  die "need 3.5 GiB available RAM"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
[ $((FRESH_RECORDS + MEMORY_RECORDS)) -eq "$TOTAL_RECORDS" ] ||
  die "record contract mismatch"
# La moitié fraîche DOIT sortir du moteur réparé : sans ça elle hériterait du
# même défaut d'étiquetage que la mémoire, et le run ne comparerait plus rien.
grep -q "root_is_drawn" src/search.cpp ||
  die "engine predates the drawn-root fix — fresh labels would be corrupted too"
monitor

phase fetch-and-authenticate-immutable-inputs
# Joueur parametrable. Defaut = TURNOVER depuis TURNOVER_TRAIN_PREFIX, donc
# home-1004 reproduit a l'identique ; un corpus neuf se genere par le champion
# courant, qui vit ailleurs.
PLAYER_PREFIX="${PLAYER_PREFIX:-$TURNOVER_TRAIN_PREFIX}"
PLAYER_FILE="${PLAYER_FILE:-turnover1to1.pjtw.gz}"
PLAYER_LABEL="${PLAYER_LABEL:-TURNOVER}"
PLAYER_SHA="${PLAYER_SHA:-$TURNOVER_MODEL_SHA}"
python3 jobs/tools/fetch_result_files.py --prefix "$PLAYER_PREFIX" \
  --file "artefacts/$PLAYER_FILE=PLAYER.pjtw.gz" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=turnover-training.json \
  --out-dir "$IN" --report "$ART/verified-turnover-training.json" \
  > "$W/fetch-turnover.log" 2>&1
if [ "$MEMORY_RECORDS" -gt 0 ]; then
python3 jobs/tools/fetch_result_files.py --prefix "$M1_PREFIX" \
  --file artefacts/common-fresh-500k.jnnw.gz=mem-a.jnnw.gz \
  --file artefacts/common-fresh-500k.jsm.gz=mem-a.jsm.gz \
  --file artefacts/extra-fresh-1500k.jnnw.gz=mem-b.jnnw.gz \
  --file artefacts/extra-fresh-1500k.jsm.gz=mem-b.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-m1-corpora.json" \
  > "$W/fetch-m1.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$M2_PREFIX" \
  --file artefacts/m2-fresh-2m.jnnw.gz=mem-c.jnnw.gz \
  --file artefacts/m2-fresh-2m.jsm.gz=mem-c.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-m2-corpus.json" \
  > "$W/fetch-m2.log" 2>&1
fi   # fin des fetch memoire
SPECS=("verified-turnover-training.json:$EXPECTED_PLAYER_JOB")
[ "$MEMORY_RECORDS" -gt 0 ] && SPECS+=(
  "verified-m1-corpora.json:$EXPECTED_M1_JOB"
  "verified-m2-corpus.json:$EXPECTED_M2_JOB")
for spec in "${SPECS[@]}"; do
  python3 - "$ART/${spec%%:*}" "${spec#*:}" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
if report.get("job_id") != sys.argv[2] or report.get("result_state") != "completed":
    raise SystemExit(f"{sys.argv[1]}: source identity/state mismatch")
PY
done
gunzip -c "$IN/PLAYER.pjtw.gz" > "$W/PLAYER.pjtw"
[ "$(sha256sum "$W/PLAYER.pjtw" | awk '{print $1}')" = "$PLAYER_SHA" ] ||
  die "$PLAYER_LABEL model hash drift"
if [ "$MEMORY_RECORDS" -gt 0 ]; then
  for part in a b c; do
    gunzip -c "$IN/mem-$part.jnnw.gz" > "$W/mem-$part.jnnw"
    gunzip -c "$IN/mem-$part.jsm.gz"  > "$W/mem-$part.jsm"
  done
  say "  entrées ✓ : $PLAYER_LABEL + trois corpus mémoire authentifiés"
else
  say "  entrées ✓ : $PLAYER_LABEL seul (corpus 100 % frais, aucune mémoire)"
fi

phase build-8cf-engine
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" $FLAGS > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests > "$W/build.log" 2>&1
ctest --test-dir "$W/build" --output-on-failure > "$W/ctest.log" 2>&1
J="$W/build/jass"
[ "$("$J" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "king-capture witness failed"
"$J" --eval-position "$W/PLAYER.pjtw" 'W:W31,32,33:B18,19,20' >/dev/null 2>&1 ||
  die "8cf engine cannot load $PLAYER_LABEL"
say "  moteur ✓ : 8cf réparé"

phase generate-8m-fresh-from-turnover-d9
base=$((FRESH_RECORDS / PRODUCERS)); rem=$((FRESH_RECORDS % PRODUCERS))
pairs=(); ACTIVE=()
for shard in $(seq 0 $((PRODUCERS - 1))); do
  count="$base"; [ "$shard" -lt "$rem" ] && count=$((count + 1))
  data="$W/fresh-s$shard.jnnw"; meta="$W/fresh-s$shard.jsm"
  timeout "$GEN_TIMEOUT" "$J" --gen-data-wdl "$count" "$data" \
    "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" $((BASE_SEED + shard)) \
    --nnue "$W/PLAYER.pjtw" --search-params-play "$Q00" --wdl-zero-score \
    --random-open-plies 8 --explore-eps 8 --explore-decay-plies 60 \
    --pair-openings --drop-plycap --sample-meta-out "$meta" \
    ${META_FMT_ARGS[@]+"${META_FMT_ARGS[@]}"} \
    > "$W/fresh-s$shard.log" 2>&1 &
  ACTIVE+=("$!"); pairs+=(--pair "$data" "$meta")
done
failed=0
for pid in "${ACTIVE[@]}"; do wait "$pid" || failed=$((failed + 1)); done
[ "$failed" -eq 0 ] || die "fresh generation: $failed producer failures"
for log in "$W"/fresh-s*.log; do
  grep -q 'label_score_searches=0' "$log" ||
    die "score-label search leaked into $log"
done
python3 tools/selfplay_frontier.py merge "${pairs[@]}" --renamespace-nested \
  --out-data "$W/fresh.jnnw" --out-meta "$W/fresh.jsm" \
  --manifest "$ART/fresh-merge.json" > "$W/fresh-merge.log" 2>&1
# Canari SUR LES DONNEES, pas sur le code. Le defaut d'etiquetage des nulles
# (4,8 % au lieu de 20,3 %) a traverse toute la lignee sans qu'aucune garde de
# code ne le voie : elles verifiaient une cause connue. Celui-ci refuse un
# corpus dont la distribution des resultats est aberrante, quelle qu'en soit la
# cause.
for _sd in "$W"/fresh-s*.jnnw; do
  python3 jobs/tools/assert_corpus_wdl.py --data "$_sd" ||
    die "canari WDL : distribution des resultats aberrante dans $_sd"
done
say "  canari WDL ✓ sur les $PRODUCERS shards"
# Round-trip écriture→lecture du schéma demandé (règle 9). Le moteur accepte
# --sample-meta-format en silence ; sans cette garde, un pool destiné à M1
# pourrait sortir en JSM1 et n'être refusé qu'à la lecture, des heures plus tard.
meta_magic_of(){ head -c4 "$1" 2>/dev/null; }
_want=$(printf '%s' "$SAMPLE_META_FORMAT" | tr '[:lower:]' '[:upper:]')
for _sm in "$W"/fresh-s*.jsm "$W/fresh.jsm"; do
  _got=$(meta_magic_of "$_sm")
  [ "$_got" = "$_want" ] ||
    die "sidecar $_sm en '$_got' alors que SAMPLE_META_FORMAT=$SAMPLE_META_FORMAT attendait '$_want'"
done
say "  sidecar ✓ : $_want sur les $PRODUCERS shards + le merge"
say "  frais ✓ : $FRESH_RECORDS records à d$PLAY_DEPTH depuis $PLAYER_LABEL"

phase assemble-memory-corpus
if [ "$MEMORY_RECORDS" -eq 0 ]; then
  say "  mémoire ⊘ : corpus 100 % frais (MEMORY_RECORDS=0)"
else
python3 tools/selfplay_frontier.py merge \
  --pair "$W/mem-a.jnnw" "$W/mem-a.jsm" \
  --pair "$W/mem-b.jnnw" "$W/mem-b.jsm" \
  --pair "$W/mem-c.jnnw" "$W/mem-c.jsm" \
  --renamespace-nested \
  --out-data "$W/memory.jnnw" --out-meta "$W/memory.jsm" \
  --manifest "$ART/memory-merge.json" > "$W/memory-merge.log" 2>&1
say "  mémoire ✓ : $MEMORY_RECORDS records (époques F2M et M2 réunies)"
fi

phase mix-twice-and-compare
MIX_SOURCES=(--source FRESH "$W/fresh.jnnw" "$W/fresh.jsm" "$FRESH_WEIGHT")
[ "$MEMORY_RECORDS" -eq 0 ] ||
  MIX_SOURCES+=(--source MEMORY "$W/memory.jnnw" "$W/memory.jsm" "$MEMORY_WEIGHT")
for pass in 1 2; do
  out="$W/vol8m.raw"; man="$ART/vol8m-mix.json"
  [ "$pass" = 2 ] && { out="$W/vol8m-repeat"; man="$W/vol8m-repeat-mix.json"; }
  python3 tools/selfplay_frontier.py mix \
    "${MIX_SOURCES[@]}" \
    --target-records "$TOTAL_RECORDS" --seed "$MIX_SEED" --namespace-openings \
    --out-data "$out.jnnw" --out-meta "$out.jsm" --manifest "$man" \
    > "$W/vol8m-mix-$pass.log" 2>&1
done
cmp -s "$W/vol8m.raw.jnnw" "$W/vol8m-repeat.jnnw" ||
  die "mix is not byte-identical across two passes"
cmp -s "$W/vol8m.raw.jsm" "$W/vol8m-repeat.jsm" ||
  die "mix metadata is not byte-identical across two passes"
python3 - "$ART/vol8m-mix.json" "$TOTAL_RECORDS" "$FRESH_RECORDS" \
  "$MEMORY_RECORDS" "$MIX_SEED" <<'PY'
import json
import sys
manifest = json.load(open(sys.argv[1]))
total, fresh, memory, seed = (int(x) for x in sys.argv[2:6])
sources = {s["label"]: s for s in manifest.get("sources", [])}
if (
    manifest.get("operation") != "weighted_aligned_mix"
    or manifest.get("seed") != seed
    or manifest.get("records") != total
    or sources.get("FRESH", {}).get("selected_records") != fresh
    or (memory and sources.get("MEMORY", {}).get("selected_records") != memory)
    or (not memory and "MEMORY" in sources)
    or manifest.get("opening_id_policy")
    != "source_namespaced_for_independent_temporal_corpora"
    or manifest.get("external_teacher_inputs") != 0
):
    raise SystemExit("volume mix contract mismatch")
PY
rm -f "$W/vol8m-repeat.jnnw" "$W/vol8m-repeat.jsm"
say "  mix ✓ : $TOTAL_RECORDS records, $FRESH_RECORDS frais / $MEMORY_RECORDS mémoire"

phase split-by-opening-twice
for pass in 1 2; do
  out="$W/vol8m.fit"; man="$ART/vol8m-split.json"
  [ "$pass" = 2 ] && { out="$W/vol8m-repeat.fit"; man="$W/vol8m-repeat-split.json"; }
  python3 tools/selfplay_frontier.py split \
    --data "$W/vol8m.raw.jnnw" --meta "$W/vol8m.raw.jsm" \
    --out-data "$out.jnnw" --out-meta "$out.jsm" \
    --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" --manifest "$man" \
    > "$W/vol8m-split-$pass.log" 2>&1
done
cmp -s "$W/vol8m.fit.jnnw" "$W/vol8m-repeat.fit.jnnw" ||
  die "split is not byte-identical across two passes"
rm -f "$W/vol8m-repeat.fit.jnnw" "$W/vol8m-repeat.fit.jsm"
gzip -n -c "$W/vol8m.raw.jnnw" > "$ART/vol8m.jnnw.gz"
gzip -n -c "$W/vol8m.raw.jsm"  > "$ART/vol8m.jsm.gz"
say "  split ✓ : holdout 1/$HOLDOUT_MOD par ouverture, graine $SPLIT_SEED"

phase exact-coverage
# C'est le MÉCANISME testé, pas un à-côté : si le volume n'achète pas de
# couverture, l'axe est mort quelle que soit la force mesurée ensuite.
env PYTHONPATH="$GEOM:pattern_jass/tools" \
  python3 jobs/tools/l3_bucket_visits.py --data "$W/vol8m.raw.jnnw" \
  --out "$ART/vol8m-coverage.json" > "$W/coverage.log" 2>&1
say "  couverture ✓ mesurée sur les $TOTAL_RECORDS records"

phase independent-evaluation-pool
"$J" --gen-opening-pool "$OPENING_CANDIDATES" "$W/open-candidates.fen" \
  8 32 20 "$OPENING_SEED" > "$W/open-candidates.log" 2>&1
python3 jobs/tools/select_independent_opening_pool.py \
  --candidates "$W/open-candidates.fen" --expected "$NOPEN" \
  --exclude data/dilf_combinations.fen \
  --generator-seed "$OPENING_SEED" \
  --out "$ART/vol8m-eval-openings.fen" \
  --manifest "$ART/vol8m-eval-openings.json" \
  > "$W/select-openings.log" 2>&1
say "  pool d'évaluation ✓ : $NOPEN ouvertures neuves"

phase publish-certificate
python3 - "$ART" "$EXPECTED_CODE_SHA" "$TOTAL_RECORDS" "$FRESH_RECORDS" \
  "$MEMORY_RECORDS" "$PLAY_DEPTH" "$MIX_SEED" "$SPLIT_SEED" <<'PY'
import hashlib
import json
import pathlib
import sys

art = pathlib.Path(sys.argv[1])
code_sha = sys.argv[2]
total, fresh, memory, play_depth = (int(x) for x in sys.argv[3:7])
mix_seed, split_seed = (int(x) for x in sys.argv[7:9])

# Les clés sont imbriquées : les lire à plat rendrait None sans rien casser,
# et le certificat sortirait vide. Round-trip vérifié contre la sortie réelle
# de l'outil, pas contre son nom de champ supposé.
cov = json.load(open(art / "vol8m-coverage.json"))
visited = cov["coverage"]["visited_buckets"]
buckets = cov["geometry"]["trained_buckets_total"]
share = round(100.0 * cov["coverage"]["coverage_fraction"], 3)
gini = cov["concentration"]["gini"]
ge_100 = cov["coverage"]["buckets_with_at_least"]["ge_100"]
heuristic = cov["capacity_heuristic"]
# Un paramètre libre = un bucket effectivement visité ; les autres gardent leur
# valeur initiale. TURNOVER : 1 801 803 lignes pour 418 070 colonnes = 4,3.
obs = round(total / visited, 2) if visited else None

payload = {
    "schema": 1,
    "verdict": "L3_PURE_VOLUME8M_PREFLIGHT_READY",
    "code_sha": code_sha,
    "train_authorized": True,
    "corpus": {
        "total_records": total,
        "fresh_records": fresh,
        "memory_records": memory,
        "fresh_share_pct": round(100.0 * fresh / total, 1),
        "play_depth": play_depth,
        "mix_seed": mix_seed,
        "split_seed": split_seed,
        "data_sha256": hashlib.sha256(
            (art / "vol8m.jnnw.gz").read_bytes()).hexdigest(),
    },
    "coverage": {
        "visited_buckets": visited,
        "total_buckets": buckets,
        "visited_pct": share,
        "buckets_with_at_least_100_visits": ge_100,
        "gini": gini,
        "capacity_heuristic": heuristic,
        "observations_per_free_parameter": obs,
        "turnover_reference": {"visited_pct": 9.8, "visited_buckets": 208914,
                               "observations_per_free_parameter": 4.3,
                               "gini": 0.85},
    },
    "declared_deviations_from_the_turnover_recipe": [
        "volume 12M instead of 2M — this is the factor under test",
        "fresh/memory ratio 67/33 instead of 50/50 — the memory half is "
        "capped at 4M distinct records and duplicating it visits no "
        "additional bucket",
        "play depth 9 instead of 8",
        "the memory half was labelled by the engine BEFORE the drawn-root "
        "fix, so games reaching a repetition draw were recorded as losses; "
        "the fresh half was not",
    ],
    "promotion_authorized": False,
    "automatic_next_job": None,
}
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
(art / "JASS_CONTROL_SUMMARY.json").write_text(serialized)
(art / "VERDICT__L3_PURE_VOLUME8M_PREFLIGHT_READY").write_text(
    "L3_PURE_VOLUME8M_PREFLIGHT_READY\n")
(art / "PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")
print(f"  couverture : {visited} / {buckets} buckets = {share} % "
      f"(TURNOVER : 208914 = 9,8 %)")
print(f"  buckets >= 100 visites : {ge_100} ; gini {gini}")
print(f"  observations par paramètre libre : {obs} (TURNOVER : 4,3)")
print(f"  heuristique de capacite : {heuristic}")
PY
phase complete
say "L3_PURE_VOLUME8M_PREFLIGHT_READY promotion=false automatic_next_job=null"
