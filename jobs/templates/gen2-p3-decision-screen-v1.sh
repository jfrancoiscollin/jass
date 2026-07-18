#!/usr/bin/env bash
# Gen2-MMTO D1: fresh-pool conditional second-pass screen.
# TEMPLATE ONLY. Requires a passing D0 autopsy and a disjoint pool.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?immutable repository checkout required}"
: "${JASS_RESULT_DIR:?runner result directory required}"
: "${JASS_ARTEFACT_DIR:?runner artefact directory required}"
: "${JASS_JOB_ID:?job id required}"
: "${GEN2_PATTERN:?bare Gen2-MMTO PJTW required}"
: "${DEFENDER_PATTERN:?fixed defender PJTW required}"
: "${P3_FRESH_POOL:?fresh certified P3 JNNW required}"
: "${FRESH_BASELINE_JSON:?fresh schema-2 baseline JSON required}"
: "${SEARCH_PARAMS:?fully resolved Gen2 search fingerprint required}"
: "${PRIOR_AUTOPSY_VERDICT:?passing D0 verdict required}"
: "${PRIOR_AUTOPSY_SUMMARY:?D0 summary required for disjointness}"
: "${APPROVED_ETA_MIN:?measured ETA required}"
: "${FULL_RUN_APPROVED:?set to 1 after approval}"
: "${JFC_GO:?set to 1 after explicit go}"
[[ "$FULL_RUN_APPROVED" == 1 && "$JFC_GO" == 1 ]] || { echo "ABORT: approval missing" >&2; exit 2; }

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; OUT="$W/decision"
mkdir -p "$W" "$ART" "$OUT"
exec 9>"$JASS_RESULT_DIR/job.lock"; flock -n 9 || { echo "ABORT: instance active" >&2; exit 3; }

DECISION_DEPTH="${DECISION_DEPTH:-10}"
VERIFY_DEPTH="${VERIFY_DEPTH:-14}"
ROLLOUT_DEPTH="${ROLLOUT_DEPTH:-10}"
TOP_K="${TOP_K:-3}"
MAX_PARENTS="${MAX_PARENTS:-600}"
MAX_PLIES="${MAX_PLIES:-260}"
DEFENDER_SEARCH_PARAMS="${DEFENDER_SEARCH_PARAMS:-$SEARCH_PARAMS}"
BUILD_JOBS="${JASS_BUILD_JOBS:-8}"

for v in GEN2_PATTERN DEFENDER_PATTERN P3_FRESH_POOL FRESH_BASELINE_JSON PRIOR_AUTOPSY_VERDICT PRIOR_AUTOPSY_SUMMARY; do
  printf -v "$v" '%s' "$(realpath "${!v}")"
done
python3 - "$PRIOR_AUTOPSY_VERDICT" "$PRIOR_AUTOPSY_SUMMARY" "$P3_FRESH_POOL" <<'PY'
import hashlib,json,sys
verdict=json.load(open(sys.argv[1])); old=json.load(open(sys.argv[2]))
if verdict.get('stage')!='p3_autopsy' or verdict.get('pass') is not True:
    raise SystemExit('prior D0 autopsy did not pass')
sha=hashlib.sha256(open(sys.argv[3],'rb').read()).hexdigest()
if sha == old.get('pool_sha256'):
    raise SystemExit('fresh screen pool equals autopsy pool')
print('D0 pass and pool disjointness verified')
PY

say(){ echo "$*" | tee -a "$W/RESULTS.txt"; }
trap 'rc=$?; set +e; cp "$W/RESULTS.txt" "$ART/RESULTS.txt" 2>/dev/null; [ -d "$OUT" ] && tar -C "$OUT" -czf "$ART/decision-screen.tar.gz" . 2>/dev/null; exit "$rc"' EXIT
say "=== $JASS_JOB_ID code=$(git rev-parse HEAD) eta=${APPROVED_ETA_MIN}min ==="

python3 -m py_compile jobs/tools/gen2_p3_decision_lab.py jobs/tools/gen2_p3_decision_verdict.py
python3 pattern_jass/tools/gen_patterns.py --variant v4 --emit > "$W/geometry.log" 2>&1
grep -q 'NUM_PATTERNS set to 32' "$W/geometry.log" || { say "ABORT: Gen2 32cf geometry not generated"; exit 4; }
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$BUILD_JOBS" --target jass > "$W/build.log" 2>&1
J="$W/build/jass"
cmd=(python3 jobs/tools/gen2_p3_decision_lab.py
  --jass "$J" --pattern "$GEN2_PATTERN" --defender-pattern "$DEFENDER_PATTERN"
  --pool-jnnw "$P3_FRESH_POOL" --baseline-json "$FRESH_BASELINE_JSON" --scope all
  --decision-depth "$DECISION_DEPTH" --verify-depth "$VERIFY_DEPTH"
  --rollout-depth "$ROLLOUT_DEPTH" --top-k "$TOP_K" --max-parents "$MAX_PARENTS"
  --max-plies "$MAX_PLIES" --work-dir "$W/lab-work" --out-dir "$OUT")
cmd+=(--search-params "$SEARCH_PARAMS")
[[ -z "$DEFENDER_SEARCH_PARAMS" ]] || cmd+=(--defender-search-params "$DEFENDER_SEARCH_PARAMS")
"${cmd[@]}" | tee -a "$W/RESULTS.txt"
python3 jobs/tools/gen2_p3_decision_verdict.py screen --input "$OUT/summary.json" \
  --out "$ART/decision-screen-verdict.json" | tee -a "$W/RESULTS.txt"
cp "$OUT/summary.json" "$ART/decision-screen-summary.json"
say "=== end $JASS_JOB_ID; no runtime integration and no automatic next job ==="
