#!/usr/bin/env bash
# Gen2-MMTO D4: profile fully-resolved search fingerprints on frozen weights.
# ARMS_FILE format: name|complete_search_fingerprint (one arm per non-comment line).
set -Eeuo pipefail

: "${JASS_CODE_DIR:?immutable repository checkout required}"
: "${JASS_RESULT_DIR:?runner result directory required}"
: "${JASS_ARTEFACT_DIR:?runner artefact directory required}"
: "${JASS_JOB_ID:?job id required}"
: "${GEN2_PATTERN:?bare Gen2-MMTO PJTW required}"
: "${P3_POOL:?certified P3 pool required}"
: "${BASELINE_P3_JSON:?baseline P3 conversion JSON required}"
: "${OPENINGS_FILE:?fixed generalist openings required}"
: "${BASELINE_SEARCH_PARAMS:?complete baseline fingerprint required}"
: "${ARMS_FILE:?name|complete fingerprint file required}"
: "${APPROVED_ETA_MIN:?measured ETA required}"
: "${FULL_RUN_APPROVED:?set to 1 after approval}"
: "${JFC_GO:?set to 1 after explicit go}"
[[ "$FULL_RUN_APPROVED" == 1 && "$JFC_GO" == 1 ]] || { echo "ABORT: approval missing" >&2; exit 2; }

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$ART"
exec 9>"$JASS_RESULT_DIR/job.lock"; flock -n 9 || { echo "ABORT: instance active" >&2; exit 3; }

GATE_DEPTH="${GATE_DEPTH:-9}"
CONV_DEPTH="${CONV_DEPTH:-10}"
MOVETIME="${MOVETIME:-0.10}"
NOPEN="${NOPEN:-300}"
NSH_GATE="${NSH_GATE:-16}"
PAR_GATE="${PAR_GATE:-8}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-7000}"
BUILD_JOBS="${JASS_BUILD_JOBS:-8}"

for v in GEN2_PATTERN P3_POOL BASELINE_P3_JSON OPENINGS_FILE ARMS_FILE; do
  printf -v "$v" '%s' "$(realpath "${!v}")"
done
say(){ echo "$*" | tee -a "$W/RESULTS.txt"; }
trap 'rc=$?; set +e; cp "$W/RESULTS.txt" "$ART/RESULTS.txt" 2>/dev/null; exit "$rc"' EXIT
say "=== $JASS_JOB_ID code=$(git rev-parse HEAD) eta=${APPROVED_ETA_MIN}min ==="

python3 -m py_compile jobs/tools/gen2_p3_decision_verdict.py
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$BUILD_JOBS" --target jass > "$W/build.log" 2>&1
J="$W/build/jass"
awk -v limit="$NOPEN" '/^[[:space:]]*#/ {next} {sub(/#.*/,""); if (NF) {print; n++; if(n>=limit) exit}}' \
  "$OPENINGS_FILE" > "$W/openings.fen"
[[ "$(wc -l < "$W/openings.fen")" -eq "$NOPEN" ]] || { say "ABORT insufficient openings"; exit 4; }

count=0
while IFS='|' read -r name params; do
  [[ -z "${name// }" || "$name" == \#* ]] && continue
  [[ -n "${params// }" ]] || { say "ABORT arm $name has empty fingerprint"; exit 4; }
  safe=$(printf '%s' "$name" | tr -cs 'A-Za-z0-9_-' '_')
  count=$((count+1)); say "=== arm=$name ==="
  python3 jobs/tools/conv_fixed_wdl.py --jass "$J" --pattern "$GEN2_PATTERN" \
    --defender-pattern "$GEN2_PATTERN" --search-params "$params" \
    --defender-search-params "$BASELINE_SEARCH_PARAMS" --pool-jnnw "$P3_POOL" \
    --depth "$CONV_DEPTH" --out "$W/$safe-conv.json" > "$W/$safe-conv.log" 2>&1
  for mode in depth movetime; do
    budget=(--depth "$GATE_DEPTH"); [[ "$mode" == movetime ]] && budget=(--movetime "$MOVETIME")
    python3 jobs/tools/run_jass_gate_bounded.py --jass "$J" --pattern-a "$GEN2_PATTERN" \
      --pattern-b "$GEN2_PATTERN" --openings-file "$W/openings.fen" \
      --search-params-a "$params" --search-params-b "$BASELINE_SEARCH_PARAMS" \
      "${budget[@]}" --pairs 1 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
      --timeout "$SHARD_TIMEOUT" --work-dir "$W/$safe-$mode" --out "$W/$safe-$mode.json" \
      > "$W/$safe-$mode.log" 2>&1
  done
  python3 - "$name" "$params" "$BASELINE_P3_JSON" "$W/$safe-conv.json" \
    "$W/$safe-depth.json" "$W/$safe-movetime.json" "$ART/$safe-profile.json" <<'PY'
import json,sys
sys.path.insert(0,'jobs/tools')
import gen2_p3_decision_verdict as v
name,params,basep,candp,depthp,mtp,out=sys.argv[1:]
base=json.load(open(basep)); cand=json.load(open(candp)); depth=json.load(open(depthp)); mt=json.load(open(mtp))
paired=v._paired_from_conv(base,cand)
if float(mt.get('ci_low',0))>0.5 and float(depth.get('ci_high',0))>=0.5:
    cls='search_gain'
elif float(mt.get('rate',0))>=0.49 and float(mt.get('ci_high',0))>=0.5 and float(depth.get('ci_high',0))>=0.5:
    cls='nonregressive'
else:
    cls='regression_or_inconclusive'
report={'schema':1,'arm':name,'search_params':params,'classification':cls,
        'paired_p3':paired,'depth_gate':depth,'movetime_gate':mt}
open(out,'w').write(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps({'arm':name,'classification':cls,'p3_delta':paired['delta'],'movetime_rate':mt.get('rate')}))
PY
done < "$ARMS_FILE"
[[ "$count" -gt 0 ]] || { say "ABORT no arms"; exit 4; }
say "profiles=$count; no automatic selection or margin tuning"
