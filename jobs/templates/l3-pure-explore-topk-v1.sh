#!/usr/bin/env bash
# L3-PURE — le bruit d'exploration doit-il tomber sur un coup plausible ?
#
# Le self-play perturbe sa politique avec `--explore-eps 8 --explore-decay-plies
# 60` : à chaque ply, avec une probabilité qui décroît de 8 % à zéro au ply 60,
# le coup joué est tiré UNIFORMÉMENT parmi tous les coups légaux. Avec un
# facteur de branchement de 8-10, ce tirage est une gaffe neuf fois sur dix. La
# distribution d'états s'élargit donc vers des positions-après-erreur, que
# personne de fort ne rencontre — alors que le déficit de `−242 Elo` contre Scan
# se joue sur des lignes quasi optimales (`home-1002`).
#
# `--explore-topk 3 --explore-margin 50` tire parmi les TROIS meilleurs coups
# situés à au plus 50 centipawns du meilleur. Même dose de perturbation, mais
# sur des coups plausibles, avec repli sur le seul meilleur coup si la position
# est tactiquement tranchée.
#
# Deux bras, un seul facteur : UNIFORM contre TOPK3. Tout le reste est identique
# — même parent, même volume, même profondeur, même graine d'ouverture, même
# L2, même warm-start, même split. Les deux bras génèrent EN PARALLÈLE pour
# subir des conditions machine identiques.
#
# Écart déclaré, identique sur les deux bras : corpus 100 % frais, sans moitié
# mémoire. Diluer de moitié un effet qu'on cherche à détecter serait se tirer
# une balle dans le pied ; la comparaison porte bras contre bras, et l'absence
# de mémoire ne les distingue pas. En contrepartie, aucun des deux n'est
# directement comparable à TURNOVER, qui lui en avait — la cellule de
# continuité doit se lire comme telle et non comme une causalité propre.
#
# Aucun verdict de promotion. Aucune continuation automatique.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"
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
        for arm in uniform topk3; do
          awk -v a="$arm" '
            /positions$/ { d[FILENAME] = $4; t[FILENAME] = $6 }
            END {
              for (k in d) { s += d[k]; u += t[k] }
              if (u > 0) printf "%s_positions=%d/%d (%.1f%%)\n", a, s, u, 100 * s / u
            }' "$W"/"$arm"-s*.log 2>/dev/null || true
        done
        for arm in uniform topk3; do
          [ -f "$W/fit-$arm.log" ] &&
            printf 'fit_%s_lines=%s\n' "$arm" "$(wc -l < "$W/fit-$arm.log")"
        done
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
  rm -rf "$W/build" "$W/venv" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

RECORDS=2000000
SHARDS=6                 # 6 par bras, deux bras en parallèle = 12 procs / 16 CPU
LABEL_DEPTH=4
PLAY_DEPTH=9
MAXPLIES=260
EXPLORE_EPS=8
EXPLORE_DECAY=60
TOPK=3
EXPLORE_MARGIN=50
BASE_SEED=2718281        # identique aux deux bras : mêmes ouvertures tirées
SPLIT_SEED=577215
HOLDOUT_MOD=10
# Taux mesuré en home-1003 : 2 519 positions/min/shard à d9. 333 334 positions
# par shard => ~132 min sain ; le classement à la profondeur de jeu coûte +21 %
# sur le micro-benchmark publié, soit ~160 min. Plafond à 200 min.
GEN_TIMEOUT=12000
FIT_TIMEOUT=7200
L2=3e-5
MAXIT=1000
LBFGS_MAXCOR=20
LBFGS_GTOL=1e-3
CHUNK=20000
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
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -ge 15000 ] ||
  die "need 15 GiB free"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
grep -q "root_is_drawn" src/search.cpp || die "engine predates the drawn-root fix"
# Sans cette option le bras TOPK3 retomberait silencieusement sur le tirage
# uniforme et le job comparerait deux fois la même chose.
grep -q "explore_topk" src/main.cpp || die "engine has no --explore-topk"
grep -q "explore_margin" src/main.cpp || die "engine has no --explore-margin"
monitor

