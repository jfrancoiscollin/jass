#!/usr/bin/env bash
# L3-PURE — authenticate one historical source and mine HARD_REPLAY v1.
#
# Data-only preflight.  It performs no self-play, fit, match or promotion.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${HISTORY_PREFIX:?}"; : "${EXPECTED_HISTORY_JOB:?}"
: "${EXPECTED_HISTORY_ATTEMPT:?}"; : "${EXPECTED_HISTORY_CODE_SHA:?}"
: "${EXPECTED_HISTORY_STATE:?}"; : "${HISTORY_DATA_ARTEFACT:?}"
: "${HISTORY_META_ARTEFACT:?}"; : "${HISTORY_SPLIT_ARTEFACT:?}"
: "${HISTORY_AUTH_PREFIX:?}"; : "${EXPECTED_HISTORY_AUTH_JOB:?}"
: "${EXPECTED_HISTORY_AUTH_ATTEMPT:?}"; : "${EXPECTED_HISTORY_AUTH_CODE_SHA:?}"
: "${EXPECTED_HISTORY_AUTH_VERDICT:?}"; : "${EXPECTED_HISTORY_RECORDS:?}"
: "${HISTORY_ARM:?}"

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

REPLAY_RECORDS=${REPLAY_RECORDS:-1000000}
MINING_SEED=${MINING_SEED:-1618033}
SPLIT_SEED=${SPLIT_SEED:-577215}
HOLDOUT_MOD=${HOLDOUT_MOD:-10}
MON=""

