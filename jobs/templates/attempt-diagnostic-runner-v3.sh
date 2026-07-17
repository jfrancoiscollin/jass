#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Compare one authoritative success with a later failed duplicate attempt.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
: "${JASS_ARTEFACT_DIR:?runner v3 must provide JASS_ARTEFACT_DIR}"
: "${SUCCESS_RUN_PREFIX:?completed authoritative result required}"
: "${FAILED_RUN_PREFIX:?failed duplicate result required}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W/success" "$W/failed" "$ART"

python3 jobs/tools/fetch_result_files.py --prefix "$SUCCESS_RUN_PREFIX" \
  --expected-state completed \
  --file manifest.json=success-manifest.json \
  --out-dir "$W/success" --report "$ART/verified-success-result.json"
python3 jobs/tools/fetch_result_files.py --prefix "$FAILED_RUN_PREFIX" \
  --expected-state failed \
  --file manifest.json=failed-manifest.json \
  --file output.log.gz=failed-output.log.gz \
  --out-dir "$W/failed" --report "$ART/verified-failed-result.json"

START="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("started_at",""))' \
  "$W/failed/failed-manifest.json")"
END="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("ended_at",""))' \
  "$W/failed/failed-manifest.json")"
if [ -n "$START" ]; then
  JOURNAL_ARGS=(--since "$START")
  [ -z "$END" ] || JOURNAL_ARGS+=(--until "$END")
  journalctl -u jass-runner-v3.service -u jass-runner.service \
    "${JOURNAL_ARGS[@]}" --no-pager > "$W/journal.log" 2>&1 || true
  journalctl -k "${JOURNAL_ARGS[@]}" --no-pager > "$W/kernel.log" 2>&1 || true
else
  : > "$W/journal.log"; : > "$W/kernel.log"
fi

python3 jobs/tools/attempt_diagnostic.py \
  --success-manifest "$W/success/success-manifest.json" \
  --failed-manifest "$W/failed/failed-manifest.json" \
  --failed-log "$W/failed/failed-output.log.gz" \
  --journal "$W/journal.log" --kernel "$W/kernel.log" \
  --out "$ART/attempt-diagnostic.json"