phase fetch-and-authenticate-parent
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_TRAIN_PREFIX" \
  --file artefacts/turnover1to1.pjtw.gz=TURNOVER.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-turnover.json" \
  > "$W/fetch-turnover.log" 2>&1
python3 - "$ART/verified-turnover.json" "$EXPECTED_TURNOVER_TRAIN_JOB" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
if report.get("job_id") != sys.argv[2] or report.get("result_state") != "completed":
    raise SystemExit(f"{sys.argv[1]}: source identity/state mismatch")
PY
gunzip -c "$IN/TURNOVER.pjtw.gz" > "$W/TURNOVER.pjtw"
[ "$(sha256sum "$W/TURNOVER.pjtw" | awk '{print $1}')" = "$TURNOVER_MODEL_SHA" ] ||
  die "TURNOVER model hash drift"
say "  parent ✓ : TURNOVER"

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
say "  moteur ✓ : 8cf, --explore-topk présent"

# Un bras = une politique d'exploration. Tout le reste est passé à l'identique,
# y compris la graine, pour que les deux bras partent des mêmes ouvertures.
gen_arm(){
  local arm="$1"; shift
  local base=$((RECORDS / SHARDS)) rem=$((RECORDS % SHARDS)) count shard
  local pids=()
  for shard in $(seq 0 $((SHARDS - 1))); do
    count="$base"; [ "$shard" -lt "$rem" ] && count=$((count + 1))
    timeout "$GEN_TIMEOUT" "$J" --gen-data-wdl "$count" \
      "$W/$arm-s$shard.jnnw" "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" \
      $((BASE_SEED + shard)) \
      --nnue "$W/TURNOVER.pjtw" --search-params-play "$Q00" --wdl-zero-score \
      --random-open-plies 8 --explore-eps "$EXPLORE_EPS" \
      --explore-decay-plies "$EXPLORE_DECAY" "$@" \
      --pair-openings --drop-plycap --sample-meta-out "$W/$arm-s$shard.jsm" \
      > "$W/$arm-s$shard.log" 2>&1 &
    pids+=("$!")
  done
  local failed=0 pid
  for pid in "${pids[@]}"; do wait "$pid" || failed=$((failed + 1)); done
  [ "$failed" -eq 0 ] || die "$arm generation: $failed producer failures"
}

phase generate-both-arms-in-parallel
gen_arm uniform &
UPID=$!
gen_arm topk3 --explore-topk "$TOPK" --explore-margin "$EXPLORE_MARGIN" &
TPID=$!
wait "$UPID" || die "uniform arm failed"
wait "$TPID" || die "topk3 arm failed"
for arm in uniform topk3; do
  for log in "$W/$arm"-s*.log; do
    grep -q 'label_score_searches=0' "$log" || die "score-label search in $log"
  done
done
# La perturbation a-t-elle réellement tiré, et à quelle dose ? Un bras TOPK3 qui
# sortirait topk_ranked_plies=0 n'aurait pas testé ce qu'on croit tester.
for arm in uniform topk3; do
  cat "$W/$arm"-s*.log | grep '^EXPLORATION' > "$ART/exploration-$arm.txt"
done
TOPK_PLIES=$(awk '{for(i=1;i<=NF;i++) if ($i ~ /^topk_ranked_plies=/) {split($i,a,"="); s+=a[2]}} END {print s+0}' \
  "$ART/exploration-topk3.txt")
MARGIN_SINGLETONS=$(awk '{for(i=1;i<=NF;i++) if ($i ~ /^margin_singleton_plies=/) {split($i,a,"="); s+=a[2]}} END {print s+0}' \
  "$ART/exploration-topk3.txt")
UNIF_PLIES=$(awk '{for(i=1;i<=NF;i++) if ($i ~ /^topk_ranked_plies=/) {split($i,a,"="); s+=a[2]}} END {print s+0}' \
  "$ART/exploration-uniform.txt")
