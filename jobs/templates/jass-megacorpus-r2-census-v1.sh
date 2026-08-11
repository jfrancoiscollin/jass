#!/usr/bin/env bash
# Jass MegaCorpus v1 — read-only R2 census and runner metadata audit.
# No corpus/model payload, frozen cohort, teacher, fit, match, or continuation.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
META="$W/metadata"
CAT="$W/catalog"
mkdir -p "$W" "$ART" "$META" "$CAT"
RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
STAGE="$W/stage.txt"
R2_LIST_TIMEOUT_SECONDS="${R2_LIST_TIMEOUT_SECONDS:-1800}"
R2_METADATA_TIMEOUT_SECONDS="${R2_METADATA_TIMEOUT_SECONDS:-1800}"
: >"$RES"
echo preflight >"$STAGE"
MON=""

say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
phase(){ echo "$1" >"$STAGE"; say "phase=$1"; }
monitor(){
  (
    local t0; t0=$(date +%s)
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_s=%s\n' "$(( $(date +%s) - t0 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
      } >"$PROG.tmp"
      mv "$PROG.tmp" "$PROG"
      cp "$PROG" "$ART/PROGRESS.txt"
      sleep 30
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
  rm -rf "$META" "$CAT" "$W/r2-objects.json" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${CENSUS_ONLY_APPROVED:-0}" = 1 ] || die "census-only authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "${NO_PAYLOAD_DOWNLOADS:-0}" = 1 ] || die "payload download guard missing"
[[ "$R2_LIST_TIMEOUT_SECONDS" =~ ^[0-9]+$ ]] || die "invalid R2 list timeout"
[[ "$R2_METADATA_TIMEOUT_SECONDS" =~ ^[0-9]+$ ]] || die "invalid R2 metadata timeout"
[ "$R2_LIST_TIMEOUT_SECONDS" -ge 60 ] && [ "$R2_LIST_TIMEOUT_SECONDS" -le 21600 ] || die "R2 list timeout outside 60..21600 s"
[ "$R2_METADATA_TIMEOUT_SECONDS" -ge 60 ] && [ "$R2_METADATA_TIMEOUT_SECONDS" -le 21600 ] || die "R2 metadata timeout outside 60..21600 s"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -ge 2048 ] || die "need 2 GiB free"
command -v rclone >/dev/null || die "rclone missing"
python3 -m py_compile jobs/tools/jass_megacorpus_catalog.py
python3 -m unittest jobs.tests.test_jass_megacorpus_catalog \
  jobs.tests.test_jass_megacorpus_census_template \
  >"$W/catalog-tests.log" 2>&1
monitor

phase list-all-r2-objects
timeout "${R2_LIST_TIMEOUT_SECONDS}s" rclone lsjson "$JASS_OBJSTORE_REMOTE" --recursive --files-only \
  >"$W/r2-objects.json" 2>"$W/rclone-lsjson.log"
[ -s "$W/r2-objects.json" ] || die "R2 object census is empty"

phase fetch-control-metadata-only
timeout "${R2_METADATA_TIMEOUT_SECONDS}s" rclone copy "$JASS_OBJSTORE_REMOTE" "$META" \
  --filter '+ /runs/**/manifest.json' \
  --filter '+ /runs/**/inventory.json' \
  --filter '+ /runs/**/checksums.sha256' \
  --filter '+ /runs/**/_SUCCESS' \
  --filter '+ /runs/**/_FAILED' \
  --filter '+ /historical/**/*.json' \
  --filter '+ /historical/**/manifests/paths.jsonl.gz' \
  --filter '- **' \
  >"$W/rclone-metadata.log" 2>&1

phase build-fail-closed-catalogue
python3 jobs/tools/jass_megacorpus_catalog.py \
  --object-index "$W/r2-objects.json" \
  --metadata-root "$META" \
  --remote-root "$JASS_OBJSTORE_REMOTE" \
  --out-dir "$CAT" >"$W/catalog.log" 2>&1
cp "$CAT/catalog-summary.json" "$ART/catalog-summary.json"
gzip -c "$CAT/r2-objects.jsonl" >"$ART/r2-objects.jsonl.gz"
gzip -c "$CAT/runner-attempts.jsonl" >"$ART/runner-attempts.jsonl.gz"
gzip -c "$CAT/corpus-candidates.jsonl" >"$ART/corpus-candidates.jsonl.gz"

phase publish-census-certificate
python3 - "$ART/catalog-summary.json" "$ART/JASS_CONTROL_SUMMARY.json" \
  "$EXPECTED_CODE_SHA" <<'PY'
import json,sys
from pathlib import Path
summary=json.loads(Path(sys.argv[1]).read_text())
if summary.get("corpus_candidate_count",0) <= 0:
    raise SystemExit("n=0 corpus candidates")
if summary.get("payload_objects_downloaded") != 0:
    raise SystemExit("payload guard violated")
payload={
    "schema": 1,
    "verdict": "JASS_MEGACORPUS_R2_CENSUS_READY",
    "code_sha": sys.argv[3],
    "catalog_schema": summary["schema"],
    "object_count": summary["object_count"],
    "object_bytes": summary["object_bytes"],
    "runner_attempt_count": summary["runner_attempt_count"],
    "runner_attempts_by_audit_state": summary["runner_attempts_by_audit_state"],
    "corpus_candidate_count": summary["corpus_candidate_count"],
    "direct_corpus_candidate_count": summary["direct_corpus_candidate_count"],
    "historical_snapshot_candidate_count": summary["historical_snapshot_candidate_count"],
    "candidates_by_disposition": summary["candidates_by_disposition"],
    "payload_objects_downloaded": 0,
    "frozen_cohorts_read": 0,
    "external_teacher_inputs": 0,
    "training_authorized": False,
    "promotion_authorized": False,
    "automatic_next_job": None,
}
Path(sys.argv[2]).write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
PY
touch "$ART/VERDICT__JASS_MEGACORPUS_R2_CENSUS_READY"
touch "$ART/TRAINING_AUTHORIZED__FALSE"
touch "$ART/PROMOTION_AUTHORIZED__FALSE"
touch "$ART/AUTOMATIC_NEXT_JOB__NULL"
phase complete
say "JASS_MEGACORPUS_R2_CENSUS_READY training=false promotion=false automatic_next_job=null"
