#!/usr/bin/env bash
# L3-PURE — causal A/B of matched-random versus failed-conversion seed roots.
#
# Both arms are 100% fresh self-play from index-aligned catalogues drawn from
# the same authenticated historical source.  They share parent, search policy,
# depths, epsilon policy, volume, shard seeds, split and fit.  The only changed
# factor is the root catalogue selection policy.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${MATCHED_PREFIX:?}"; : "${EXPECTED_MATCHED_JOB:?}"
: "${EXPECTED_MATCHED_ATTEMPT:?}"; : "${EXPECTED_MATCHED_CODE_SHA:?}"
: "${PROBE_READOUT_PREFIX:?}"; : "${EXPECTED_PROBE_READOUT_JOB:?}"
: "${EXPECTED_PROBE_READOUT_ATTEMPT:?}"; : "${EXPECTED_PROBE_READOUT_CODE_SHA:?}"
: "${PARENT_PREFIX:?}"; : "${EXPECTED_PARENT_JOB:?}"
: "${EXPECTED_PARENT_ATTEMPT:?}"; : "${EXPECTED_PARENT_CODE_SHA:?}"
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

RECORDS=${RECORDS:-2000000}
SHARDS=${SHARDS:-6}
SEED_FRAC=${SEED_FRAC:-100}
LABEL_DEPTH=4
PLAY_DEPTH=8
MAXPLIES=260
EXPLORE_EPS=8
EXPLORE_DECAY=60
# Disjoint from the operational probe (32452843): the probe read no WDL, but
# the scientific corpora still use a fresh RNG stream.
BASE_SEED=49979687
SPLIT_SEED=577215
HOLDOUT_MOD=10
GEN_TIMEOUT_CONTROL=${GEN_TIMEOUT_CONTROL:-18000}
GEN_TIMEOUT_TREATMENT=${GEN_TIMEOUT_TREATMENT:-18000}
FIT_TIMEOUT=${FIT_TIMEOUT:-10800}
L2=3e-5
MAXIT=1000
LBFGS_MAXCOR=20
LBFGS_GTOL=1e-3
CHUNK=20000
NUMPY_VERSION=${NUMPY_VERSION:-2.5.1}
SCIPY_VERSION=${SCIPY_VERSION:-1.18.0}
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