[ "$TOPK_PLIES" -gt 0 ] || die "TOPK3 arm ranked no ply — the flag did not fire"
[ "$MARGIN_SINGLETONS" -gt 0 ] || die "explore-margin never constrained TOPK3"
[ "$UNIF_PLIES" -eq 0 ] || die "UNIFORM arm ranked plies — the arms are not distinct"
say "  génération ✓ : topk_ranked_plies=$TOPK_PLIES, margin_singletons=$MARGIN_SINGLETONS"

phase merge-split-and-fit-both-arms
for arm in uniform topk3; do
  pairs=()
  for shard in $(seq 0 $((SHARDS - 1))); do
    pairs+=(--pair "$W/$arm-s$shard.jnnw" "$W/$arm-s$shard.jsm")
  done
  python3 tools/selfplay_frontier.py merge "${pairs[@]}" --renamespace-nested \
    --out-data "$W/$arm.raw.jnnw" --out-meta "$W/$arm.raw.jsm" \
    --manifest "$ART/$arm-merge.json" > "$W/$arm-merge.log" 2>&1
  python3 tools/selfplay_frontier.py split \
    --data "$W/$arm.raw.jnnw" --meta "$W/$arm.raw.jsm" \
    --out-data "$W/$arm.fit.jnnw" --out-meta "$W/$arm.fit.jsm" \
    --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
    --manifest "$ART/$arm-split.json" > "$W/$arm-split.log" 2>&1
  env PYTHONPATH="$GEOM:pattern_jass/tools" \
    python3 jobs/tools/l3_bucket_visits.py --data "$W/$arm.raw.jnnw" \
    --out "$ART/$arm-coverage.json" > "$W/$arm-coverage.log" 2>&1
  gzip -n -c "$W/$arm.raw.jnnw" > "$ART/$arm.jnnw.gz"
  gzip -n -c "$W/$arm.raw.jsm"  > "$ART/$arm.jsm.gz"
done
for arm in uniform topk3; do
  HOLD=$("$W/venv/bin/python" -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["holdout_records"])' \
    "$ART/$arm-split.json")
  [ "$HOLD" -gt 0 ] || die "$arm holdout missing"
  "$J" --dump-eval-features "$W/$arm.fit.jnnw" "$W/$arm.feat" \
    > "$W/$arm-features.log" 2>&1
  set +e
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
    timeout "$FIT_TIMEOUT" \
    "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
    --data "$W/$arm.fit.jnnw" --feat "$W/$arm.feat" --out "$W/$arm.pjtw" \
    --target wdl --loss logistic --color-fold --tempo-stage \
    --warm-start "$W/TURNOVER.pjtw" --holdout-count "$HOLD" \
    --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
    --lbfgs-maxcor "$LBFGS_MAXCOR" --lbfgs-gtol "$LBFGS_GTOL" \
    --optimizer-report "$ART/$arm-optimizer.json" \
    > "$W/fit-$arm.log" 2>&1
  FIT_RC=$?
  set -e
  [ -s "$W/$arm.pjtw" ] && gzip -n -c "$W/$arm.pjtw" > "$ART/$arm.pjtw.gz"
  [ "$FIT_RC" -eq 0 ] || die "$arm fit failed rc=$FIT_RC; checkpoint preserved"
  "$W/venv/bin/python" - "$ART/$arm-optimizer.json" <<'PY' ||
import json
import sys
if not json.load(open(sys.argv[1])).get("success"):
    raise SystemExit(1)
PY
    die "$arm optimiser did not converge"
done
say "  deux bras fittés et convergés"

phase publish-certificate
"$W/venv/bin/python" - "$W" "$ART" "$EXPECTED_CODE_SHA" "$RECORDS" \
  "$PLAY_DEPTH" "$EXPLORE_EPS" "$EXPLORE_DECAY" "$TOPK" "$EXPLORE_MARGIN" <<'PY'
import hashlib
import json
import pathlib
import re
import sys

w, art = map(pathlib.Path, sys.argv[1:3])
code_sha = sys.argv[3]
records, play_depth, eps, decay, topk, margin = (int(x) for x in sys.argv[4:10])


