#!/usr/bin/env bash
# template: L3-PURE 8cf bucket-visit diagnostic v1 (plan 6.4 pre-condition for 32cf)
# description: tally per-bucket visit counts of the current-recipe 8cf corpus
#              (X_HHH_CONTROL 0817 g1+g2) to decide if capacity is data-limited.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"; : "${JASS_JOB_ID:?}"
: "${EXPECTED_CODE_SHA:?wrapper must pin the reviewed develop SHA}"
CORPUS_PREFIX="${CORPUS_PREFIX:-r2:jass-data/runs/cpx62-0817-l3-c2x1-hhh-control-v1/20260718T221711Z-7a35084f}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART" "$GEOM"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }
RES="$W/RESULTS.txt"; : > "$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT; set +e; [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt";
  [ -d "$W" ] && (cd "$W" && find . -type f -name '*.log' -print0|tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null||true; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR

say "=== $JASS_JOB_ID — L3-PURE 8cf bucket-visit diagnostic v1 ==="
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
ACTUAL_SHA="$(git rev-parse HEAD)"; [ "$ACTUAL_SHA" = "$EXPECTED_CODE_SHA" ] || die "code SHA $ACTUAL_SHA != $EXPECTED_CODE_SHA"
FREE_MB="$(df -Pm "$JASS_RESULT_DIR"|awk 'NR==2{print $4}')"; [ "${FREE_MB:-0}" -ge 2000 ] || die "<2GiB free"
say "preflight: nproc=$(nproc) free_mb=$FREE_MB corpus=$CORPUS_PREFIX"

python3 -m py_compile jobs/tools/l3_bucket_visits.py jobs/tools/fetch_result_files.py
python3 jobs/tests/test_l3_bucket_visits.py > "$W/t-bv.log" 2>&1 || die "bucket-visit tests red"

# Freeze the 8cf geometry (the trained parameter space we are measuring).
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen-8cf.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
NPAT="$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')"
[ "$NPAT" -eq 4251528 ] || die "8cf geometry mismatch: n_pat=$NPAT"

# Fetch the current-recipe corpus (X_HHH_CONTROL g1+g2 self-play).
python3 jobs/tools/fetch_result_files.py --prefix "$CORPUS_PREFIX" \
  --file artefacts/g1-selfplay.jnnw.gz=g1.jnnw.gz \
  --file artefacts/g2-selfplay.jnnw.gz=g2.jnnw.gz \
  --expected-state completed --out-dir "$W" --report "$ART/verified-corpus.json" > "$W/fetch.log" 2>&1 \
  || die "corpus fetch failed"
gunzip -c "$W/g1.jnnw.gz" > "$W/g1.jnnw"; gunzip -c "$W/g2.jnnw.gz" > "$W/g2.jnnw"
[ -s "$W/g1.jnnw" ] && [ -s "$W/g2.jnnw" ] || die "corpus empty"

env PYTHONPATH="$GEOM:pattern_jass/tools" python3 jobs/tools/l3_bucket_visits.py \
  --data "$W/g1.jnnw" "$W/g2.jnnw" --out "$ART/bucket-visits.json" --top-k 100 > "$W/bv-run.log" 2>&1 \
  || die "bucket-visit tool failed"
cat "$ART/bucket-visits.json" | tee -a "$RES"

# Inline a compact summary via the allowlisted status-summary name.
python3 - "$ART/bucket-visits.json" "$ART/c0-decision.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
out={"job":"l3-bucket-visits","geometry":d["geometry"],"corpus":d["corpus"],
     "coverage":d["coverage"],"concentration":d["concentration"],
     "capacity_heuristic":d["capacity_heuristic"],"note":d["note"]}
json.dump(out,open(sys.argv[2],"w"),indent=2,sort_keys=True); print("inlined summary")
PY
say "=== bucket-visit diagnostic complete ==="
