#!/usr/bin/env bash
# L3-PURE — build the matched-random/HARD reverse-seed catalogues.
#
# Data-only preflight. It authenticates one historical source and one HARD
# catalogue, reproduces the historical split, then runs the matcher twice.
# It never self-plays, fits, matches strength, promotes, queues or continues.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${HISTORY_PREFIX:?}"; : "${EXPECTED_HISTORY_JOB:?}"
: "${EXPECTED_HISTORY_ATTEMPT:?}"; : "${EXPECTED_HISTORY_CODE_SHA:?}"
: "${EXPECTED_HISTORY_STATE:?}"; : "${HISTORY_DATA_ARTEFACT:?}"
: "${HISTORY_META_ARTEFACT:?}"; : "${HISTORY_SPLIT_ARTEFACT:?}"
: "${HISTORY_AUTH_PREFIX:?}"; : "${EXPECTED_HISTORY_AUTH_JOB:?}"
: "${EXPECTED_HISTORY_AUTH_ATTEMPT:?}"; : "${EXPECTED_HISTORY_AUTH_CODE_SHA:?}"
: "${EXPECTED_HISTORY_AUTH_VERDICT:?}"; : "${EXPECTED_HISTORY_RECORDS:?}"
: "${HISTORY_ARM:?}"; : "${SOURCE_TEMPORAL_ID:?}"
: "${HARD_PREFIX:?}"; : "${EXPECTED_HARD_JOB:?}"
: "${EXPECTED_HARD_ATTEMPT:?}"; : "${EXPECTED_HARD_CODE_SHA:?}"
: "${EXPECTED_HARD_VERDICT:?}"

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

MATCHING_SEED=${MATCHING_SEED:-3141592}
SPLIT_SEED=${SPLIT_SEED:-577215}
HOLDOUT_MOD=${HOLDOUT_MOD:-10}
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
  rm -rf "$IN" "$W/match-a" "$W/match-b" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${DATA_ONLY_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "explicit data-only authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$MATCHING_SEED" -eq 3141592 ] || die "matching seed drift"
[ "$SPLIT_SEED" -eq 577215 ] || die "historical split seed drift"
[ "$HOLDOUT_MOD" -eq 10 ] || die "historical holdout ratio drift"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -ge 12000 ] ||
  die "need 12 GiB free"
monitor

phase fetch-history-certificate
python3 jobs/tools/fetch_result_files.py --prefix "$HISTORY_AUTH_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=history-auth.json \
  --out-dir "$IN" --report "$ART/verified-history-auth.json" \
  > "$W/fetch-history-auth.log" 2>&1

phase fetch-and-authenticate-history
python3 jobs/tools/fetch_result_files.py --prefix "$HISTORY_PREFIX" \
  --expected-state "$EXPECTED_HISTORY_STATE" \
  --file "artefacts/$HISTORY_DATA_ARTEFACT=history.jnnw.gz" \
  --file "artefacts/$HISTORY_META_ARTEFACT=history.jsm.gz" \
  --file "artefacts/$HISTORY_SPLIT_ARTEFACT=source-split.json" \
  --out-dir "$IN" --report "$ART/verified-history-source.json" \
  > "$W/fetch-history.log" 2>&1
python3 - "$ART/verified-history-source.json" "$EXPECTED_HISTORY_JOB" \
  "$EXPECTED_HISTORY_ATTEMPT" "$EXPECTED_HISTORY_CODE_SHA" \
  "$EXPECTED_HISTORY_STATE" "$ART/verified-history-auth.json" \
  "$IN/history-auth.json" "$EXPECTED_HISTORY_AUTH_JOB" \
  "$EXPECTED_HISTORY_AUTH_ATTEMPT" "$EXPECTED_HISTORY_AUTH_CODE_SHA" \
  "$EXPECTED_HISTORY_AUTH_VERDICT" "$EXPECTED_HISTORY_RECORDS" \
  "$HISTORY_ARM" "$IN/history.jnnw.gz" "$IN/history.jsm.gz" \
  "$IN/source-split.json" <<'PY'
import hashlib
import json
import sys

def digest(path):
    value = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()