def counters(arm):
    """Somme les compteurs EXPLORATION de tous les shards du bras."""
    text = (art / f"exploration-{arm}.txt").read_text()
    keys = ("eps_events", "eps_changed_best", "play_plies",
            "topk_ranked_plies", "margin_singleton_plies", "games")
    out = {k: 0 for k in keys}
    for line in text.splitlines():
        for tok in line.split():
            k, _, v = tok.partition("=")
            if k in out:
                out[k] += int(v)
    out["eps_rate_pct"] = (round(100.0 * out["eps_events"] / out["play_plies"], 3)
                           if out["play_plies"] else None)
    out["changed_best_share"] = (round(out["eps_changed_best"] / out["eps_events"], 3)
                                 if out["eps_events"] else None)
    return out


arms = {}
for arm in ("uniform", "topk3"):
    cov = json.load(open(art / f"{arm}-coverage.json"))
    opt = json.load(open(art / f"{arm}-optimizer.json"))
    log = (w / f"fit-{arm}.log").read_text(errors="replace")
    m = re.search(r"HOLDOUT_LOGLOSS[ =:]+([0-9.]+)", log)
    arms[arm] = {
        "model_sha256": hashlib.sha256(
            (w / f"{arm}.pjtw").read_bytes()).hexdigest(),
        "exploration": counters(arm),
        "coverage": {
            "visited_buckets": cov["coverage"]["visited_buckets"],
            "visited_pct": round(100.0 * cov["coverage"]["coverage_fraction"], 3),
            "gini": cov["concentration"]["gini"],
            "buckets_ge_100": cov["coverage"]["buckets_with_at_least"]["ge_100"],
        },
        "fit": {"iterations": opt.get("nit"), "converged": opt.get("success"),
                "holdout_logloss": float(m.group(1)) if m else None},
    }

payload = {
    "schema": 1,
    "verdict": "L3_PURE_EXPLORE_TOPK_ARMS_READY",
    "code_sha": code_sha,
    "question": "does exploration noise on plausible moves beat uniform noise",
    "design": {
        "single_factor": (
            "exploration policy: uniform legal move vs top-3 within "
            f"{margin} centipawns of best"
        ),
        "records_per_arm": records, "play_depth": play_depth,
        "explore_eps": eps, "explore_decay_plies": decay,
        "topk": topk, "explore_margin": margin,
        "identical_across_arms": ["parent", "seed", "openings", "volume",
                                  "depth", "L2", "warm start", "split seed"],
        "declared_deviation": "100% fresh, no replay memory, on BOTH arms — "
                              "halving the exposure to the factor under test "
                              "would only make it harder to detect; the cost "
                              "is that neither arm is directly comparable to "
                              "TURNOVER, which had memory",
    },
    "arms": arms,
    "readout_required": "TOPK3 vs UNIFORM, views summed, n=6000 — this job "
                        "produces models, it does not measure strength",
    "promotion_authorized": False,
    "automatic_next_job": None,
}
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
(art / "JASS_CONTROL_SUMMARY.json").write_text(serialized)
(art / "VERDICT__L3_PURE_EXPLORE_TOPK_ARMS_READY").write_text(
    "L3_PURE_EXPLORE_TOPK_ARMS_READY\n")
(art / "PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")

for arm, a in arms.items():
    e, c, f = a["exploration"], a["coverage"], a["fit"]
    print(f"  {arm:8s} eps={e['eps_rate_pct']}% sur {e['play_plies']} plies, "
          f"ranked={e['topk_ranked_plies']}, "
          f"singletons={e['margin_singleton_plies']}, "
          f"coup changé {e['changed_best_share']}")
    print(f"           couverture {c['visited_pct']}% gini {c['gini']} "
          f"| fit {f['iterations']} it, holdout {f['holdout_logloss']}")
PY
phase complete
say "L3_PURE_EXPLORE_TOPK_ARMS_READY promotion=false automatic_next_job=null"
