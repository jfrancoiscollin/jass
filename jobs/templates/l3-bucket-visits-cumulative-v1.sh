#!/usr/bin/env bash
# template: L3-PURE 8cf bucket-visit diagnostic — CUMULATIVE v1 (plan 6.4)
# description: tally per-bucket visits over the full current-recipe family
#              (five C2-X1 cells g1+g2 ~= 1.5M records) to close the 8cf->32cf
#              capacity question on real cumulative volume, not a single cell.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"; : "${JASS_JOB_ID:?}"
: "${EXPECTED_CODE_SHA:?wrapper must pin the reviewed develop SHA}"
# Immutable C2-X1 cell URIs (0817-0821), all seed 271828, current recipe / L2=3e-5.
PREFIXES=(
  "r2:jass-data/runs/cpx62-0817-l3-c2x1-hhh-control-v1/20260718T221711Z-7a35084f"
  "r2:jass-data/runs/cpx62-0818-l3-c2x1-llh-v1/20260718T222242Z-7a35084f"
  "r2:jass-data/runs/cpx62-0819-l3-c2x1-hll-v1/20260718T222759Z-7a35084f"
  "r2:jass-data/runs/cpx62-0820-l3-c2x1-lhl-v1/20260718T223320Z-7a35084f"
  "r2:jass-data/runs/cpx62-0821-l3-c2x1-center-v1/20260718T223829Z-7a35084f"
)
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART" "$GEOM"
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }
RES="$W/RESULTS.txt"; : > "$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT; set +e; [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt";
  [ -d "$W" ] && (cd "$W" && find . -type f -name '*.log' -print0|tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null||true; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR

say "=== $JASS_JOB_ID — L3-PURE 8cf bucket-visit CUMULATIVE diagnostic v1 ==="
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
ACTUAL_SHA="$(git rev-parse HEAD)"; [ "$ACTUAL_SHA" = "$EXPECTED_CODE_SHA" ] || die "code SHA $ACTUAL_SHA != $EXPECTED_CODE_SHA"
FREE_MB="$(df -Pm "$JASS_RESULT_DIR"|awk 'NR==2{print $4}')"; [ "${FREE_MB:-0}" -ge 3000 ] || die "<3GiB free"
say "preflight: nproc=$(nproc) free_mb=$FREE_MB cells=${#PREFIXES[@]}"

python3 -m py_compile jobs/tools/l3_bucket_visits.py jobs/tools/fetch_result_files.py
python3 jobs/tests/test_l3_bucket_visits.py > "$W/t-bv.log" 2>&1 || die "bucket-visit tests red"

python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen-8cf.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
NPAT="$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')"
[ "$NPAT" -eq 4251528 ] || die "8cf geometry mismatch: n_pat=$NPAT"

DATA=()
i=0
for P in "${PREFIXES[@]}"; do
  python3 jobs/tools/fetch_result_files.py --prefix "$P" \
    --file artefacts/g1-selfplay.jnnw.gz=c${i}-g1.jnnw.gz \
    --file artefacts/g2-selfplay.jnnw.gz=c${i}-g2.jnnw.gz \
    --expected-state completed --out-dir "$W" --report "$ART/verified-c${i}.json" > "$W/fetch-c${i}.log" 2>&1 \
    || die "corpus fetch failed for $P"
  gunzip -c "$W/c${i}-g1.jnnw.gz" > "$W/c${i}-g1.jnnw"; gunzip -c "$W/c${i}-g2.jnnw.gz" > "$W/c${i}-g2.jnnw"
  [ -s "$W/c${i}-g1.jnnw" ] && [ -s "$W/c${i}-g2.jnnw" ] || die "corpus c${i} empty"
  DATA+=("$W/c${i}-g1.jnnw" "$W/c${i}-g2.jnnw")
  i=$((i+1))
done
say "fetched ${#DATA[@]} corpus files from ${#PREFIXES[@]} cells"

env PYTHONPATH="$GEOM:pattern_jass/tools" python3 jobs/tools/l3_bucket_visits.py \
  --data "${DATA[@]}" --out "$ART/bucket-visits-cumulative.json" --top-k 100 > "$W/bv-run.log" 2>&1 \
  || die "bucket-visit tool failed"
cat "$ART/bucket-visits-cumulative.json" | tee -a "$RES"

python3 - "$ART/bucket-visits-cumulative.json" "$ART/c0-decision.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
out={"job":"l3-bucket-visits-cumulative","geometry":d["geometry"],"corpus":d["corpus"],
     "coverage":d["coverage"],"concentration":d["concentration"],
     "capacity_heuristic":d["capacity_heuristic"],"note":d["note"]}
json.dump(out,open(sys.argv[2],"w"),indent=2,sort_keys=True); print("inlined summary")
PY
say "=== cumulative bucket-visit diagnostic complete ==="