report = json.load(open(sys.argv[1]))
if (
    report.get("job_id") != sys.argv[2]
    or report.get("attempt_id") != sys.argv[3]
    or report.get("code_sha") != sys.argv[4]
    or report.get("result_state") != sys.argv[5]
):
    raise SystemExit("historical source identity/state mismatch")

auth_report = json.load(open(sys.argv[6]))
auth = json.load(open(sys.argv[7]))
if (
    auth_report.get("job_id") != sys.argv[8]
    or auth_report.get("attempt_id") != sys.argv[9]
    or auth_report.get("code_sha") != sys.argv[10]
    or auth_report.get("result_state") != "completed"
    or auth.get("verdict") != sys.argv[11]
    or auth.get("source_job") != sys.argv[2]
    or auth.get("source_attempt") != sys.argv[3]
    or auth.get("source_code_sha") != sys.argv[4]
    or auth.get("external_teacher_inputs") != 0
    or auth.get("promotion") is not False
    or auth.get("automatic_next_job") is not None
):
    raise SystemExit("historical catalogue certificate mismatch")

expected_records = int(sys.argv[12])
arm_name = sys.argv[13]
arm = auth.get("arms", {}).get(arm_name)
if not isinstance(arm, dict) or arm.get("records") != expected_records:
    raise SystemExit(f"historical catalogue arm mismatch: {arm_name}")
expected = {
    "history.jnnw.gz": arm.get("data_gz_sha256"),
    "history.jsm.gz": arm.get("meta_gz_sha256"),
}
actual = {row["local_name"]: row["sha256"] for row in report["files"]}
for name, expected_digest in expected.items():
    if actual.get(name) != expected_digest:
        raise SystemExit(f"historical compressed hash mismatch for {name}")
if digest(sys.argv[14]) != expected["history.jnnw.gz"]:
    raise SystemExit("downloaded historical JNNW gzip hash mismatch")
if digest(sys.argv[15]) != expected["history.jsm.gz"]:
    raise SystemExit("downloaded historical JSM1 gzip hash mismatch")
if json.load(open(sys.argv[16])) != arm.get("split"):
    raise SystemExit("historical source split differs from catalogue")
PY
gunzip -c "$IN/history.jnnw.gz" > "$W/history.raw.jnnw"
gunzip -c "$IN/history.jsm.gz" > "$W/history.raw.jsm"
HISTORY_DATA_SHA=$(sha256sum "$W/history.raw.jnnw" | awk '{print $1}')
HISTORY_META_SHA=$(sha256sum "$W/history.raw.jsm" | awk '{print $1}')
python3 - "$IN/history-auth.json" "$HISTORY_ARM" "$HISTORY_DATA_SHA" \
  "$HISTORY_META_SHA" <<'PY'
import json
import sys
arm = json.load(open(sys.argv[1]))["arms"][sys.argv[2]]
if (
    arm.get("data_raw_sha256") != sys.argv[3]
    or arm.get("meta_raw_sha256") not in (None, sys.argv[4])
):
    raise SystemExit("historical raw JNNW/JSM1 hash differs from catalogue")
PY

phase reproduce-historical-split
python3 tools/selfplay_frontier.py split \
  --data "$W/history.raw.jnnw" --meta "$W/history.raw.jsm" \
  --out-data "$W/history.fit.jnnw" --out-meta "$W/history.fit.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$ART/history-split.json" > "$W/history-split.log" 2>&1
cmp -s "$IN/source-split.json" "$ART/history-split.json" ||
  die "historical split reproduction drift"

phase fetch-and-authenticate-hard-catalogue
python3 jobs/tools/fetch_result_files.py --prefix "$HARD_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=hard-summary.json \
  --file artefacts/hard-replay.jnnw.gz=hard-replay.jnnw.gz \
  --file artefacts/hard-replay.jsm.gz=hard-replay.jsm.gz \
  --file artefacts/hard-seeds.jnnw.gz=hard-seeds.jnnw.gz \
  --file artefacts/hard-mining-manifest.json=hard-mining-manifest.json \
  --file artefacts/history-split.json=hard-history-split.json \
  --out-dir "$IN" --report "$ART/verified-hard-catalogue.json" \
  > "$W/fetch-hard.log" 2>&1
