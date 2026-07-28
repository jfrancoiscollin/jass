#!/usr/bin/env bash
# L3-PURE — independent causal readout: TOPK3 versus UNIFORM.
#
# The two models come from the paired 2M/arm home-1017 corpora, fitted by
# home-1022.  The source summary, both models and both coverage reports are
# authenticated before play.  Both arms use one engine binary and the same
# fresh paired openings; the only training-policy contrast is TOPK K=3 with an
# explore margin of 50 versus uniform exploration.
#
# Q00 depth 9 and native 0.1 s are summed from raw W/D/L counts (not averaged).
# Holdout losses remain diagnostic only and never select either arm.
# No promotion and no automatic continuation.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"
: "${SOURCE_PREFIX:?}"; : "${EXPECTED_SOURCE_JOB:?}"
: "${EXPECTED_SOURCE_ATTEMPT:?}"; : "${EXPECTED_SOURCE_CODE_SHA:?}"
: "${MODEL_PREFLIGHT_PREFIX:?}"; : "${EXPECTED_MODEL_PREFLIGHT_JOB:?}"
: "${EXPECTED_MODEL_PREFLIGHT_ATTEMPT:?}"; : "${EXPECTED_MODEL_PREFLIGHT_CODE_SHA:?}"
: "${EXPECTED_UNIFORM_MODEL_SHA:?}"; : "${EXPECTED_TOPK3_MODEL_SHA:?}"
: "${PRIOR_OPENINGS_PREFIX:?}"; : "${EXPECTED_PRIOR_OPENINGS_JOB:?}"
: "${EXPECTED_PRIOR_OPENINGS_ATTEMPT:?}"; : "${EXPECTED_PRIOR_OPENINGS_CODE_SHA:?}"

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
        for f in "$ART"/force/*.json; do
          [ -e "$f" ] || continue
          printf 'done_%s\n' "$(basename "$f" .json)"
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

NOPEN=1500
OPENING_CANDIDATES=6000
OPENING_SEED="${OPENING_SEED:-1024001}"
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
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -ge 8000 ] ||
  die "need 8 GiB free"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
grep -q "root_is_drawn" src/search.cpp || die "engine predates drawn-root fix"
monitor

stage fetch-and-authenticate-immutable-inputs
python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=arms-summary.json \
  --file artefacts/uniform.pjtw.gz=UNIFORM.pjtw.gz \
  --file artefacts/topk3.pjtw.gz=TOPK3.pjtw.gz \
  --file artefacts/uniform-coverage.json=uniform-coverage.json \
  --file artefacts/topk3-coverage.json=topk3-coverage.json \
  --out-dir "$IN" --report "$ART/verified-arms.json" \
  > "$W/fetch-arms.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$MODEL_PREFLIGHT_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=model-preflight.json \
  --out-dir "$IN" --report "$ART/verified-model-preflight.json" \
  > "$W/fetch-model-preflight.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$PRIOR_OPENINGS_PREFIX" \
  --file artefacts/vol8m-eval-openings.fen=prior-1008-openings.fen \
  --out-dir "$IN" --report "$ART/verified-prior-openings.json" \
  > "$W/fetch-prior-openings.log" 2>&1

python3 - "$ART/verified-arms.json" "$ART/verified-model-preflight.json" \
  "$ART/verified-prior-openings.json" "$IN/arms-summary.json" \
  "$IN/model-preflight.json" "$EXPECTED_SOURCE_JOB" "$EXPECTED_SOURCE_ATTEMPT" \
  "$EXPECTED_SOURCE_CODE_SHA" "$EXPECTED_MODEL_PREFLIGHT_JOB" \
  "$EXPECTED_MODEL_PREFLIGHT_ATTEMPT" "$EXPECTED_MODEL_PREFLIGHT_CODE_SHA" \
  "$EXPECTED_PRIOR_OPENINGS_JOB" "$EXPECTED_PRIOR_OPENINGS_ATTEMPT" \
  "$EXPECTED_PRIOR_OPENINGS_CODE_SHA" "$EXPECTED_UNIFORM_MODEL_SHA" \
  "$EXPECTED_TOPK3_MODEL_SHA" <<'PY'
import json
import sys

arms_report, preflight_report, openings_report, arms, preflight = (
    json.load(open(path)) for path in sys.argv[1:6]
)
(
    source_job, source_attempt, source_code, preflight_job,
    preflight_attempt, preflight_code, openings_job, openings_attempt,
    openings_code, uniform_sha, topk3_sha,
) = sys.argv[6:17]

def require(condition, message):
    if not condition:
        raise SystemExit(message)

require(
    arms_report.get("job_id") == source_job
    and arms_report.get("attempt_id") == source_attempt
    and arms_report.get("code_sha") == source_code
    and arms_report.get("result_state") == "completed"
    and arms_report.get("exit_code") == 0,
    "arms source identity/state mismatch",
)
require(
    preflight_report.get("job_id") == preflight_job
    and preflight_report.get("attempt_id") == preflight_attempt
    and preflight_report.get("code_sha") == preflight_code
    and preflight_report.get("result_state") == "completed"
    and preflight_report.get("exit_code") == 0,
    "model preflight identity/state mismatch",
)
require(
    openings_report.get("job_id") == openings_job
    and openings_report.get("attempt_id") == openings_attempt
    and openings_report.get("code_sha") == openings_code
    and openings_report.get("result_state") == "completed",
    "prior opening source identity/state mismatch",
)
require(
    arms.get("verdict")
    == "L3_PURE_TOPK_CAUSAL_AB_ARMS_READY_FROM_1017_CORPORA",
    "arms verdict mismatch",
)
require(arms.get("code_sha") == source_code, "arms summary code SHA mismatch")
require(arms.get("promotion_authorized") is False, "arms promotion guard mismatch")
require(arms.get("automatic_next_job", "missing") is None, "arms continuation guard mismatch")
require(
    arms.get("source", {}).get("job_id")
    == "home-1017-l3-pure-topk-causal-ab-v2",
    "1017 corpus source mismatch",
)
require(
    arms.get("parent", {}).get("model_sha256")
    == "b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16",
    "TURNOVER parent mismatch",
)
require(
    preflight.get("verdict") == "L3_PURE_TOPK_READOUT_PREFLIGHT_READY",
    "model preflight verdict mismatch",
)
require(preflight.get("promotion_authorized") is False, "preflight promotion guard mismatch")
require(preflight.get("automatic_next_job", "missing") is None, "preflight continuation guard mismatch")
for arm, expected in (("uniform", uniform_sha), ("topk3", topk3_sha)):
    require(
        arms.get("arms", {}).get(arm, {}).get("model_sha256") == expected,
        f"{arm} summary hash mismatch",
    )
    require(
        arms.get("arms", {}).get(arm, {}).get("optimizer", {}).get("success") is True,
        f"{arm} optimizer did not converge",
    )
    require(
        preflight.get("model_sha256", {}).get(arm) == expected,
        f"{arm} preflight hash mismatch",
    )
PY

gunzip -c "$IN/UNIFORM.pjtw.gz" > "$W/UNIFORM.pjtw"
gunzip -c "$IN/TOPK3.pjtw.gz" > "$W/TOPK3.pjtw"
[ "$(sha256sum "$W/UNIFORM.pjtw" | awk '{print $1}')" = "$EXPECTED_UNIFORM_MODEL_SHA" ] ||
  die "UNIFORM model hash drift"
[ "$(sha256sum "$W/TOPK3.pjtw" | awk '{print $1}')" = "$EXPECTED_TOPK3_MODEL_SHA" ] ||
  die "TOPK3 model hash drift"
say "  inputs authenticated: UNIFORM=$EXPECTED_UNIFORM_MODEL_SHA TOPK3=$EXPECTED_TOPK3_MODEL_SHA"

stage build-8cf-engine
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
cmake --build "$W/build8" -j8 --target jass jass_tests > "$W/build8.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB \
  ctest --test-dir "$W/build8" --output-on-failure > "$W/ctest8.log" 2>&1
J8="$W/build8/jass"
[ "$("$J8" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "king-capture witness failed"
say "  engine built: one 8cf binary for both arms"

stage select-fresh-disjoint-openings
"$J8" --gen-opening-pool "$OPENING_CANDIDATES" "$W/open-candidates.fen" \
  8 32 20 "$OPENING_SEED" > "$W/open-candidates.log" 2>&1
python3 jobs/tools/select_independent_opening_pool.py \
  --candidates "$W/open-candidates.fen" --expected "$NOPEN" \
  --exclude data/dilf_combinations.fen \
  --exclude "$IN/prior-1008-openings.fen" \
  --generator-seed "$OPENING_SEED" \
  --out "$ART/topk-readout-openings.fen" \
  --manifest "$ART/topk-readout-openings.json" \
  > "$W/select-openings.log" 2>&1
cp "$ART/topk-readout-openings.fen" "$W/open-eval.fen"
python3 - "$ART/topk-readout-openings.json" "$NOPEN" <<'PY'
import json
import sys
manifest = json.load(open(sys.argv[1]))
expected = int(sys.argv[2])
if (
    manifest.get("records") != expected
    or manifest.get("unique_records") != expected
    or manifest.get("overlap_records") != 0
):
    raise SystemExit("fresh opening manifest mismatch")
PY
say "  fresh pool selected: $NOPEN unique openings, overlap with 1008 = 0"

run_gate(){
  local view="$1"
  local args=()
  [ "$view" = q00 ] && args=(--depth "$FORCE_DEPTH") ||
    args=(--movetime "$MOVETIME")
  timeout 10800 python3 jobs/tools/run_jass_gate_bounded.py \
    --jass-a "$J8" --jass-b "$J8" \
    --pattern-a "$W/TOPK3.pjtw" --pattern-b "$W/UNIFORM.pjtw" \
    --search-params-a "$Q00" --search-params-b "$Q00" \
    --openings-file "$W/open-eval.fen" "${args[@]}" --pairs 1 \
    --max-plies 160 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout 9000 --game-timeout 180 \
    --work-dir "$W/gate-$view" \
    --out "$ART/force/force-$view-TOPK3-vs-UNIFORM.json" \
    > "$W/force-$view.log" 2>&1
}

stage play-both-views
for view in q00 native; do
  stage "view-$view-${GAMES_PER_VIEW}-games"
  if run_gate "$view"; then
    say "  view $view completed"
  else
    say "  view $view FAILED (rc=$?) — fail-closed readout"
  fi
done

stage publish-readout
python3 - "$ART" "$EXPECTED_CODE_SHA" "$GAMES_PER_VIEW" \
  "$EXPECTED_UNIFORM_MODEL_SHA" "$EXPECTED_TOPK3_MODEL_SHA" \
  "$IN/arms-summary.json" "$IN/uniform-coverage.json" \
  "$IN/topk3-coverage.json" "$ART/topk-readout-openings.json" <<'PY'
import json
import math
import pathlib
import sys

art = pathlib.Path(sys.argv[1])
code_sha = sys.argv[2]
per_view = int(sys.argv[3])
uniform_sha, topk3_sha = sys.argv[4:6]
arms = json.load(open(sys.argv[6]))
uniform_cov = json.load(open(sys.argv[7]))
topk3_cov = json.load(open(sys.argv[8]))
opening_manifest = json.load(open(sys.argv[9]))

views = {}
for view in ("q00", "native"):
    path = art / "force" / f"force-{view}-TOPK3-vs-UNIFORM.json"
    views[view] = json.load(open(path)) if path.exists() else None

missing = [view for view, data in views.items() if data is None]
short = [
    view for view, data in views.items()
    if data is not None and data.get("n", 0) < int(0.9 * per_view)
]
wins = sum(data["wins_a"] for data in views.values() if data)
draws = sum(data["draws"] for data in views.values() if data)
losses = sum(data["wins_b"] for data in views.values() if data)
n = wins + draws + losses

def elo(rate):
    return -400 * math.log10(1 / rate - 1) if 0 < rate < 1 else None

if n:
    rate = (wins + 0.5 * draws) / n
    var = max(0.0, (wins + 0.25 * draws) / n - rate * rate)
    se = math.sqrt(var / n)
    lo = max(0.0, rate - 1.96 * se)
    hi = min(1.0, rate + 1.96 * se)
else:
    rate = lo = hi = None

if missing or short:
    verdict = "L3_PURE_TOPK3_VS_UNIFORM_READOUT_INVALID"
elif lo > 0.5:
    verdict = "L3_PURE_TOPK3_ABOVE_UNIFORM"
elif hi < 0.5:
    verdict = "L3_PURE_TOPK3_BELOW_UNIFORM"
else:
    verdict = "L3_PURE_TOPK3_VS_UNIFORM_INCONCLUSIVE"

def coverage_summary(report):
    cov = report["coverage"]
    return {
        "visited_buckets": int(cov["visited_buckets"]),
        "coverage_fraction": float(cov["coverage_fraction"]),
        "ge_10": int(cov["buckets_with_at_least"]["ge_10"]),
        "ge_100": int(cov["buckets_with_at_least"]["ge_100"]),
        "gini": float(report["concentration"]["gini"]),
    }

uc = coverage_summary(uniform_cov)
tc = coverage_summary(topk3_cov)
coverage = {
    "uniform": uc,
    "topk3": tc,
    "topk3_minus_uniform": {
        key: round(tc[key] - uc[key], 6)
        for key in ("visited_buckets", "coverage_fraction", "ge_10", "ge_100", "gini")
    },
}

summed = {
    "wins_topk3": wins,
    "draws": draws,
    "wins_uniform": losses,
    "n": n,
    "rate_topk3": round(rate, 6) if rate is not None else None,
    "ci95": [round(lo, 6), round(hi, 6)] if rate is not None else None,
    "elo": round(elo(rate), 2) if rate is not None and elo(rate) is not None else None,
    "elo_ci95": (
        [round(elo(lo), 1), round(elo(hi), 1)]
        if rate is not None and elo(lo) is not None and elo(hi) is not None
        else None
    ),
}
payload = {
    "schema": 1,
    "verdict": verdict,
    "code_sha": code_sha,
    "primary_contrast": "TOPK3 minus UNIFORM",
    "matchup": "TOPK3 vs UNIFORM",
    "models": {"uniform_sha256": uniform_sha, "topk3_sha256": topk3_sha},
    "source": {
        "job_id": "home-1022-l3-pure-topk-fit-resume-v1",
        "attempt_id": "20260728T163900Z-6dcc49d1",
        "corpus_job_id": arms["source"]["job_id"],
        "corpus_attempt_id": arms["source"]["attempt_id"],
    },
    "paired_fresh_openings": opening_manifest,
    "views_summed": summed,
    "per_view": views,
    "training_coverage": coverage,
    "holdout_is_diagnostic_only": True,
    "holdout_not_used_for_selection": True,
    "decision_rule": {
        "positive": "summed Elo CI95 entirely above zero",
        "negative": "summed Elo CI95 entirely below zero",
        "otherwise": "inconclusive; no promotion",
    },
    "promotion_authorized": False,
    "automatic_next_job": None,
}
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
(art / "topk3-vs-uniform-readout.json").write_text(serialized)
(art / "JASS_CONTROL_SUMMARY.json").write_text(serialized)
(art / f"VERDICT__{verdict}").write_text(verdict + "\n")
(art / "PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")

for view, data in sorted(views.items()):
    if data:
        print(
            f"  {view:7s} n={data['n']:>5} "
            f"{data['wins_a']}-{data['draws']}-{data['wins_b']} "
            f"rate={data['rate']} elo={data['elo']}"
        )
    else:
        print(f"  {view:7s} MISSING")
if n:
    print(
        f"\n  summed views: n={n} {wins}-{draws}-{losses} "
        f"rate={rate:.4f} CI95 [{lo:.4f}; {hi:.4f}]"
    )
    if elo(rate) is not None:
        print(f"  Elo {elo(rate):+.2f} CI95 [{elo(lo):+.1f}; {elo(hi):+.1f}]")
print(f"\n  verdict={verdict}")
PY

stage complete
VERDICT=$(ls "$ART" | sed -n 's/^VERDICT__//p' | head -1)
say "$VERDICT promotion=false automatic_next_job=null"
