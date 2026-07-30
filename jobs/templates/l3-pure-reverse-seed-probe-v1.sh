#!/usr/bin/env bash
# L3-PURE — operational CPX62 probe for matched-random vs HARD seed roots.
#
# This template consumes an already authenticated matched catalogue. It measures
# only throughput/yield at 100% seeding. It does not fit, play a strength match,
# choose the scientific SEED_FRAC, promote, bake, queue or continue a lineage.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${MATCHED_PREFIX:?}"; : "${EXPECTED_MATCHED_JOB:?}"
: "${EXPECTED_MATCHED_ATTEMPT:?}"; : "${EXPECTED_MATCHED_CODE_SHA:?}"
: "${HARD_VERDICT_PREFIX:?}"; : "${EXPECTED_HARD_VERDICT_JOB:?}"
: "${EXPECTED_HARD_VERDICT_ATTEMPT:?}"; : "${EXPECTED_HARD_VERDICT_CODE_SHA:?}"
: "${EXPECTED_HARD_VERDICT:?}"
: "${PARENT_PREFIX:?}"; : "${EXPECTED_PARENT_JOB:?}"
: "${EXPECTED_PARENT_ATTEMPT:?}"; : "${EXPECTED_PARENT_CODE_SHA:?}"
: "${PARENT_ARTEFACT:?}"
: "${PARENT_MODEL_SHA:?}"; : "${PARENT_NAME:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
IN="$JASS_RESULT_DIR/inputs"
mkdir -p "$W" "$ART" "$IN"
RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
STAGE="$W/stage.txt"
: > "$RES"
echo preflight > "$STAGE"

say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
phase(){ echo "$1" > "$STAGE"; say "phase=$1"; }

PROBE_RECORDS=${PROBE_RECORDS:-200}
PROBE_SEED_FRAC=${PROBE_SEED_FRAC:-100}
PROBE_TIMEOUT=${PROBE_TIMEOUT:-900}
LABEL_DEPTH=4
PLAY_DEPTH=8
MAXPLIES=260
EXPLORE_EPS=8
EXPLORE_DECAY=60
BASE_SEED=32452843
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"
MON=""

monitor(){
  (
    local t0; t0=$(date +%s)
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_s=%s\n' "$(( $(date +%s) - t0 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        awk '/MemAvailable:/{printf "mem_available_mb=%d\n",$2/1024}' /proc/meminfo
        for arm in control treatment; do
          [ -f "$W/$arm.log" ] &&
            printf '%s_log_lines=%s\n' "$arm" "$(wc -l < "$W/$arm.log")"
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
  rm -rf "$W/build" "$IN" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W/PARENT.pjtw" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${PROBE_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "explicit probe authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$PROBE_RECORDS" -eq 200 ] || die "operational probe requires 200 records/arm"
[ "$PROBE_SEED_FRAC" -eq 100 ] ||
  die "operational probe fraction is fixed at 100%, not the scientific dose"
[ "$PLAY_DEPTH" -eq 8 ] && [ "$LABEL_DEPTH" -eq 4 ] ||
  die "probe depth contract drift"
[ "$PROBE_TIMEOUT" -ge 60 ] && [ "$PROBE_TIMEOUT" -le 1800 ] ||
  die "probe timeout must be in [60,1800] seconds"
[ "$(nproc)" -eq 16 ] || die "CPX62 probe requires nproc=16"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" \
  -exec rm -rf {} + 2>/dev/null || true
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -ge 8000 ] || die "need 8 GiB free"
say "  CPX62: nproc=16 build=-j4 producers=1 sequential"
say "  operational dose: records=$PROBE_RECORDS seed_frac=$PROBE_SEED_FRAC%"
say "  scientific SEED_FRAC remains unset"
monitor

phase authenticate-hard-replay-verdict
python3 jobs/tools/fetch_result_files.py --prefix "$HARD_VERDICT_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=hard-verdict.json \
  --out-dir "$IN" --report "$ART/verified-hard-verdict.json" \
  > "$W/fetch-hard-verdict.log" 2>&1
python3 - "$ART/verified-hard-verdict.json" "$IN/hard-verdict.json" \
  "$EXPECTED_HARD_VERDICT_JOB" "$EXPECTED_HARD_VERDICT_ATTEMPT" \
  "$EXPECTED_HARD_VERDICT_CODE_SHA" "$EXPECTED_HARD_VERDICT" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
summary = json.load(open(sys.argv[2]))
if (
    report.get("job_id") != sys.argv[3]
    or report.get("attempt_id") != sys.argv[4]
    or report.get("code_sha") != sys.argv[5]
    or report.get("result_state") != "completed"
):
    raise SystemExit("hard-replay verdict identity/state mismatch")
if summary.get("verdict") != sys.argv[6]:
    raise SystemExit("hard-replay verdict mismatch")
if summary.get("automatic_next_job") is not None:
    raise SystemExit("hard-replay verdict attempted automatic continuation")
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
):
    raise SystemExit("matched catalogue identity/state mismatch")
