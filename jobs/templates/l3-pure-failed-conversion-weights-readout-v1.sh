#!/usr/bin/env bash
# L3-PURE — independent FAILED_X2 versus UNWEIGHTED sample-weight readout.
#
# The fit-only arms are authenticated before 6000 paired-colour games on 1500
# new openings disjoint from all earlier L3-PURE signal readouts. This job
# measures strength; it cannot promote a model or chain another job.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${SOURCE_PREFIX:?}"; : "${EXPECTED_SOURCE_JOB:?}"
: "${EXPECTED_SOURCE_ATTEMPT:?}"; : "${EXPECTED_SOURCE_CODE_SHA:?}"
: "${EXPECTED_CONTROL_MODEL_SHA:?}"; : "${EXPECTED_TREATMENT_MODEL_SHA:?}"
: "${TOPK_OPENINGS_PREFIX:?}"; : "${EXPECTED_TOPK_OPENINGS_JOB:?}"
: "${EXPECTED_TOPK_OPENINGS_ATTEMPT:?}"; : "${EXPECTED_TOPK_OPENINGS_CODE_SHA:?}"
: "${HARD_OPENINGS_PREFIX:?}"; : "${EXPECTED_HARD_OPENINGS_JOB:?}"
: "${EXPECTED_HARD_OPENINGS_ATTEMPT:?}"; : "${EXPECTED_HARD_OPENINGS_CODE_SHA:?}"
: "${REVERSE_OPENINGS_PREFIX:?}"; : "${EXPECTED_REVERSE_OPENINGS_JOB:?}"
: "${EXPECTED_REVERSE_OPENINGS_ATTEMPT:?}"
: "${EXPECTED_REVERSE_OPENINGS_CODE_SHA:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
IN="$JASS_RESULT_DIR/inputs"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART" "$IN" "$GEOM" "$ART/force"
RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
STAGE="$W/stage.txt"
: > "$RES"
echo preflight > "$STAGE"