monitor(){
  (
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
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
  rm -rf "$IN" 2>/dev/null || true
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
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$REPLAY_RECORDS" -eq 1000000 ] ||
  die "full causal protocol requires 1M historical replay records"
[ $((REPLAY_RECORDS % 2)) -eq 0 ] || die "replay count must be even"
[ "$SPLIT_SEED" -eq 577215 ] || die "historical split seed drift"
[ "$HOLDOUT_MOD" -eq 10 ] || die "historical holdout ratio drift"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -ge 12000 ] ||
  die "need 12 GiB free"
monitor

phase fetch-history-catalogue
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
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

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
export HISTORY_DATA_SHA HISTORY_META_SHA
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
python3 jobs/tools/assert_corpus_wdl.py --data "$W/history.raw.jnnw" \
  --out "$ART/history-corpus-wdl.json" > "$W/history-wdl.log" 2>&1 ||
  die "historical WDL canary failed"

phase reproduce-historical-split
python3 tools/selfplay_frontier.py split \
  --data "$W/history.raw.jnnw" --meta "$W/history.raw.jsm" \
  --out-data "$W/history.fit.jnnw" --out-meta "$W/history.fit.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$ART/history-split.json" > "$W/history-split.log" 2>&1
cmp -s "$IN/source-split.json" "$ART/history-split.json" ||
  die "historical split reproduction drift"

phase targeted-tests
python3 -m py_compile tools/selfplay_frontier.py \
  jobs/tools/l3_hard_replay_assembly.py
python3 -m unittest jobs.tests.test_selfplay_hard_mining \
  jobs.tests.test_l3_hard_replay_assembly \
  > "$W/test-hard-replay.log" 2>&1

mine_once(){
  local suffix="$1"
  python3 tools/selfplay_frontier.py mine-hard \
    --data "$W/history.fit.jnnw" --meta "$W/history.fit.jsm" \
    --split-manifest "$ART/history-split.json" \
    --max-records "$REPLAY_RECORDS" --seed "$MINING_SEED" \
    --signal failed_conversion --one-per-game --colour-mirror \
    --code-sha "$EXPECTED_CODE_SHA" \
    --out-replay "$W/hard-replay-$suffix.jnnw" \
    --out-meta "$W/hard-replay-$suffix.jsm" \
    --out-seeds "$W/hard-seeds-$suffix.jnnw" \
    --manifest "$ART/hard-mining-$suffix.json" \
    > "$W/hard-mining-$suffix.log" 2>&1
}

phase mine-hard-replay-twice
mine_once a
mine_once b
cmp -s "$W/hard-replay-a.jnnw" "$W/hard-replay-b.jnnw" ||
  die "hard replay is not bit deterministic"
cmp -s "$W/hard-replay-a.jsm" "$W/hard-replay-b.jsm" ||
  die "hard replay metadata is not bit deterministic"
cmp -s "$W/hard-seeds-a.jnnw" "$W/hard-seeds-b.jnnw" ||
  die "hard seeds are not bit deterministic"
SELECTED_RECORDS=$(python3 - "$W/hard-replay-a.jnnw" \
  "$ART/hard-mining-a.json" <<'PY'
import json
import struct
import sys
path, manifest_path = sys.argv[1], sys.argv[2]
with open(path, "rb") as stream:
    head = stream.read(8)
if len(head) != 8 or head[:4] != b"JNNW":
    raise SystemExit("invalid hard replay header")
count = struct.unpack_from("<I", head, 4)[0]
manifest = json.load(open(manifest_path))
if count != manifest["selection"]["output_records"]:
    raise SystemExit("hard replay count differs from mining manifest")
print(count)
PY
)
export SELECTED_RECORDS
say "  hard replay capacity: selected=$SELECTED_RECORDS required=$REPLAY_RECORDS"

phase publish-catalogue-and-certificate
gzip -n -c "$W/hard-replay-a.jnnw" > "$ART/hard-replay.jnnw.gz"
gzip -n -c "$W/hard-replay-a.jsm" > "$ART/hard-replay.jsm.gz"
gzip -n -c "$W/hard-seeds-a.jnnw" > "$ART/hard-seeds.jnnw.gz"
cp "$ART/hard-mining-a.json" "$ART/hard-mining-manifest.json"
python3 - "$ART" "$IN/history-auth.json" "$IN/history.jnnw.gz" \
  "$IN/history.jsm.gz" "$REPLAY_RECORDS" "$SELECTED_RECORDS" \
  "$MINING_SEED" <<'PY'
import hashlib
import json
import os
import sys
from pathlib import Path

art, auth_path, data_gz, meta_gz = map(Path, sys.argv[1:5])
required, selected, seed = map(int, sys.argv[5:8])
ready = selected == required
verdict = (
    "L3_PURE_HARD_REPLAY_CATALOGUE_READY"
    if ready
    else "L3_PURE_HARD_REPLAY_CATALOGUE_INSUFFICIENT"
)
auth = json.load(open(auth_path))
arm_name = os.environ["HISTORY_ARM"]
auth_arm = auth["arms"][arm_name]
mining = json.load(open(art / "hard-mining-manifest.json"))
split = json.load(open(art / "history-split.json"))
payload = {
    "schema": 1,
    "verdict": verdict,
    "code_sha": os.environ["EXPECTED_CODE_SHA"],
    "source": {
        "job_id": os.environ["EXPECTED_HISTORY_JOB"],
        "attempt_id": os.environ["EXPECTED_HISTORY_ATTEMPT"],
        "code_sha": os.environ["EXPECTED_HISTORY_CODE_SHA"],
        "state": os.environ["EXPECTED_HISTORY_STATE"],
        "arm": arm_name,
        "catalogue_job": os.environ["EXPECTED_HISTORY_AUTH_JOB"],
        "catalogue_attempt": os.environ["EXPECTED_HISTORY_AUTH_ATTEMPT"],
        "catalogue_code_sha": os.environ["EXPECTED_HISTORY_AUTH_CODE_SHA"],
        "data_gz_sha256": hashlib.sha256(data_gz.read_bytes()).hexdigest(),
        "meta_gz_sha256": hashlib.sha256(meta_gz.read_bytes()).hexdigest(),
        "data_sha256": os.environ["HISTORY_DATA_SHA"],
        "meta_sha256": os.environ["HISTORY_META_SHA"],
        "catalogued_data_sha256": auth_arm["data_raw_sha256"],
        "split_sha256": hashlib.sha256(
            (art / "history-split.json").read_bytes()
        ).hexdigest(),
        "split": split,
    },
    "selection": {
        "signal": "failed_conversion",
        "seed": seed,
        "records": selected,
        "required_records": required,
        "capacity_sufficient": ready,
        "manifest": mining,
    },
    "outputs": {
        name: hashlib.sha256((art / name).read_bytes()).hexdigest()
        for name in (
            "hard-replay.jnnw.gz",
            "hard-replay.jsm.gz",
            "hard-seeds.jnnw.gz",
        )
    },
    "training_authorized": ready,
    "promotion_authorized": False,
    "automatic_next_job": None,
    "external_teacher_inputs": 0,
}
(art / "JASS_CONTROL_SUMMARY.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
(art / f"VERDICT__{verdict}").touch()
(art / "PROMOTION_AUTHORIZED__FALSE").touch()
(art / "AUTOMATIC_NEXT_JOB__NULL").touch()
print(
    f"  hard replay catalogue: verdict={verdict} selected={selected} "
    f"required={required} "
    f"candidates={mining['candidates']['signal_records']}"
)
PY
phase complete
VERDICT=$(ls "$ART" | sed -n 's/^VERDICT__//p' | head -1)
say "$VERDICT promotion=false automatic_next_job=null"