MON=""
monitor(){
  (
    local t0; t0=$(date +%s)
    while true; do
      {
        local elapsed; elapsed=$(( ($(date +%s) - t0) / 60 ))
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$elapsed"
        awk '/MemAvailable:/{printf "mem_available_mb=%d\n",$2/1024}' /proc/meminfo
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        for arm in control treatment; do
          awk -v a="$arm" -v el="$elapsed" '
            /positions$/ { done[FILENAME] = $4; total[FILENAME] = $6 }
            END {
              for (k in done) { d += done[k]; t += total[k] }
              if (t > 0) {
                printf "%s_positions=%d/%d (%.1f%%)\n", a, d, t, 100*d/t
                if (d > 0 && el > 0)
                  printf "%s_eta_remaining_min=%d\n", a, el*(t-d)/d
              }
            }' "$W"/"$arm"-s*.log 2>/dev/null || true
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
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat "$W"/*.pjtw 2>/dev/null || true
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
[ "$RECORDS" -eq 2000000 ] || die "causal contract requires 2M records/arm"
[ "$SHARDS" -eq 6 ] || die "causal contract requires 6 shards/arm"
[ "$SEED_FRAC" -eq 100 ] || die "authenticated probe selected seed_frac=100"
[ "$PLAY_DEPTH" -eq 8 ] && [ "$LABEL_DEPTH" -eq 4 ] ||
  die "depth contract drift"
[ "$(nproc)" -eq 16 ] || die "CPX62 causal job requires nproc=16"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -ge 20000 ] || die "need 20 GiB free"
say "  CPX62: sequential arms, at most $SHARDS producers"
say "  design: 2M/arm, 100% seeded, d8/Q00, zero historical replay"
monitor

phase authenticate-probe-readout
python3 jobs/tools/fetch_result_files.py --prefix "$PROBE_READOUT_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=probe-readout.json \
  --out-dir "$IN" --report "$ART/verified-probe-readout.json" \
  > "$W/fetch-probe-readout.log" 2>&1
python3 - "$ART/verified-probe-readout.json" "$IN/probe-readout.json" \
  "$EXPECTED_PROBE_READOUT_JOB" "$EXPECTED_PROBE_READOUT_ATTEMPT" \
  "$EXPECTED_PROBE_READOUT_CODE_SHA" "$SEED_FRAC" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
summary = json.load(open(sys.argv[2]))
if (
    report.get("job_id") != sys.argv[3]
    or report.get("attempt_id") != sys.argv[4]
    or report.get("code_sha") != sys.argv[5]
    or report.get("result_state") != "completed"
    or report.get("exit_code") != 0
):
    raise SystemExit("probe readout identity/state mismatch")
if (
    summary.get("verdict")
       != "DIAGNOSTIC_1084_OPERATIONAL_PROBE_AUTHENTICATED"
    or summary.get("recommended_scientific_seed_frac") != int(sys.argv[6])
    or summary.get("dose_rule", {}).get("wdl_read") is not False
    or summary.get("scientific_result") is not False
    or summary.get("training_authorized") is not False
    or summary.get("promotion_authorized") is not False
    or summary.get("automatic_next_job", "missing") is not None
):
    raise SystemExit("probe dose certificate mismatch")
PY

phase fetch-and-authenticate-matched-catalogue
python3 jobs/tools/fetch_result_files.py --prefix "$MATCHED_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=matched-summary.json \
  --file artefacts/control-seeds.jnnw=control-seeds.jnnw \
  --file artefacts/treatment-seeds.jnnw=treatment-seeds.jnnw \
  --file artefacts/reverse-seed-matching.json=reverse-seed-matching.json \
  --out-dir "$IN" --report "$ART/verified-matched-catalogue.json" \
  > "$W/fetch-matched.log" 2>&1
python3 - "$ART/verified-matched-catalogue.json" "$IN/matched-summary.json" \
  "$IN/reverse-seed-matching.json" "$IN/control-seeds.jnnw" \
  "$IN/treatment-seeds.jnnw" "$EXPECTED_MATCHED_JOB" \
  "$EXPECTED_MATCHED_ATTEMPT" "$EXPECTED_MATCHED_CODE_SHA" <<'PY'
import hashlib
import json
import struct
import sys
report = json.load(open(sys.argv[1]))
summary = json.load(open(sys.argv[2]))
manifest = json.load(open(sys.argv[3]))
if (
    report.get("job_id") != sys.argv[6]
    or report.get("attempt_id") != sys.argv[7]
    or report.get("code_sha") != sys.argv[8]
    or report.get("result_state") != "completed"
    or report.get("exit_code") != 0
):
    raise SystemExit("matched catalogue identity/state mismatch")
if (
    summary.get("verdict") != "L3_PURE_REVERSE_SEED_CATALOGUE_READY"
    or summary.get("code_sha") != sys.argv[8]
    or manifest.get("operation") != "l3-reverse-seed-matching"
    or manifest.get("code_sha") != sys.argv[8]
    or summary.get("training_authorized") is not False
    or manifest.get("training_authorized") is not False
    or summary.get("promotion_authorized") is not False
    or manifest.get("promotion_authorized") is not False
    or summary.get("automatic_next_job", "missing") is not None
    or manifest.get("automatic_next_job", "missing") is not None
    or summary.get("external_teacher_inputs") != 0
    or manifest.get("external_teacher_inputs") != 0
    or summary.get("matching_manifest_sha256")
       != hashlib.sha256(open(sys.argv[3], "rb").read()).hexdigest()
):
    raise SystemExit("matched catalogue certificate mismatch")
causal = manifest.get("causal_certificate", {})
for key in (
    "same_authenticated_source", "same_source_temporal_id",
    "same_cardinality", "same_index_ordered_strata",
    "colour_pairs_verified", "zero_targets_verified",
    "historical_holdout_excluded",
):
    if causal.get(key) is not True:
        raise SystemExit(f"matched catalogue lacks causal proof: {key}")
if causal.get("control_selection_uses_wdl") is not False:
    raise SystemExit("matched-random control consulted WDL")
counts = []
for key, path in (
    ("control_seeds", sys.argv[4]), ("treatment_seeds", sys.argv[5])
):
    raw = open(path, "rb").read()
    if len(raw) < 8 or raw[:4] != b"JNNW":
        raise SystemExit(f"{key}: invalid JNNW")
    count = struct.unpack_from("<I", raw, 4)[0]
    if len(raw) != 8 + 38 * count:
        raise SystemExit(f"{key}: size/count mismatch")
    output = manifest["outputs"][key]
    if (
        output.get("records") != count
        or output.get("sha256") != hashlib.sha256(raw).hexdigest()
    ):
        raise SystemExit(f"{key}: output certificate mismatch")
    counts.append(count)
if counts[0] != counts[1] or counts[0] <= 0:
    raise SystemExit("matched catalogues unequal or empty")
PY

phase fetch-and-authenticate-parent
python3 jobs/tools/fetch_result_files.py --prefix "$PARENT_PREFIX" \
  --file "artefacts/$PARENT_ARTEFACT=PARENT.pjtw.gz" \
  --out-dir "$IN" --report "$ART/verified-parent.json" \
  > "$W/fetch-parent.log" 2>&1
python3 - "$ART/verified-parent.json" "$EXPECTED_PARENT_JOB" \
  "$EXPECTED_PARENT_ATTEMPT" "$EXPECTED_PARENT_CODE_SHA" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
if (
    report.get("job_id") != sys.argv[2]
    or report.get("attempt_id") != sys.argv[3]
    or report.get("code_sha") != sys.argv[4]
    or report.get("result_state") != "completed"
    or report.get("exit_code") != 0
):
    raise SystemExit("parent identity/state mismatch")
PY
gunzip -c "$IN/PARENT.pjtw.gz" > "$W/PARENT.pjtw"
[ "$(sha256sum "$W/PARENT.pjtw" | awk '{print $1}')" = "$PARENT_MODEL_SHA" ] ||
  die "parent model hash drift"

phase build-and-tests
python3 -m venv "$W/venv"
"$W/venv/bin/python" -m pip install --disable-pip-version-check \
  --only-binary=:all: "numpy==$NUMPY_VERSION" "scipy==$SCIPY_VERSION" \
  > "$W/pip.log" 2>&1
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf \
  > "$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
  -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests > "$W/build.log" 2>&1
ctest --test-dir "$W/build" --output-on-failure > "$W/ctest.log" 2>&1
J="$W/build/jass"
[ "$("$J" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "king-capture witness failed"
"$J" --gen-tdleaf "$W/PARENT.pjtw" 0 1 \
  "$W/parent-load-smoke.jnnw" 1 "$BASE_SEED" \
  > "$W/parent-load-smoke.log" 2>&1
rm -f "$W/parent-load-smoke.jnnw" "$W/parent-load-smoke.jnnw.games"
say "  build, 8cf parent load and tests passed"

gen_arm(){
  local arm="$1" seed_file="$2" timeout_s="$3"
  local base=$((RECORDS / SHARDS)) rem=$((RECORDS % SHARDS))
  local count shard failed=0 pid rc idx
  local pids=() shards=()
  : > "$ART/producer-exits-$arm.txt"
  for shard in $(seq 0 $((SHARDS - 1))); do
    count="$base"; [ "$shard" -lt "$rem" ] && count=$((count + 1))
    timeout "$timeout_s" "$J" --gen-data-wdl "$count" \
      "$W/$arm-s$shard.jnnw" "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" \
      $((BASE_SEED + shard)) \
      --nnue "$W/PARENT.pjtw" --search-params-play "$Q00" --wdl-zero-score \
      --seed-file "$seed_file" --seed-frac "$SEED_FRAC" \
      --random-open-plies 0 --explore-eps "$EXPLORE_EPS" \
      --explore-decay-plies "$EXPLORE_DECAY" --split-selfplay-rngs \
      --pair-openings --drop-plycap --sample-initial \
      --sample-meta-out "$W/$arm-s$shard.jsm" \
      < /dev/null > "$W/$arm-s$shard.log" 2>&1 &
    pids+=("$!"); shards+=("$shard")
  done
  for idx in "${!pids[@]}"; do
    pid="${pids[$idx]}"; shard="${shards[$idx]}"
    if wait "$pid"; then rc=0; else rc=$?; fi
    printf 'arm=%s shard=%s pid=%s rc=%s timeout_s=%s\n' \
      "$arm" "$shard" "$pid" "$rc" "$timeout_s" |
      tee -a "$ART/producer-exits-$arm.txt"
    [ "$rc" -eq 0 ] || failed=$((failed + 1))
  done
  [ "$failed" -eq 0 ] || die "$arm generation: $failed producer failures"
}

phase generate-control
gen_arm control "$IN/control-seeds.jnnw" "$GEN_TIMEOUT_CONTROL"
phase generate-treatment
gen_arm treatment "$IN/treatment-seeds.jnnw" "$GEN_TIMEOUT_TREATMENT"

for arm in control treatment; do
  for log in "$W/$arm"-s*.log; do
    grep -q 'label_score_searches=0' "$log" ||
      die "score-label search in $log"
  done
  grep '^EXPLORATION' "$W/$arm"-s*.log > "$ART/exploration-$arm.txt"
  grep '^LABELHYG' "$W/$arm"-s*.log > "$ART/labelhyg-$arm.txt"
done

phase verify-generation
python3 - "$W" "$ART" "$RECORDS" "$SEED_FRAC" "$SHARDS" <<'PY'
import json
import pathlib
import re
import struct
import sys
w, art = map(pathlib.Path, sys.argv[1:3])
records, seed_frac, shards = map(int, sys.argv[3:6])
payload = {"schema": 1, "records_per_arm": records, "seed_frac": seed_frac}
for arm in ("control", "treatment"):
    total = 0
    counters = []
    plycap_games = 0
    plycap_denominator_games = 0
    for shard in range(shards):
        path = w / f"{arm}-s{shard}.jnnw"
        raw = path.read_bytes()[:8]
        if len(raw) != 8 or raw[:4] != b"JNNW":
            raise SystemExit(f"{path}: invalid JNNW")
        total += struct.unpack_from("<I", raw, 4)[0]
        lines = (w / f"{arm}-s{shard}.log").read_text(errors="replace").splitlines()
        line = next((x for x in reversed(lines) if x.startswith("EXPLORATION ")), None)
        if line is None:
            raise SystemExit(f"{arm}-s{shard}: missing exploration counters")
        values = {
            k: int(v) for k, v in re.findall(r"([a-z_]+)=(-?[0-9]+)", line)
        }
        for key, expected in (
            ("split_selfplay_rngs", 1), ("seed_frac", seed_frac),
            ("random_open_plies", 0), ("standard_openings", 0),
        ):
            if values.get(key) != expected:
                raise SystemExit(
                    f"{arm}-s{shard}: {key}={values.get(key)} expected={expected}"
                )
        if values.get("seeded_openings", 0) <= 0:
            raise SystemExit(f"{arm}-s{shard}: no seeded opening")
        hygiene = next(
            (x for x in reversed(lines) if x.startswith("LABELHYG ")), None
        )
        match = re.search(r"plycap_games=([0-9]+)/([0-9]+)", hygiene or "")
        if match is None:
            raise SystemExit(f"{arm}-s{shard}: missing plycap counters")
        plycap_games += int(match.group(1))
        plycap_denominator_games += int(match.group(2))
        counters.append(values)
    if total != records:
        raise SystemExit(f"{arm}: {total} records, expected {records}")
    payload[arm] = {
        "records": total,
        "seeded_openings": sum(x["seeded_openings"] for x in counters),
        "standard_openings": sum(x["standard_openings"] for x in counters),
        "plycap_games": plycap_games,
        "plycap_denominator_games": plycap_denominator_games,
        "plycap_rate": (
            plycap_games / plycap_denominator_games
            if plycap_denominator_games else None
        ),
    }
    if (
        plycap_denominator_games <= 0
        or plycap_games / plycap_denominator_games > 0.25
    ):
        raise SystemExit(f"{arm}: full-run plycap rate exceeds probe dose gate")
payload["same_shard_seeds"] = True
payload["same_seed_fraction"] = True
payload["only_factor"] = "seed_root_selection_policy"
(art / "paired-generation-check.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

phase merge-split-cover
for arm in control treatment; do
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
  python3 jobs/tools/assert_corpus_wdl.py --data "$W/$arm.raw.jnnw" \
    --out "$ART/$arm-corpus-wdl.json" > "$W/$arm-corpus-wdl.log" 2>&1 ||
    die "$arm WDL canary failed"
  gzip -n -c "$W/$arm.raw.jnnw" > "$ART/$arm.jnnw.gz"
  gzip -n -c "$W/$arm.raw.jsm" > "$ART/$arm.jsm.gz"
done

python3 - "$ART/control-split.json" "$ART/treatment-split.json" \
  "$ART/paired-split-check.json" <<'PY'
import json
import sys
a, b = (json.load(open(path)) for path in sys.argv[1:3])
for key in ("split_unit", "holdout_mod", "seed", "tail_is_holdout"):
    if a.get(key) != b.get(key):
        raise SystemExit(f"split contract mismatch: {key}")
for name, manifest in (("control", a), ("treatment", b)):
    for key in ("train_openings", "holdout_openings", "train_records",
                "holdout_records"):
        if int(manifest.get(key, 0)) <= 0:
            raise SystemExit(f"{name}: non-positive {key}")
payload = {
    "schema": 1,
    "same_split_contract": True,
    "opening_counts_are_treatment_outcomes": True,
    "control": a,
    "treatment": b,
}
with open(sys.argv[3], "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY

phase fit-control
for arm in control treatment; do
  [ "$arm" = control ] || phase fit-treatment
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
    --warm-start "$W/PARENT.pjtw" --holdout-count "$HOLD" \
    --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
    --lbfgs-maxcor "$LBFGS_MAXCOR" --lbfgs-gtol "$LBFGS_GTOL" \
    --optimizer-report "$ART/$arm-optimizer.json" \
    > "$W/fit-$arm.log" 2>&1
  fit_rc=$?
  set -e
  [ -s "$W/$arm.pjtw" ] && gzip -n -c "$W/$arm.pjtw" > "$ART/$arm.pjtw.gz"
  [ "$fit_rc" -eq 0 ] || die "$arm fit failed rc=$fit_rc"
  "$W/venv/bin/python" - "$ART/$arm-optimizer.json" <<'PY' ||
import json
import sys
if not json.load(open(sys.argv[1])).get("success"):
    raise SystemExit(1)
PY
    die "$arm optimiser did not converge"
done

phase publish-certificate
"$W/venv/bin/python" - "$W" "$ART" "$EXPECTED_CODE_SHA" "$RECORDS" \
  "$SEED_FRAC" "$PLAY_DEPTH" "$PARENT_NAME" "$PARENT_MODEL_SHA" \
  "$IN" "$PROBE_READOUT_PREFIX" "$MATCHED_PREFIX" "$PARENT_PREFIX" <<'PY'
import hashlib
import json
import pathlib
import re
import sys
w, art = map(pathlib.Path, sys.argv[1:3])
code_sha = sys.argv[3]
records, seed_frac, depth = map(int, sys.argv[4:7])
parent_name, parent_sha = sys.argv[7:9]
inputs = pathlib.Path(sys.argv[9])
probe_prefix, matched_prefix, parent_prefix = sys.argv[10:13]

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

probe_report = json.load(open(art / "verified-probe-readout.json"))
probe_summary_path = inputs / "probe-readout.json"
matched_report = json.load(open(art / "verified-matched-catalogue.json"))
matched_summary_path = inputs / "matched-summary.json"
matching_path = inputs / "reverse-seed-matching.json"
parent_report = json.load(open(art / "verified-parent.json"))
arms = {}
generation = json.load(open(art / "paired-generation-check.json"))
for arm in ("control", "treatment"):
    cov = json.load(open(art / f"{arm}-coverage.json"))
    opt = json.load(open(art / f"{arm}-optimizer.json"))
    wdl = json.load(open(art / f"{arm}-corpus-wdl.json"))
    log = (w / f"fit-{arm}.log").read_text(errors="replace")
    match = re.search(r"HOLDOUT_LOGLOSS[ =:]+([0-9.]+)", log)
    arms[arm] = {
        "model_sha256": hashlib.sha256((w / f"{arm}.pjtw").read_bytes()).hexdigest(),
        "wdl": wdl,
        "generation": generation[arm],
        "coverage": {
            "visited_buckets": cov["coverage"]["visited_buckets"],
            "visited_pct": round(100.0 * cov["coverage"]["coverage_fraction"], 3),
            "gini": cov["concentration"]["gini"],
            "buckets_ge_10": cov["coverage"]["buckets_with_at_least"]["ge_10"],
            "buckets_ge_100": cov["coverage"]["buckets_with_at_least"]["ge_100"],
        },
        "fit": {
            "iterations": opt.get("nit"),
            "converged": opt.get("success"),
            "holdout_logloss_diagnostic_only": (
                float(match.group(1)) if match else None
            ),
        },
    }
payload = {
    "schema": 1,
    "verdict": "L3_PURE_REVERSE_SEED_CAUSAL_AB_ARMS_READY",
    "code_sha": code_sha,
    "parent": {"name": parent_name, "model_sha256": parent_sha},
    "authenticated_inputs": {
        "probe_readout": {
            "prefix": probe_prefix,
            "job_id": probe_report["job_id"],
            "attempt_id": probe_report["attempt_id"],
            "code_sha": probe_report["code_sha"],
            "summary_sha256": sha256(probe_summary_path),
        },
        "matched_catalogue": {
            "prefix": matched_prefix,
            "job_id": matched_report["job_id"],
            "attempt_id": matched_report["attempt_id"],
            "code_sha": matched_report["code_sha"],
            "summary_sha256": sha256(matched_summary_path),
            "matching_manifest_sha256": sha256(matching_path),
            "control_seeds_sha256": sha256(inputs / "control-seeds.jnnw"),
            "treatment_seeds_sha256": sha256(inputs / "treatment-seeds.jnnw"),
        },
        "parent": {
            "prefix": parent_prefix,
            "job_id": parent_report["job_id"],
            "attempt_id": parent_report["attempt_id"],
            "code_sha": parent_report["code_sha"],
            "model_sha256": parent_sha,
        },
    },
    "primary_contrast": "HARD_SEED_SELFPLAY minus MATCHED_RANDOM_SEED_SELFPLAY",
    "design": {
        "single_factor": "seed_root_selection_policy",
        "control": "matched_random_train_only_roots",
        "treatment": "failed_conversion_train_only_roots",
        "records_per_arm": records,
        "seed_frac": seed_frac,
        "historical_replay_records": 0,
        "play_depth": depth,
        "label_depth": 4,
        "random_open_plies": 0,
        "sample_initial": True,
        "same_parent": True,
        "same_search_policy": True,
        "same_shard_seeds": True,
        "same_split_contract": True,
        "same_fit": True,
    },
    "arms": arms,
    "holdout_loss_is_diagnostic_only": True,
    "readout_required": (
        "treatment vs control on fresh paired openings, both colours, "
        "Q00 and native 0.1 s/move, summed before Elo"
    ),
    "scientific_result": False,
    "training_authorized": True,
    "promotion_authorized": False,
    "automatic_next_job": None,
    "external_teacher_inputs": 0,
}
(art / "JASS_CONTROL_SUMMARY.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
(art / "VERDICT__L3_PURE_REVERSE_SEED_CAUSAL_AB_ARMS_READY").touch()
(art / "SCIENTIFIC_RESULT__FALSE").touch()
(art / "PROMOTION_AUTHORIZED__FALSE").touch()
(art / "AUTOMATIC_NEXT_JOB__NULL").touch()
for arm, result in arms.items():
    print(
        f"  {arm}: model={result['model_sha256']} "
        f"coverage={result['coverage']['visited_pct']}% "
        f"draw={result['wdl']['shares']['draw']} "
        f"converged={result['fit']['converged']}"
    )
PY
phase complete
say "L3_PURE_REVERSE_SEED_CAUSAL_AB_ARMS_READY promotion=false automatic_next_job=null"