python3 - "$ART/verified-hard-catalogue.json" "$IN/hard-summary.json" \
  "$IN/hard-mining-manifest.json" "$IN/hard-history-split.json" \
  "$EXPECTED_HARD_JOB" "$EXPECTED_HARD_ATTEMPT" \
  "$EXPECTED_HARD_CODE_SHA" "$EXPECTED_HARD_VERDICT" \
  "$HISTORY_DATA_SHA" "$HISTORY_META_SHA" "$ART/history-split.json" \
  "$W/history.fit.jnnw" "$W/history.fit.jsm" <<'PY'
import hashlib
import json
import sys

def digest(path):
    value = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()

report = json.load(open(sys.argv[1]))
summary = json.load(open(sys.argv[2]))
mining = json.load(open(sys.argv[3]))
hard_split = json.load(open(sys.argv[4]))
if (
    report.get("job_id") != sys.argv[5]
    or report.get("attempt_id") != sys.argv[6]
    or report.get("code_sha") != sys.argv[7]
    or report.get("result_state") != "completed"
    or summary.get("schema") != 1
    or summary.get("verdict") != sys.argv[8]
    or summary.get("code_sha") != sys.argv[7]
    or summary.get("selection", {}).get("capacity_sufficient") is not True
    or summary.get("training_authorized") is not True
    or summary.get("promotion_authorized") is not False
    or summary.get("automatic_next_job") is not None
    or summary.get("external_teacher_inputs") != 0
    or summary.get("selection", {}).get("manifest") != mining
):
    raise SystemExit("HARD catalogue identity/certificate mismatch")
if (
    summary.get("source", {}).get("data_sha256") != sys.argv[9]
    or summary.get("source", {}).get("meta_sha256") != sys.argv[10]
    or summary.get("source", {}).get("split") != hard_split
    or hard_split != json.load(open(sys.argv[11]))
    or mining.get("input", {}).get("data_sha256") != digest(sys.argv[12])
    or mining.get("input", {}).get("meta_sha256") != digest(sys.argv[13])
    or mining.get("input", {}).get("split_manifest_sha256")
       != digest(sys.argv[11])
):
    raise SystemExit("HARD catalogue is not linked to the authenticated source")
actual = {row["local_name"]: row["sha256"] for row in report["files"]}
for name in (
    "hard-replay.jnnw.gz",
    "hard-replay.jsm.gz",
    "hard-seeds.jnnw.gz",
):
    if actual.get(name) != summary.get("outputs", {}).get(name):
        raise SystemExit(f"HARD compressed hash mismatch for {name}")
PY
gunzip -c "$IN/hard-replay.jnnw.gz" > "$W/hard-replay.jnnw"
gunzip -c "$IN/hard-replay.jsm.gz" > "$W/hard-replay.jsm"
gunzip -c "$IN/hard-seeds.jnnw.gz" > "$W/hard-seeds.jnnw"
python3 - "$IN/hard-mining-manifest.json" "$W/hard-replay.jnnw" \
  "$W/hard-replay.jsm" "$W/hard-seeds.jnnw" <<'PY'
import hashlib
import json
import sys
manifest = json.load(open(sys.argv[1]))
for name, path in (
    ("hard_replay", sys.argv[2]),
    ("hard_replay_meta", sys.argv[3]),
    ("hard_seeds", sys.argv[4]),
):
    if hashlib.sha256(open(path, "rb").read()).hexdigest() != (
        manifest.get("outputs", {}).get(name, {}).get("sha256")
    ):
        raise SystemExit(f"HARD raw hash mismatch for {name}")
PY

phase targeted-tests
python3 -m py_compile tools/selfplay_frontier.py \
  jobs/tools/l3_reverse_seed_matching.py
python3 -m unittest jobs.tests.test_l3_reverse_seed_matching \
  > "$W/test-reverse-seed-matching.log" 2>&1

