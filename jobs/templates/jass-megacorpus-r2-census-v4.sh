#!/usr/bin/env bash
# Jass MegaCorpus v4 — resumable, adaptively sharded, read-only R2 census.
# No corpus/model payload, frozen cohort, fit, match, or automatic continuation.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; CHECK="$ART/checkpoints"
META="$W/metadata"; CAT="$W/catalog"; INDEX="$W/r2-objects.json"
METADATA_FILES="$W/metadata-files.txt"
mkdir -p "$W" "$ART" "$META" "$CAT" "$CHECK"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/stage.txt"
SHARD_TIMEOUT_SECONDS="${SHARD_TIMEOUT_SECONDS:-900}"
DISCOVERY_TIMEOUT_SECONDS="${DISCOVERY_TIMEOUT_SECONDS:-300}"
METADATA_CHUNK_TIMEOUT_SECONDS="${METADATA_CHUNK_TIMEOUT_SECONDS:-900}"
: >"$RES"; echo preflight >"$STAGE"; MON=""

say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
phase(){ echo "$1" >"$STAGE"; say "phase=$1"; }
monitor(){
  ( local t0; t0=$(date +%s)
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_s=%s\n' "$(( $(date +%s) - t0 ))"
        printf 'checkpoint_shards=%s\n' "$(find "$CHECK/shards" -type f 2>/dev/null | wc -l)"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
      } >"$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 30
    done ) >/dev/null 2>&1 & MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt"; [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$META" "$CAT" "$INDEX" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${CENSUS_ONLY_APPROVED:-0}" = 1 ] || die "census-only authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "${NO_PAYLOAD_DOWNLOADS:-0}" = 1 ] || die "payload download guard missing"
for value in "$SHARD_TIMEOUT_SECONDS" "$DISCOVERY_TIMEOUT_SECONDS" "$METADATA_CHUNK_TIMEOUT_SECONDS"; do
  [[ "$value" =~ ^[0-9]+$ ]] && [ "$value" -ge 60 ] && [ "$value" -le 3600 ] || die "invalid bounded timeout"
done
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -ge 4096 ] || die "need 4 GiB free"
command -v rclone >/dev/null || die "rclone missing"
python3 -m py_compile jobs/tools/jass_megacorpus_r2_shards.py jobs/tools/jass_megacorpus_catalog.py
python3 -m unittest jobs.tests.test_jass_megacorpus_r2_shards \
  jobs.tests.test_jass_megacorpus_catalog jobs.tests.test_jass_megacorpus_census_v4_template \
  >"$W/catalog-tests.log" 2>&1
monitor

if [ -n "${MEGACORPUS_RESUME_URI:-}" ]; then
  phase restore-metadata-only-checkpoint
  rclone copy "$MEGACORPUS_RESUME_URI" "$CHECK" \
    --include 'state.json' --include 'summary.json' --include 'shards/**' --exclude '**'
fi

phase adaptive-sharded-r2-index
python3 jobs/tools/jass_megacorpus_r2_shards.py \
  --remote "$JASS_OBJSTORE_REMOTE" --checkpoint-dir "$CHECK" \
  --object-index "$INDEX" --metadata-files "$METADATA_FILES" \
  --split-depth 2 --max-depth 6 \
  --shard-timeout-seconds "$SHARD_TIMEOUT_SECONDS" \
  --discovery-timeout-seconds "$DISCOVERY_TIMEOUT_SECONDS" \
  ${EXCLUDE_JOB_SCRATCH:+--exclude-job-scratch} \
  >"$W/sharded-index.log" 2>&1
[ -s "$INDEX" ] || die "sharded R2 object census is empty"
[ -s "$METADATA_FILES" ] || die "metadata object list is empty"

phase fetch-exact-control-metadata
split -l 500 -d -a 5 "$METADATA_FILES" "$W/metadata-chunk-"
for chunk in "$W"/metadata-chunk-*; do
  marker="$CHECK/metadata-$(basename "$chunk").done"
  [ -f "$marker" ] && continue
  timeout "${METADATA_CHUNK_TIMEOUT_SECONDS}s" rclone copy \
    "$JASS_OBJSTORE_REMOTE" "$META" --files-from-raw "$chunk" --no-traverse \
    >"$chunk.log" 2>&1
  touch "$marker"
done

phase build-fail-closed-catalogue
python3 jobs/tools/jass_megacorpus_catalog.py \
  --object-index "$INDEX" --metadata-root "$META" \
  --remote-root "$JASS_OBJSTORE_REMOTE" --out-dir "$CAT" >"$W/catalog.log" 2>&1
cp "$CAT/catalog-summary.json" "$ART/catalog-summary.json"
gzip -c "$CAT/r2-objects.jsonl" >"$ART/r2-objects.jsonl.gz"
gzip -c "$CAT/runner-attempts.jsonl" >"$ART/runner-attempts.jsonl.gz"
gzip -c "$CAT/corpus-candidates.jsonl" >"$ART/corpus-candidates.jsonl.gz"

phase publish-census-certificate
python3 - "$ART/catalog-summary.json" "$ART/JASS_CONTROL_SUMMARY.json" "$EXPECTED_CODE_SHA" <<'PY'
import json,sys
from pathlib import Path
s=json.loads(Path(sys.argv[1]).read_text())
if s.get("corpus_candidate_count",0)<=0 or s.get("payload_objects_downloaded")!=0:
    raise SystemExit("invalid census result")
p={"schema":2,"verdict":"JASS_MEGACORPUS_R2_CENSUS_READY","code_sha":sys.argv[3],
   "catalog_schema":s["schema"],"object_count":s["object_count"],
   "object_bytes":s["object_bytes"],"runner_attempt_count":s["runner_attempt_count"],
   "corpus_candidate_count":s["corpus_candidate_count"],
   "candidate_bytes_known":s["candidate_bytes_known"],
   "candidates_by_disposition":s["candidates_by_disposition"],
   "payload_objects_downloaded":0,"frozen_cohorts_read":0,
   "training_authorized":False,"promotion_authorized":False,"automatic_next_job":None}
Path(sys.argv[2]).write_text(json.dumps(p,indent=2,sort_keys=True)+"\n")
PY
touch "$ART/VERDICT__JASS_MEGACORPUS_R2_CENSUS_READY"
touch "$ART/TRAINING_AUTHORIZED__FALSE" "$ART/PROMOTION_AUTHORIZED__FALSE" "$ART/AUTOMATIC_NEXT_JOB__NULL"
phase complete
say "JASS_MEGACORPUS_R2_CENSUS_READY training=false promotion=false automatic_next_job=null"
