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
: "${HISTORY_DATA_GZ_SHA:?}"; : "${HISTORY_META_GZ_SHA:?}"
: "${HISTORY_DATA_SHA:?}"; : "${HISTORY_META_SHA:?}"

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
  "$EXPECTED_HISTORY_STATE" "$HISTORY_DATA_GZ_SHA" "$HISTORY_META_GZ_SHA" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
if (
    report.get("job_id") != sys.argv[2]
    or report.get("attempt_id") != sys.argv[3]
    or report.get("code_sha") != sys.argv[4]
    or report.get("result_state") != sys.argv[5]
):
    raise SystemExit("historical source identity/state mismatch")
expected = {
    "history.jnnw.gz": sys.argv[6],
    "history.jsm.gz": sys.argv[7],
}
actual = {row["local_name"]: row["sha256"] for row in report["files"]}
for name, digest in expected.items():
    if actual.get(name) != digest:
        raise SystemExit(f"historical compressed hash mismatch for {name}")
PY
gunzip -c "$IN/history.jnnw.gz" > "$W/history.raw.jnnw"
gunzip -c "$IN/history.jsm.gz" > "$W/history.raw.jsm"
[ "$(sha256sum "$W/history.raw.jnnw" | awk '{print $1}')" = "$HISTORY_DATA_SHA" ] ||
  die "historical JNNW hash drift"
[ "$(sha256sum "$W/history.raw.jsm" | awk '{print $1}')" = "$HISTORY_META_SHA" ] ||
  die "historical JSM1 hash drift"
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
python3 - "$W/hard-replay-a.jnnw" "$ART/hard-mining-a.json" \
  "$REPLAY_RECORDS" <<'PY'
import json
import struct
import sys
path, manifest_path, expected = sys.argv[1], sys.argv[2], int(sys.argv[3])
with open(path, "rb") as stream:
    head = stream.read(8)
if len(head) != 8 or head[:4] != b"JNNW":
    raise SystemExit("invalid hard replay header")
count = struct.unpack_from("<I", head, 4)[0]
manifest = json.load(open(manifest_path))
if count != expected or manifest["selection"]["output_records"] != expected:
    raise SystemExit(
        f"insufficient hard replay capacity: selected={count} required={expected}"
    )
PY

phase publish-catalogue-and-certificate
gzip -n -c "$W/hard-replay-a.jnnw" > "$ART/hard-replay.jnnw.gz"
gzip -n -c "$W/hard-replay-a.jsm" > "$ART/hard-replay.jsm.gz"
gzip -n -c "$W/hard-seeds-a.jnnw" > "$ART/hard-seeds.jnnw.gz"
cp "$ART/hard-mining-a.json" "$ART/hard-mining-manifest.json"
python3 - "$ART" "$EXPECTED_CODE_SHA" "$EXPECTED_HISTORY_JOB" \
  "$EXPECTED_HISTORY_ATTEMPT" "$HISTORY_DATA_SHA" "$HISTORY_META_SHA" \
  "$REPLAY_RECORDS" "$MINING_SEED" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

art = Path(sys.argv[1])
code_sha, source_job, source_attempt, data_sha, meta_sha = sys.argv[2:7]
records, seed = map(int, sys.argv[7:9])
mining = json.load(open(art / "hard-mining-manifest.json"))
split = json.load(open(art / "history-split.json"))
payload = {
    "schema": 1,
    "verdict": "L3_PURE_HARD_REPLAY_CATALOGUE_READY",
    "code_sha": code_sha,
    "source": {
        "job_id": source_job,
        "attempt_id": source_attempt,
        "data_sha256": data_sha,
        "meta_sha256": meta_sha,
        "split": split,
    },
    "selection": {
        "signal": "failed_conversion",
        "seed": seed,
        "records": records,
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
    "training_authorized": True,
    "promotion_authorized": False,
    "automatic_next_job": None,
    "external_teacher_inputs": 0,
}
(art / "JASS_CONTROL_SUMMARY.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
(art / "VERDICT__L3_PURE_HARD_REPLAY_CATALOGUE_READY").touch()
(art / "PROMOTION_AUTHORIZED__FALSE").touch()
(art / "AUTOMATIC_NEXT_JOB__NULL").touch()
print(
    f"  hard replay catalogue: records={records} "
    f"candidates={mining['candidates']['signal_records']}"
)
PY
phase complete
say "L3_PURE_HARD_REPLAY_CATALOGUE_READY promotion=false automatic_next_job=null"