say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "stage=$1"; }
MON=""
monitor(){
  (
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'stage=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        awk '/MemAvailable:/{printf "mem_available_mb=%d\n",$2/1024}' /proc/meminfo
        for file in "$ART"/force/*.json; do
          [ -e "$file" ] || continue
          printf 'done_%s\n' "$(basename "$file" .json)"
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
  rm -rf "$W/build8" "$IN" "$GEOM" "$W"/gate-* 2>/dev/null || true
  rm -f "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

NOPEN="${NOPEN:-1500}"
OPENING_CANDIDATES="${OPENING_CANDIDATES:-12000}"
OPENING_SEED="${OPENING_SEED:-1094001}"
GAMES_PER_VIEW=$((NOPEN * 2))
NSH_GATE=12
PAR_GATE=12
FORCE_DEPTH=9
MOVETIME=0.1
CACHE_MB=128
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$(nproc)" -ge 12 ] || die "HOME requires at least 12 logical CPUs"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -ge 8000 ] ||
  die "need 8 GiB free"
[ "$NOPEN" -eq 1500 ] || die "readout power drift"
[ "$OPENING_SEED" -eq 1094001 ] || die "opening seed drift"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
grep -q "root_is_drawn" src/search.cpp || die "engine predates drawn-root fix"
monitor

stage fetch-and-authenticate-immutable-inputs
python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=arms-summary.json \
  --file artefacts/control.pjtw.gz=CONTROL.pjtw.gz \
  --file artefacts/treatment.pjtw.gz=TREATMENT.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-arms.json" \
  > "$W/fetch-arms.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TOPK_OPENINGS_PREFIX" \
  --file artefacts/topk-readout-openings.fen=prior-topk-openings.fen \
  --out-dir "$IN" --report "$ART/verified-topk-openings.json" \
  > "$W/fetch-topk-openings.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$HARD_OPENINGS_PREFIX" \
  --file artefacts/hard-replay-readout-openings.fen=prior-hard-openings.fen \
  --out-dir "$IN" --report "$ART/verified-hard-openings.json" \
  > "$W/fetch-hard-openings.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$REVERSE_OPENINGS_PREFIX" \
  --file artefacts/reverse-seed-readout-openings.fen=prior-reverse-openings.fen \
  --out-dir "$IN" --report "$ART/verified-reverse-openings.json" \
  > "$W/fetch-reverse-openings.log" 2>&1

python3 - "$ART/verified-arms.json" "$ART/verified-topk-openings.json" \
  "$ART/verified-hard-openings.json" "$ART/verified-reverse-openings.json" \
  "$IN/arms-summary.json" "$EXPECTED_SOURCE_JOB" "$EXPECTED_SOURCE_ATTEMPT" \
  "$EXPECTED_SOURCE_CODE_SHA" "$EXPECTED_TOPK_OPENINGS_JOB" \
  "$EXPECTED_TOPK_OPENINGS_ATTEMPT" "$EXPECTED_TOPK_OPENINGS_CODE_SHA" \
  "$EXPECTED_HARD_OPENINGS_JOB" "$EXPECTED_HARD_OPENINGS_ATTEMPT" \
  "$EXPECTED_HARD_OPENINGS_CODE_SHA" "$EXPECTED_REVERSE_OPENINGS_JOB" \
  "$EXPECTED_REVERSE_OPENINGS_ATTEMPT" "$EXPECTED_REVERSE_OPENINGS_CODE_SHA" \
  "$EXPECTED_CONTROL_MODEL_SHA" "$EXPECTED_TREATMENT_MODEL_SHA" <<'PY'
import json
import sys

arms_report, topk_report, hard_report, reverse_report, summary = (
    json.load(open(path)) for path in sys.argv[1:6]
)
(
    source_job, source_attempt, source_code,
    topk_job, topk_attempt, topk_code,
    hard_job, hard_attempt, hard_code,
    reverse_job, reverse_attempt, reverse_code,
    control_sha, treatment_sha,
) = sys.argv[6:20]

def require(condition, message):
    if not condition:
        raise SystemExit(message)

for report, identity, label in (
    (arms_report, (source_job, source_attempt, source_code), "arms"),
    (topk_report, (topk_job, topk_attempt, topk_code), "topk openings"),
    (hard_report, (hard_job, hard_attempt, hard_code), "hard openings"),
    (
        reverse_report,
        (reverse_job, reverse_attempt, reverse_code),
        "reverse openings",
    ),
):
    require(
        report.get("job_id") == identity[0]
        and report.get("attempt_id") == identity[1]
        and report.get("code_sha") == identity[2]
        and report.get("result_state") == "completed"
        and report.get("exit_code") == 0,
        f"{label} source identity/state mismatch",
    )
design = summary.get("design", {})
arms = summary.get("arms", {})
require(
    summary.get("verdict")
    == "L3_PURE_FAILED_CONVERSION_WEIGHTS_CAUSAL_AB_ARMS_READY"
    and summary.get("code_sha") == source_code
    and summary.get("primary_contrast") == "FAILED_X2 minus UNWEIGHTED",
    "arms summary identity/verdict mismatch",
)
require(
    design.get("single_factor") == "train_failed_conversion_weight"
    and design.get("control_weight") == 1.0
    and design.get("treatment_weight") == 2.0
    and design.get("same_records") is True
    and design.get("same_opening_split") is True
    and design.get("same_feature_matrix") is True
    and design.get("same_warm_start") is True
    and design.get("same_fit") is True
    and design.get("holdout_weighted") is False
    and design.get("oversampling") is False
    and design.get("control_reproduced_historical_model") is True,
    "causal design drift",
)
require(summary.get("scientific_result") is False, "source result-state drift")
require(summary.get("promotion_authorized") is False, "source promotion drift")
require(summary.get("automatic_next_job", "missing") is None, "source chaining drift")
require(summary.get("external_teacher_inputs") == 0, "teacher input drift")
for arm, expected, uniform, sw_used in (
    ("UNWEIGHTED", control_sha, True, False),
    ("FAILED_X2", treatment_sha, False, True),
):
    row = arms.get(arm, {})
    trainer = row.get("trainer_weights", {})
    require(row.get("model_sha256") == expected, f"{arm} model hash mismatch")
    require(row.get("optimizer", {}).get("success") is True,
            f"{arm} optimizer did not converge")
    require(
        trainer.get("split", {}).get("holdout_weighted") is False
        and trainer.get("optimizer", {}).get("uniform_after_normalization")
        is uniform
        and trainer.get("optimizer", {}).get("sw_all_used") is sw_used,
        f"{arm} weight path mismatch",
    )
require(
    summary.get("training_coverage", {}).get("common_to_both_arms") is True,
    "common training coverage missing",
)
PY

gunzip -c "$IN/CONTROL.pjtw.gz" > "$W/CONTROL.pjtw"
gunzip -c "$IN/TREATMENT.pjtw.gz" > "$W/TREATMENT.pjtw"
[ "$(sha256sum "$W/CONTROL.pjtw" | awk '{print $1}')" = \
  "$EXPECTED_CONTROL_MODEL_SHA" ] || die "CONTROL model hash drift"
[ "$(sha256sum "$W/TREATMENT.pjtw" | awk '{print $1}')" = \
  "$EXPECTED_TREATMENT_MODEL_SHA" ] || die "TREATMENT model hash drift"
say "  immutable fit-only arms and prior opening pools authenticated"

stage build-repaired-8cf-engine
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf \
  > "$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
cmake --build "$W/build8" -j8 --target jass jass_tests \
  > "$W/build8.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB \
  ctest --test-dir "$W/build8" --output-on-failure > "$W/ctest8.log" 2>&1
J8="$W/build8/jass"
[ "$("$J8" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "king-capture witness failed"
say "  one repaired 8cf engine built for both arms"

stage select-fresh-disjoint-openings
"$J8" --gen-opening-pool "$OPENING_CANDIDATES" "$W/open-candidates.fen" \
  8 32 20 "$OPENING_SEED" > "$W/open-candidates.log" 2>&1
python3 jobs/tools/select_independent_opening_pool.py \
  --candidates "$W/open-candidates.fen" --expected "$NOPEN" \
  --exclude data/dilf_combinations.fen \
  --exclude "$IN/prior-topk-openings.fen" \
  --exclude "$IN/prior-hard-openings.fen" \
  --exclude "$IN/prior-reverse-openings.fen" \
  --generator-seed "$OPENING_SEED" \
  --out "$ART/failed-x2-readout-openings.fen" \
  --manifest "$ART/failed-x2-readout-openings.json" \
  > "$W/select-openings.log" 2>&1
cp "$ART/failed-x2-readout-openings.fen" "$W/open-eval.fen"
python3 - "$ART/failed-x2-readout-openings.json" "$NOPEN" \
  "$OPENING_SEED" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1]))
if (
    manifest.get("records") != int(sys.argv[2])
    or manifest.get("unique_records") != int(sys.argv[2])
    or manifest.get("overlap_records") != 0
    or manifest.get("generator_seed") != int(sys.argv[3])
):
    raise SystemExit("fresh opening manifest mismatch")
PY
say "  selected $NOPEN openings disjoint from DILF, 1024, 1076 and 1091"

run_gate(){
  local view="$1"; local args=()
  [ "$view" = q00 ] && args=(--depth "$FORCE_DEPTH") ||
    args=(--movetime "$MOVETIME")
  timeout 10800 python3 jobs/tools/run_jass_gate_bounded.py \
    --jass-a "$J8" --jass-b "$J8" \
    --pattern-a "$W/TREATMENT.pjtw" --pattern-b "$W/CONTROL.pjtw" \
    --search-params-a "$Q00" --search-params-b "$Q00" \
    --openings-file "$W/open-eval.fen" "${args[@]}" --pairs 1 \
    --max-plies 160 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout 9000 --game-timeout 180 --work-dir "$W/gate-$view" \
    --out "$ART/force/force-$view-FAILED_X2-vs-UNWEIGHTED.json" \
    > "$W/force-$view.log" 2>&1
}

stage play-independent-force
for view in q00 native; do
  stage "force-$view-${GAMES_PER_VIEW}-games"
  run_gate "$view" || die "$view force readout failed"
  say "  $view force cell complete"
done

stage aggregate-preregistered-readout
python3 -m jobs.tools.l3_failed_conversion_weights_readout \
  --force-dir "$ART/force" --training-summary "$IN/arms-summary.json" \
  --opening-manifest "$ART/failed-x2-readout-openings.json" \
  --expected-games-per-view "$GAMES_PER_VIEW" --expected-openings "$NOPEN" \
  --code-sha "$EXPECTED_CODE_SHA" --source-job "$EXPECTED_SOURCE_JOB" \
  --source-attempt "$EXPECTED_SOURCE_ATTEMPT" \
  --source-code-sha "$EXPECTED_SOURCE_CODE_SHA" \
  --control-model-sha "$EXPECTED_CONTROL_MODEL_SHA" \
  --treatment-model-sha "$EXPECTED_TREATMENT_MODEL_SHA" \
  --out "$ART/failed-x2-vs-unweighted-readout.json" \
  --summary-out "$ART/JASS_CONTROL_SUMMARY.json"
VERDICT="$(python3 -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["verdict"])' \
  "$ART/JASS_CONTROL_SUMMARY.json")"
printf '%s\n' "$VERDICT" > "$ART/VERDICT__$VERDICT"
printf '%s\n' SCIENTIFIC_RESULT__TRUE > "$ART/SCIENTIFIC_RESULT__TRUE"
printf '%s\n' PROMOTION_AUTHORIZED__FALSE > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf '%s\n' AUTOMATIC_NEXT_JOB__NULL > "$ART/AUTOMATIC_NEXT_JOB__NULL"
python3 - "$ART/JASS_CONTROL_SUMMARY.json" <<'PY' | tee -a "$RES"
import json
import sys

summary = json.load(open(sys.argv[1]))
for view, row in summary["force"].items():
    print(
        f"  {view}: n={row['n']} "
        f"{row['wins_treatment']}-{row['draws']}-{row['wins_control']} "
        f"rate={row['rate_treatment']:.6f} elo={row['elo']:+.2f}"
    )
row = summary["force_views_summed"]
print(
    f"  summed: n={row['n']} "
    f"{row['wins_treatment']}-{row['draws']}-{row['wins_control']} "
    f"rate={row['rate_treatment']:.6f} elo={row['elo']:+.2f}"
)
print(f"  CI90={row['ci90']} CI95={row['ci95']}")
print(f"  verdict={summary['verdict']}")
PY

stage complete
say "$VERDICT scientific_result=true promotion=false automatic_next_job=null"
