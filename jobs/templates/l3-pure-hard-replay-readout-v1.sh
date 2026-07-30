#!/usr/bin/env bash
# L3-PURE — independent causal readout: HARD_REPLAY vs UNIFORM_REPLAY.
#
# The source job must certify two converged 2M fits which share their parent,
# fresh corpus, split, holdout and optimizer settings. The sole training
# factor is historical replay selection (failed_conversion versus uniform).
# This readout uses a new disjoint paired opening pool, Q00 d9 and native
# 0.1 s, plus paired P3/P4 conversion against the corrected historical
# defender. Holdout never selects an arm. No promotion or automatic chaining.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${SOURCE_PREFIX:?}"; : "${EXPECTED_SOURCE_JOB:?}"
: "${EXPECTED_SOURCE_ATTEMPT:?}"; : "${EXPECTED_SOURCE_CODE_SHA:?}"
: "${EXPECTED_UNIFORM_MODEL_SHA:?}"; : "${EXPECTED_HARD_MODEL_SHA:?}"
: "${GAUGE_PREFIX:?}"; : "${EXPECTED_GAUGE_JOB:?}"
: "${EXPECTED_GAUGE_ATTEMPT:?}"; : "${EXPECTED_GAUGE_CODE_SHA:?}"
: "${PRIOR_OPENINGS_PREFIX:?}"; : "${EXPECTED_PRIOR_OPENINGS_JOB:?}"
: "${EXPECTED_PRIOR_OPENINGS_ATTEMPT:?}"; : "${EXPECTED_PRIOR_OPENINGS_CODE_SHA:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"
IN="$JASS_RESULT_DIR/inputs"; GEOM8="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART/force" "$ART/conversion" "$IN" "$GEOM8"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/stage.txt"
: > "$RES"; echo preflight > "$STAGE"

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
        for file in "$ART"/force/*.json "$ART"/conversion/*.json; do
          [ -e "$file" ] || continue
          printf 'done_%s\n' "$(basename "$file" .json)"
        done
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 60
    done
  ) &
  MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build8" "$W/build32fixed" "$W/fixed-defender-code" \
    "$IN" "$GEOM8" "$W"/gate-* 2>/dev/null || true
  rm -f "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

NOPEN="${NOPEN:-2500}"
OPENING_CANDIDATES="${OPENING_CANDIDATES:-10000}"
OPENING_SEED="${OPENING_SEED:-1069001}"
GAMES_PER_VIEW=$((NOPEN * 2))
NSH_GATE="${NSH_GATE:-12}"; PAR_GATE="${PAR_GATE:-12}"
NSH_CONV="${NSH_CONV:-4}"; CONV_DEPTH="${CONV_DEPTH:-10}"
TARGET_PER_STRATUM="${TARGET_PER_STRATUM:-300}"
FORCE_DEPTH=9; MOVETIME=0.1; CACHE_MB=128
GEN2_GZ_SHA="01cc3ea59e9cc3ced1910d4d9054f88f92c1c4d9d220d5f28b0ebaaad33681a0"
P3_GAUGE_SHA="cd92710fec7934d113ccade22180d4cddf029b084dd20c8fa9e30ca686767c91"
P4_GAUGE_SHA="0d925c4fbd7e7928bf6d86bd2cd40f796ee6805e0010e51d5d6483986da2a1ac"
FIXED_DEFENDER_CODE_SHA="9c1d1e8eaaa5b9bbd86105f7f9807a3033784186"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$(nproc)" -ge 16 ] || die "readout requires at least 16 logical CPUs"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -ge 8000 ] ||
  die "need 8 GiB free"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
[ "$NOPEN" -ge 2500 ] || die "powered readout requires at least 2500 openings"
grep -q "root_is_drawn" src/search.cpp || die "engine predates drawn-root fix"
monitor

stage fetch-and-authenticate-immutable-inputs
python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=arms-summary.json \
  --file artefacts/control.pjtw.gz=UNIFORM_REPLAY.pjtw.gz \
  --file artefacts/treatment.pjtw.gz=HARD_REPLAY.pjtw.gz \
  --file artefacts/hard-replay-causal-assembly.json=assembly.json \
  --out-dir "$IN" --report "$ART/verified-arms.json" \
  > "$W/fetch-arms.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$GAUGE_PREFIX" \
  --file artefacts/p3_mince-stable.jnnw.gz=p3.jnnw.gz \
  --file artefacts/p4_egal-stable.jnnw.gz=p4.jnnw.gz \
  --out-dir "$IN" --report "$ART/verified-gauge.json" \
  > "$W/fetch-gauge.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$PRIOR_OPENINGS_PREFIX" \
  --file artefacts/topk-readout-openings.fen=prior-1024-openings.fen \
  --out-dir "$IN" --report "$ART/verified-prior-openings.json" \
  > "$W/fetch-prior-openings.log" 2>&1
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$IN" \
  --report "$ART/verified-fixed-inputs.json" \
  > "$W/fetch-fixed-inputs.log" 2>&1

python3 - "$ART/verified-arms.json" "$ART/verified-gauge.json" \
  "$ART/verified-prior-openings.json" "$IN/arms-summary.json" \
  "$EXPECTED_SOURCE_JOB" "$EXPECTED_SOURCE_ATTEMPT" \
  "$EXPECTED_SOURCE_CODE_SHA" "$EXPECTED_GAUGE_JOB" \
  "$EXPECTED_GAUGE_ATTEMPT" "$EXPECTED_GAUGE_CODE_SHA" \
  "$EXPECTED_PRIOR_OPENINGS_JOB" "$EXPECTED_PRIOR_OPENINGS_ATTEMPT" \
  "$EXPECTED_PRIOR_OPENINGS_CODE_SHA" "$EXPECTED_UNIFORM_MODEL_SHA" \
  "$EXPECTED_HARD_MODEL_SHA" <<'PY'
import json
import sys

arms_report, gauge_report, openings_report, summary = (
    json.load(open(path)) for path in sys.argv[1:5]
)
(
    source_job, source_attempt, source_code,
    gauge_job, gauge_attempt, gauge_code,
    openings_job, openings_attempt, openings_code,
    uniform_sha, hard_sha,
) = sys.argv[5:16]

def require(condition, message):
    if not condition:
        raise SystemExit(message)

for report, identity, label in (
    (arms_report, (source_job, source_attempt, source_code), "arms"),
    (gauge_report, (gauge_job, gauge_attempt, gauge_code), "gauge"),
    (openings_report, (openings_job, openings_attempt, openings_code), "openings"),
):
    require(
        report.get("job_id") == identity[0]
        and report.get("attempt_id") == identity[1]
        and report.get("code_sha") == identity[2]
        and report.get("result_state") == "completed"
        and report.get("exit_code") == 0,
        f"{label} source identity/state mismatch",
    )
require(
    summary.get("verdict") == "L3_PURE_HARD_REPLAY_CAUSAL_AB_ARMS_READY"
    and summary.get("code_sha") == source_code
    and summary.get("primary_contrast") == "HARD_REPLAY minus UNIFORM_REPLAY",
    "arms summary identity/verdict mismatch",
)
design = summary.get("design", {})
require(
    design.get("single_factor") == "historical_replay_selection_policy"
    and design.get("same_parent") is True
    and design.get("same_fresh_corpus") is True
    and design.get("same_fit") is True
    and design.get("same_holdout") is True,
    "causal design drift",
)
require(summary.get("promotion_authorized") is False, "source promotion drift")
require(summary.get("automatic_next_job", "missing") is None, "source chaining drift")
require(summary.get("external_teacher_inputs") == 0, "teacher input drift")
for arm, expected in (("UNIFORM_REPLAY", uniform_sha), ("HARD_REPLAY", hard_sha)):
    require(
        summary.get("arms", {}).get(arm, {}).get("model_sha256") == expected,
        f"{arm} model hash mismatch",
    )
    require(
        summary.get("arms", {}).get(arm, {}).get("optimizer", {}).get("success")
        is True,
        f"{arm} optimizer did not converge",
    )
PY

gunzip -c "$IN/UNIFORM_REPLAY.pjtw.gz" > "$W/UNIFORM_REPLAY.pjtw"
gunzip -c "$IN/HARD_REPLAY.pjtw.gz" > "$W/HARD_REPLAY.pjtw"
gunzip -c "$IN/gen2.pjtw.gz" > "$W/GEN2.pjtw"
gunzip -c "$IN/p3.jnnw.gz" > "$W/p3_mince.jnnw"
gunzip -c "$IN/p4.jnnw.gz" > "$W/p4_egal.jnnw"
[ "$(sha256sum "$W/UNIFORM_REPLAY.pjtw" | awk '{print $1}')" = "$EXPECTED_UNIFORM_MODEL_SHA" ] ||
  die "UNIFORM_REPLAY model hash drift"
[ "$(sha256sum "$W/HARD_REPLAY.pjtw" | awk '{print $1}')" = "$EXPECTED_HARD_MODEL_SHA" ] ||
  die "HARD_REPLAY model hash drift"
[ "$(sha256sum "$IN/gen2.pjtw.gz" | awk '{print $1}')" = "$GEN2_GZ_SHA" ] ||
  die "GEN2 gzip hash drift"
[ "$(sha256sum "$W/p3_mince.jnnw" | awk '{print $1}')" = "$P3_GAUGE_SHA" ] ||
  die "P3 gauge hash drift"
[ "$(sha256sum "$W/p4_egal.jnnw" | awk '{print $1}')" = "$P4_GAUGE_SHA" ] ||
  die "P4 gauge hash drift"
say "  immutable inputs authenticated"

stage build-repaired-engines
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM8/patterns.py"
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
cmake --build "$W/build8" -j8 --target jass jass_tests > "$W/build8.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB \
  ctest --test-dir "$W/build8" --output-on-failure > "$W/ctest8.log" 2>&1
mkdir "$W/fixed-defender-code"
git archive "$FIXED_DEFENDER_CODE_SHA" | tar -x -C "$W/fixed-defender-code"
grep -q "root_is_drawn" "$W/fixed-defender-code/src/search.cpp" ||
  die "fixed defender predates drawn-root repair"
(cd "$W/fixed-defender-code" &&
  python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 \
    > "$W/gen32fixed.log" 2>&1)
cmake -S "$W/fixed-defender-code" -B "$W/build32fixed" $FLAGS \
  > "$W/cmake32fixed.log" 2>&1
cmake --build "$W/build32fixed" -j8 --target jass \
  > "$W/build32fixed.log" 2>&1
J8="$W/build8/jass"; J32FIXED="$W/build32fixed/jass"
[ "$("$J8" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "king-capture witness failed"
say "  current 8cf attacker and corrected historical defender built"

stage select-fresh-disjoint-openings
"$J8" --gen-opening-pool "$OPENING_CANDIDATES" "$W/open-candidates.fen" \
  8 32 20 "$OPENING_SEED" > "$W/open-candidates.log" 2>&1
python3 jobs/tools/select_independent_opening_pool.py \
  --candidates "$W/open-candidates.fen" --expected "$NOPEN" \
  --exclude data/dilf_combinations.fen \
  --exclude "$IN/prior-1024-openings.fen" \
  --generator-seed "$OPENING_SEED" \
  --out "$ART/hard-replay-readout-openings.fen" \
  --manifest "$ART/hard-replay-readout-openings.json" \
  > "$W/select-openings.log" 2>&1
cp "$ART/hard-replay-readout-openings.fen" "$W/open-eval.fen"
python3 - "$ART/hard-replay-readout-openings.json" "$NOPEN" "$OPENING_SEED" <<'PY'
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
say "  selected $NOPEN unique openings disjoint from DILF and readout 1024"

run_gate(){
  local view="$1"; local args=()
  [ "$view" = q00 ] && args=(--depth "$FORCE_DEPTH") ||
    args=(--movetime "$MOVETIME")
  timeout 21600 python3 jobs/tools/run_jass_gate_bounded.py \
    --jass-a "$J8" --jass-b "$J8" \
    --pattern-a "$W/HARD_REPLAY.pjtw" \
    --pattern-b "$W/UNIFORM_REPLAY.pjtw" \
    --search-params-a "$Q00" --search-params-b "$Q00" \
    --openings-file "$W/open-eval.fen" "${args[@]}" --pairs 1 \
    --max-plies 160 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout 18000 --game-timeout 180 --work-dir "$W/gate-$view" \
    --out "$ART/force/force-$view-HARD_REPLAY-vs-UNIFORM_REPLAY.json" \
    > "$W/force-$view.log" 2>&1
}

stage play-independent-force
for view in q00 native; do
  stage "force-$view-${GAMES_PER_VIEW}-games"
  run_gate "$view" || die "$view force readout failed"
  say "  $view force cell complete"
done

wait_all(){
  local label="$1"; shift; local failures=0
  for pid in "$@"; do wait "$pid" || failures=$((failures + 1)); done
  [ "$failures" -eq 0 ] || die "$label: $failures workers failed"
}
run_conversion(){
  local arm="$1"; local stratum="$2"; local pool="$3"
  local pids=(); local inputs=()
  for shard in $(seq 0 $((NSH_CONV - 1))); do
    local out="$W/$arm-$stratum-$shard.json"; inputs+=("$out")
    timeout 14400 python3 jobs/tools/conv_fixed_wdl.py \
      --jass "$J8" --defender-jass "$J32FIXED" \
      --pattern "$W/$arm.pjtw" --defender-pattern "$W/GEN2.pjtw" \
      --search-params "$Q00" --defender-search-params "$Q00" \
      --pool-jnnw "$pool" --depth "$CONV_DEPTH" --max-plies 260 \
      --shard "$shard" --nshards "$NSH_CONV" --out "$out" \
      > "$W/$arm-$stratum-$shard.log" 2>&1 &
    pids+=("$!")
  done
  wait_all "$arm $stratum conversion" "${pids[@]}"
  python3 jobs/tools/aggregate_conv_shards.py \
    --inputs "${inputs[@]}" --expected-shards "$NSH_CONV" \
    --expected-records "$TARGET_PER_STRATUM" --max-error-rate 0.08 \
    --stratum "$stratum" --require-position-results \
    --out "$ART/conversion/$arm-$stratum.json" \
    > "$W/aggregate-$arm-$stratum.log" 2>&1
}

stage paired-corrected-defender-conversion
for stratum in p3_mince p4_egal; do
  pool="$W/$stratum.jnnw"
  for arm in UNIFORM_REPLAY HARD_REPLAY; do
    stage "conversion-$stratum-$arm"
    run_conversion "$arm" "$stratum" "$pool"
  done
done

stage aggregate-preregistered-readout
python3 -m jobs.tools.l3_hard_replay_readout \
  --force-dir "$ART/force" --conversion-dir "$ART/conversion" \
  --training-summary "$IN/arms-summary.json" \
  --opening-manifest "$ART/hard-replay-readout-openings.json" \
  --expected-games-per-view "$GAMES_PER_VIEW" --expected-openings "$NOPEN" \
  --code-sha "$EXPECTED_CODE_SHA" \
  --source-job "$EXPECTED_SOURCE_JOB" \
  --source-attempt "$EXPECTED_SOURCE_ATTEMPT" \
  --source-code-sha "$EXPECTED_SOURCE_CODE_SHA" \
  --uniform-model-sha "$EXPECTED_UNIFORM_MODEL_SHA" \
  --hard-model-sha "$EXPECTED_HARD_MODEL_SHA" \
  --out "$ART/hard-replay-vs-uniform-readout.json" \
  --summary-out "$ART/JASS_CONTROL_SUMMARY.json"
VERDICT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["verdict"])' \
  "$ART/JASS_CONTROL_SUMMARY.json")"
printf '%s\n' "$VERDICT" > "$ART/VERDICT__$VERDICT"
printf '%s\n' PROMOTION_AUTHORIZED__FALSE > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf '%s\n' AUTOMATIC_NEXT_JOB__NULL > "$ART/AUTOMATIC_NEXT_JOB__NULL"
python3 - "$ART/JASS_CONTROL_SUMMARY.json" <<'PY' | tee -a "$RES"
import json
import sys
summary = json.load(open(sys.argv[1]))
for view, row in summary["force"].items():
    print(
        f"  {view}: n={row['n']} "
        f"{row['wins_hard_replay']}-{row['draws']}-"
        f"{row['wins_uniform_replay']} "
        f"rate={row['rate_hard_replay']:.6f} elo={row['elo']:+.2f}"
    )
row = summary["force_views_summed"]
print(
    f"  summed: n={row['n']} "
    f"{row['wins_hard_replay']}-{row['draws']}-"
    f"{row['wins_uniform_replay']} "
    f"rate={row['rate_hard_replay']:.6f} elo={row['elo']:+.2f}"
)
print(f"  CI90={row['ci90']} CI95={row['ci95']}")
print(f"  verdict={summary['verdict']}")
PY
stage complete
say "$VERDICT promotion=false automatic_next_job=null"