if (
    manifest.get("schema") != 1
    or manifest.get("operation") != "l3-reverse-seed-matching"
    or manifest.get("code_sha") != sys.argv[8]
    or manifest.get("probe_authorized") is not True
    or manifest.get("training_authorized") is not False
    or manifest.get("promotion_authorized") is not False
    or manifest.get("automatic_next_job") is not None
    or manifest.get("external_teacher_inputs") != 0
):
    raise SystemExit("matched catalogue certificate mismatch")
if (
    summary.get("schema") != 1
    or summary.get("verdict") != "L3_PURE_REVERSE_SEED_CATALOGUE_READY"
    or summary.get("code_sha") != sys.argv[8]
    or summary.get("source_temporal_id")
       != manifest.get("source_temporal_id")
    or summary.get("matching_manifest_sha256")
       != hashlib.sha256(open(sys.argv[3], "rb").read()).hexdigest()
    or summary.get("probe_authorized") is not True
    or summary.get("training_authorized") is not False
    or summary.get("promotion_authorized") is not False
    or summary.get("automatic_next_job") is not None
    or summary.get("external_teacher_inputs") != 0
):
    raise SystemExit("matched job certificate mismatch")
causal = manifest.get("causal_certificate", {})
for key in (
    "same_authenticated_source",
    "same_source_temporal_id",
    "same_cardinality",
    "same_index_ordered_strata",
    "colour_pairs_verified",
    "zero_targets_verified",
    "historical_holdout_excluded",
):
    if causal.get(key) is not True:
        raise SystemExit(f"matched catalogue lacks causal proof: {key}")
if causal.get("control_selection_uses_wdl") is not False:
    raise SystemExit("matched-random control consulted WDL")
counts = []
for name, path in (
    ("control_seeds", sys.argv[4]),
    ("treatment_seeds", sys.argv[5]),
):
    raw = open(path, "rb").read()
    if len(raw) < 8 or raw[:4] != b"JNNW":
        raise SystemExit(f"{name}: invalid JNNW")
    count = struct.unpack_from("<I", raw, 4)[0]
    if len(raw) != 8 + 38 * count:
        raise SystemExit(f"{name}: JNNW size/count mismatch")
    output = manifest["outputs"][name]
    summary_name = name.replace("_", "-") + ".jnnw"
    job_output = summary.get("outputs", {}).get(summary_name, {})
    if (
        output.get("records") != count
        or output.get("sha256") != hashlib.sha256(raw).hexdigest()
        or job_output.get("records") != count
        or job_output.get("sha256") != hashlib.sha256(raw).hexdigest()
    ):
        raise SystemExit(f"{name}: hash/count mismatch")
    counts.append(count)
if counts[0] != counts[1] or counts[0] <= 0:
    raise SystemExit("matched catalogues have unequal/empty cardinality")
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
):
    raise SystemExit("parent identity/state mismatch")
PY
gunzip -c "$IN/PARENT.pjtw.gz" > "$W/PARENT.pjtw"
[ "$(sha256sum "$W/PARENT.pjtw" | awk '{print $1}')" = "$PARENT_MODEL_SHA" ] ||
  die "parent model hash drift"

phase build-and-tests
grep -q -- '--seed-frac must be an integer in \[0,100\]' src/main.cpp ||
  die "engine lacks seed-frac range guard"
grep -q 'seeded_openings=' src/main.cpp ||
  die "engine lacks seeded-opening counters"
grep -q 'split_selfplay_rngs' src/main.cpp ||
  die "engine lacks split self-play RNGs"
grep -q 'root_is_drawn' src/search.cpp ||
  die "engine predates drawn-root fix"
python3 -m py_compile tools/selfplay_frontier.py \
  jobs/tools/l3_reverse_seed_matching.py
python3 -m unittest jobs.tests.test_l3_reverse_seed_matching \
  > "$W/test-reverse-seeds.log" 2>&1
# TURNOVER was trained with the historical 8cf geometry.  The repository
# checkout intentionally carries the v4 generated files, so CMake flags alone
# do not select a compatible PJTW layout: regenerate the geometry before
# compiling every binary which must load the authenticated parent.
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf \
  > "$W/gen8.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
  -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j4 --target jass jass_tests > "$W/build.log" 2>&1