match_once(){
  local suffix="$1"
  mkdir -p "$W/match-$suffix"
  (
    cd "$W/match-$suffix"
    PYTHONPATH="$JASS_CODE_DIR" python3 \
      "$JASS_CODE_DIR/jobs/tools/l3_reverse_seed_matching.py" \
      --history-data "$W/history.fit.jnnw" \
      --history-meta "$W/history.fit.jsm" \
      --history-split-manifest "$ART/history-split.json" \
      --hard-replay "$W/hard-replay.jnnw" \
      --hard-meta "$W/hard-replay.jsm" \
      --hard-seeds "$W/hard-seeds.jnnw" \
      --hard-manifest "$IN/hard-mining-manifest.json" \
      --expected-hard-code-sha "$EXPECTED_HARD_CODE_SHA" \
      --source-temporal-id "$SOURCE_TEMPORAL_ID" \
      --matching-seed "$MATCHING_SEED" --code-sha "$EXPECTED_CODE_SHA" \
      --out-control-seeds control-seeds.jnnw \
      --out-treatment-seeds treatment-seeds.jnnw \
      --manifest reverse-seed-matching.json
  ) > "$W/matching-$suffix.log" 2>&1
}

phase match-catalogues-twice
match_once a
match_once b
for name in control-seeds.jnnw treatment-seeds.jnnw \
  reverse-seed-matching.json; do
  cmp -s "$W/match-a/$name" "$W/match-b/$name" ||
    die "reverse-seed matching is not bit deterministic: $name"
done

phase publish-data-only-certificate
cp "$W/match-a/control-seeds.jnnw" "$ART/control-seeds.jnnw"
cp "$W/match-a/treatment-seeds.jnnw" "$ART/treatment-seeds.jnnw"
cp "$W/match-a/reverse-seed-matching.json" \
  "$ART/reverse-seed-matching.json"
python3 - "$ART" "$ART/reverse-seed-matching.json" \
  "$EXPECTED_CODE_SHA" "$SOURCE_TEMPORAL_ID" \
  "$EXPECTED_HISTORY_JOB" "$EXPECTED_HISTORY_ATTEMPT" \
  "$EXPECTED_HISTORY_CODE_SHA" "$EXPECTED_HARD_JOB" \
  "$EXPECTED_HARD_ATTEMPT" "$EXPECTED_HARD_CODE_SHA" \
  "$EXPECTED_HARD_VERDICT" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

art, matching_path = map(Path, sys.argv[1:3])
matching = json.load(open(matching_path))
if (
    matching.get("probe_authorized") is not True
    or matching.get("training_authorized") is not False
    or matching.get("promotion_authorized") is not False
    or matching.get("automatic_next_job") is not None
):
    raise SystemExit("matching certificate authorization drift")
payload = {
    "schema": 1,
    "verdict": "L3_PURE_REVERSE_SEED_CATALOGUE_READY",
    "code_sha": sys.argv[3],
    "source_temporal_id": sys.argv[4],
    "source": {
        "job_id": sys.argv[5],
        "attempt_id": sys.argv[6],
        "code_sha": sys.argv[7],
    },
    "hard_catalogue": {
        "job_id": sys.argv[8],
        "attempt_id": sys.argv[9],
        "code_sha": sys.argv[10],
        "required_verdict": sys.argv[11],
        "manifest_sha256": matching["upstream_hard"]["manifest_sha256"],
    },
    "matching_manifest_sha256": hashlib.sha256(
        matching_path.read_bytes()
    ).hexdigest(),
    "outputs": {
        name: {
            "sha256": hashlib.sha256((art / name).read_bytes()).hexdigest(),
            "records": matching["outputs"][key]["records"],
        }
        for name, key in (
            ("control-seeds.jnnw", "control_seeds"),
            ("treatment-seeds.jnnw", "treatment_seeds"),
        )
    },
    "probe_authorized": True,
    "training_authorized": False,
    "promotion_authorized": False,
    "automatic_next_job": None,
    "external_teacher_inputs": 0,
}
(art / "JASS_CONTROL_SUMMARY.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
(art / "VERDICT__L3_PURE_REVERSE_SEED_CATALOGUE_READY").touch()
(art / "TRAINING_AUTHORIZED__FALSE").touch()
(art / "PROMOTION_AUTHORIZED__FALSE").touch()
(art / "AUTOMATIC_NEXT_JOB__NULL").touch()
print(
    "  matched reverse-seed catalogue: "
    f"records={payload['outputs']['control-seeds.jnnw']['records']}"
)
PY

phase complete
say "L3_PURE_REVERSE_SEED_CATALOGUE_READY training=false promotion=false automatic_next_job=null"
