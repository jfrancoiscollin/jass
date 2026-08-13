#!/usr/bin/env bash
# MegaCorpus P1: metadata-only triage and evidence-backed lineage graph.
# Downloads only the P0 catalogue and runner audit JSONL files.  It never opens
# JNNW/JSM/model payloads, frozen cohorts, strength results, or training data.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${P0_ATTEMPT_URI:?}"
: "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; IN="$W/input"; OUT="$W/output"
mkdir -p "$IN" "$OUT" "$ART"
RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  cp "$RES" "$ART/RESULTS.txt"
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${METADATA_ONLY_APPROVED:-0}" = 1 ] || die "metadata-only authorization missing"
[ "${NO_PAYLOAD_DOWNLOADS:-0}" = 1 ] || die "payload download guard missing"
[ "${NO_FROZEN_READS:-0}" = 1 ] || die "frozen read guard missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
command -v rclone >/dev/null || die "rclone missing"
python3 -m py_compile jobs/tools/jass_megacorpus_p1_triage.py
python3 -m unittest jobs.tests.test_jass_megacorpus_p1_triage \
  jobs.tests.test_jass_megacorpus_p1_template >"$W/tests.log" 2>&1

say "phase=fetch-exact-p0-catalogue-metadata"
for name in catalog-summary.json corpus-candidates.jsonl.gz runner-attempts.jsonl.gz; do
  timeout 300s rclone copyto "$P0_ATTEMPT_URI/$name" "$IN/$name" \
    --retries 3 --low-level-retries 10
done

say "phase=authenticate-p0-catalogue"
python3 - "$IN" <<'PY'
import gzip, hashlib, json, sys
from pathlib import Path
root=Path(sys.argv[1]); summary=json.loads((root/'catalog-summary.json').read_text())
if summary.get('schema')!='jass.megacorpus.catalog.v1': raise SystemExit('unexpected P0 schema')
if summary.get('operation')!='read_only_r2_census': raise SystemExit('unexpected P0 operation')
for compressed,name in [('corpus-candidates.jsonl.gz','corpus-candidates.jsonl'),
                        ('runner-attempts.jsonl.gz','runner-attempts.jsonl')]:
    digest=hashlib.sha256(); lines=0
    with gzip.open(root/compressed,'rb') as handle:
        for line in handle: digest.update(line); lines += bool(line.strip())
    expected=summary['catalog_files'][name]['sha256']
    if digest.hexdigest()!=expected: raise SystemExit(f'{name}: P0 digest mismatch')
    expected_lines=summary['corpus_candidate_count' if name.startswith('corpus-') else 'runner_attempt_count']
    if lines!=expected_lines: raise SystemExit(f'{name}: P0 row count mismatch')
if summary.get('payload_objects_downloaded') != 0: raise SystemExit('P0 payload guard failed')
PY

say "phase=metadata-only-p1-triage"
python3 jobs/tools/jass_megacorpus_p1_triage.py \
  --candidates "$IN/corpus-candidates.jsonl.gz" \
  --attempts "$IN/runner-attempts.jsonl.gz" --out-dir "$OUT" >"$W/triage.log" 2>&1

cp "$OUT/p1-summary.json" "$ART/p1-summary.json"
cp "$OUT/review-candidates.json" "$ART/review-candidates.json"
cp "$OUT/quarantine-groups.json" "$ART/quarantine-groups.json"
gzip -c "$OUT/candidate-triage.jsonl" >"$ART/candidate-triage.jsonl.gz"
gzip -c "$OUT/lineage-graph.jsonl" >"$ART/lineage-graph.jsonl.gz"
gzip -c "$OUT/exact-duplicate-groups.jsonl" >"$ART/exact-duplicate-groups.jsonl.gz"

say "phase=publish-bounded-scientific-summary"
python3 - "$OUT" "$ART/scientific-summary.json" <<'PY'
import json,sys
from pathlib import Path
root,out=Path(sys.argv[1]),Path(sys.argv[2])
payload={
 'schema':'jass.megacorpus.p1_readout.v1',
 'p1-summary.json':json.loads((root/'p1-summary.json').read_text()),
 'review-candidates.json':json.loads((root/'review-candidates.json').read_text()),
 'quarantine-groups.json':json.loads((root/'quarantine-groups.json').read_text()),
}
raw=json.dumps(payload,indent=2,sort_keys=True)+'\n'
if len(raw.encode())>60000: raise SystemExit('scientific summary exceeds runner transport cap')
out.write_text(raw)
PY
cp "$ART/scientific-summary.json" "$ART/JASS_CONTROL_SUMMARY.json"
touch "$ART/VERDICT__JASS_MEGACORPUS_P1_TRIAGE_READY"
touch "$ART/PAYLOAD_SAMPLE_AUTHORIZED__FALSE" "$ART/TRAINING_AUTHORIZED__FALSE"
touch "$ART/PROMOTION_AUTHORIZED__FALSE" "$ART/AUTOMATIC_NEXT_JOB__NULL"
say "JASS_MEGACORPUS_P1_TRIAGE_READY payload_sample=false training=false promotion=false automatic_next_job=null"