ctest --test-dir "$W/build" --output-on-failure > "$W/ctest.log" 2>&1
J="$W/build/jass"
[ "$("$J" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "king-capture witness failed"

phase validate-parent-geometry
# n_games=0 makes --gen-tdleaf a load-only smoke: it exercises the same
# load_eval_network PJTW dispatch as --gen-data-wdl without playing a game or
# reading a WDL.  This fails before either probe arm if generated geometry and
# parent weights ever drift again.
"$J" --gen-tdleaf "$W/PARENT.pjtw" 0 1 \
  "$W/parent-load-smoke.jnnw" 1 "$BASE_SEED" \
  > "$W/parent-load-smoke.log" 2>&1
python3 - "$W/parent-load-smoke.jnnw" <<'PY'
import struct
import sys
raw = open(sys.argv[1], "rb").read()
if raw != b"JNNW" + struct.pack("<I", 0):
    raise SystemExit("parent load smoke emitted an unexpected payload")
PY
rm -f "$W/parent-load-smoke.jnnw" "$W/parent-load-smoke.jnnw.games"
say "  parent geometry/load smoke: 8cf PASS"

run_probe(){
  local arm="$1" seed_file="$2"
  local start end rc
  start=$(date +%s)
  set +e
  timeout "$PROBE_TIMEOUT" "$J" --gen-data-wdl "$PROBE_RECORDS" \
    "$W/$arm.jnnw" "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" "$BASE_SEED" \
    --nnue "$W/PARENT.pjtw" --search-params-play "$Q00" --wdl-zero-score \
    --seed-file "$seed_file" --seed-frac "$PROBE_SEED_FRAC" \
    --random-open-plies 0 --explore-eps "$EXPLORE_EPS" \
    --explore-decay-plies "$EXPLORE_DECAY" --split-selfplay-rngs \
    --pair-openings --drop-plycap --sample-initial \
    --sample-meta-out "$W/$arm.jsm" \
    < /dev/null > "$W/$arm.log" 2>&1
  rc=$?
  set -e
  end=$(date +%s)
  printf '%s\n' "$((end - start))" > "$W/$arm.elapsed"
  printf 'arm=%s rc=%s elapsed_s=%s timeout_s=%s\n' \
    "$arm" "$rc" "$((end - start))" "$PROBE_TIMEOUT" |
    tee -a "$ART/producer-exits.txt"
  [ "$rc" -eq 0 ] || die "$arm probe failed rc=$rc"
}

phase probe-control
: > "$ART/producer-exits.txt"
run_probe control "$IN/control-seeds.jnnw"
phase probe-treatment
run_probe treatment "$IN/treatment-seeds.jnnw"

phase publish-operational-certificate
python3 - "$W" "$ART" "$IN/reverse-seed-matching.json" \
  "$EXPECTED_CODE_SHA" "$PARENT_NAME" "$PARENT_MODEL_SHA" \
  "$EXPECTED_HARD_VERDICT" "$PROBE_RECORDS" "$PROBE_SEED_FRAC" \
  "$BASE_SEED" "$PROBE_TIMEOUT" <<'PY'
import hashlib
import json
import math
import re
import struct
import sys
from pathlib import Path

w, art, matching_path = map(Path, sys.argv[1:4])
code_sha, parent_name, parent_sha, upstream_verdict = sys.argv[4:8]
records, probe_frac, base_seed, timeout_s = map(int, sys.argv[8:12])

def counted(path, magic, rec_size):
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != magic:
        raise SystemExit(f"{path}: invalid counted file")
    count = struct.unpack_from("<I", raw, 4)[0]
    if len(raw) != 8 + count * rec_size:
        raise SystemExit(f"{path}: size/count mismatch")
    return count, raw[8:]

def counters(log_path):
    lines = log_path.read_text(errors="replace").splitlines()
    exploration = next(
        (line for line in reversed(lines) if line.startswith("EXPLORATION ")),
        None,
    )
    hygiene = next(
        (line for line in reversed(lines) if line.startswith("LABELHYG ")),
        None,
    )
    if exploration is None or hygiene is None:
        raise SystemExit(f"{log_path}: missing engine counters")
    values = {
        key: int(value)
        for key, value in re.findall(r"([a-z_]+)=(-?[0-9]+)", exploration)
    }
    plycap = re.search(r"plycap_games=([0-9]+)/([0-9]+)", hygiene)
    if plycap is None:
        raise SystemExit(f"{log_path}: missing plycap counters")
    values["plycap_games"] = int(plycap.group(1))
    values["plycap_denominator_games"] = int(plycap.group(2))
    return values

arms = {}
for arm in ("control", "treatment"):
    count, _ = counted(w / f"{arm}.jnnw", b"JNNW", 38)
    meta_count, meta_body = counted(w / f"{arm}.jsm", b"JSM1", 17)
    if count != records or meta_count != records:
        raise SystemExit(f"{arm}: output count drift")
    seeded_records = 0
    standard_records = 0
    seeded_openings = set()
    standard_openings = set()
    for index in range(meta_count):
        game_id, opening_id, seeded = struct.unpack_from(
            "<QQB", meta_body, index * 17
        )
        del game_id
        if seeded == 1:
            seeded_records += 1
            seeded_openings.add(opening_id)
        elif seeded == 0:
            standard_records += 1
            standard_openings.add(opening_id)
        else:
            raise SystemExit(f"{arm}: invalid seeded flag")
    values = counters(w / f"{arm}.log")
    for key, expected in (
        ("split_selfplay_rngs", 1),
        ("random_open_plies", 0),
        ("random_open_moves", 0),
        ("seed_frac", probe_frac),
        ("standard_openings", 0),
    ):
        if values.get(key) != expected:
            raise SystemExit(
                f"{arm}: {key}={values.get(key)} expected={expected}"
            )
    if (
        values.get("seeded_openings", 0) <= 0
        or values.get("openings")
        != values.get("seeded_openings") + values.get("standard_openings")
        or standard_records != 0
        or seeded_records != records
    ):
        raise SystemExit(f"{arm}: realised seed dose mismatch")
    elapsed = int((w / f"{arm}.elapsed").read_text().strip())
    if elapsed <= 0:
        raise SystemExit(f"{arm}: non-positive elapsed time")
    arms[arm] = {
        "records": count,
        "elapsed_s": elapsed,
        "records_per_min": 60.0 * count / elapsed,
        "engine_openings": values["openings"],
        "engine_games": values["games"],
        "seeded_openings": values["seeded_openings"],
        "standard_openings": values["standard_openings"],
        "emitted_seeded_records": seeded_records,
        "emitted_standard_records": standard_records,
        "emitted_seeded_openings": len(seeded_openings),
        "emitted_standard_openings": len(standard_openings),
        "records_per_engine_game": (
            count / values["games"] if values["games"] else None
        ),
        "plycap_games": values["plycap_games"],
        "plycap_denominator_games": values["plycap_denominator_games"],
    }

healthy_s = max(value["elapsed_s"] for value in arms.values())
payload = {
    "schema": 1,
    "verdict": "L3_PURE_REVERSE_SEED_OPERATIONAL_PROBE_COMPLETE",
    "code_sha": code_sha,
    "parent": {"name": parent_name, "model_sha256": parent_sha},
    "upstream_hard_replay_verdict": upstream_verdict,
    "matched_catalogue_manifest_sha256": hashlib.sha256(
        matching_path.read_bytes()
    ).hexdigest(),
    "probe": {
        "box": "cpx62",
        "nproc": 16,
        "build_jobs": 4,
        "producer_concurrency": 1,
        "arm_order": ["control", "treatment"],
        "records_per_arm": records,
        "probe_seed_frac": probe_frac,
        "scientific_seed_frac": None,
        "same_base_seed": True,
        "base_seed": base_seed,
        "random_open_plies": 0,
        "split_selfplay_rngs": True,
        "sample_initial": True,
        "timeout_s": timeout_s,
        "recommended_future_timeout_s_1p3x": math.ceil(healthy_s * 1.3),
        "wdl_read_for_dose_choice": False,
    },
    "arms": arms,
    "scientific_result": None,
    "probe_authorized": True,
    "training_authorized": False,
    "promotion_authorized": False,
    "automatic_next_job": None,
    "external_teacher_inputs": 0,
}
(art / "JASS_CONTROL_SUMMARY.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
(art / "VERDICT__L3_PURE_REVERSE_SEED_OPERATIONAL_PROBE_COMPLETE").touch()
(art / "TRAINING_AUTHORIZED__FALSE").touch()
(art / "PROMOTION_AUTHORIZED__FALSE").touch()
(art / "AUTOMATIC_NEXT_JOB__NULL").touch()
for arm, result in arms.items():
    print(
        f"  {arm}: {result['records']} records in {result['elapsed_s']}s "
        f"({result['records_per_min']:.1f}/min), "
        f"seeded_openings={result['seeded_openings']}"
    )
print(
    "  scientific SEED_FRAC remains unset; "
    f"future timeout floor={payload['probe']['recommended_future_timeout_s_1p3x']}s"
)
PY

phase complete
say "L3_PURE_REVERSE_SEED_OPERATIONAL_PROBE_COMPLETE training=false promotion=false automatic_next_job=null"
