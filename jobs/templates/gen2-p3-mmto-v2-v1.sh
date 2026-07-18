#!/usr/bin/env bash
# Gen2-MMTO D3: through-search MMTO-v2 on certified P3 hard negatives.
# TEMPLATE ONLY. Runs only after D0 autopsy and offline ranker both pass.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?immutable repository checkout required}"
: "${JASS_RESULT_DIR:?runner result directory required}"
: "${JASS_ARTEFACT_DIR:?runner artefact directory required}"
: "${JASS_JOB_ID:?job id required}"
: "${GEN2_PATTERN:?bare Gen2-MMTO PJTW required}"
: "${DEFENDER_PATTERN:?fixed defender PJTW required}"
: "${HARD_PAIR_DIR:?directory containing train/holdout hard-pair assets}"
: "${PRIOR_AUTOPSY_VERDICT:?passing autopsy verdict required}"
: "${PRIOR_RANKER_VERDICT:?passing ranker verdict required}"
: "${P3_POOL:?fresh certified P3 pool required}"
: "${BASELINE_P3_JSON:?baseline conversion JSON on exactly P3_POOL required}"
: "${OPENINGS_FILE:?generalist fixed openings required}"
: "${SEARCH_PARAMS:?fully resolved Gen2 search fingerprint required}"
: "${APPROVED_ETA_MIN:?measured ETA required}"
: "${FULL_RUN_APPROVED:?set to 1 after approval}"
: "${JFC_GO:?set to 1 after explicit go}"
[[ "$FULL_RUN_APPROVED" == 1 && "$JFC_GO" == 1 ]] || { echo "ABORT: approval missing" >&2; exit 2; }

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; GEOM="$W/geom"
mkdir -p "$W" "$ART" "$GEOM"
exec 9>"$JASS_RESULT_DIR/job.lock"; flock -n 9 || { echo "ABORT: instance active" >&2; exit 3; }

LEAF_DEPTH="${LEAF_DEPTH:-12}"
RANK_LAM="${RANK_LAM:-0.3}"
MAX_ITER="${MAX_ITER:-80}"
CHUNK="${CHUNK:-100000}"
MIN_PAIRS="${MIN_PAIRS:-2}"
CONV_DEPTH="${CONV_DEPTH:-10}"
GATE_DEPTH="${GATE_DEPTH:-9}"
MOVETIME="${MOVETIME:-0.10}"
NOPEN="${NOPEN:-300}"
NSH_GATE="${NSH_GATE:-16}"
PAR_GATE="${PAR_GATE:-8}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-7000}"
BUILD_JOBS="${JASS_BUILD_JOBS:-8}"
ANCHORS="${ANCHORS:-0.05 0.10}"

for v in GEN2_PATTERN DEFENDER_PATTERN HARD_PAIR_DIR PRIOR_AUTOPSY_VERDICT PRIOR_RANKER_VERDICT P3_POOL BASELINE_P3_JSON OPENINGS_FILE; do
  printf -v "$v" '%s' "$(realpath "${!v}")"
done
python3 - "$PRIOR_AUTOPSY_VERDICT" "$PRIOR_RANKER_VERDICT" <<'PY'
import json,sys
for path,stage in ((sys.argv[1],'p3_autopsy'),(sys.argv[2],'sibling_ranker')):
    x=json.load(open(path))
    if x.get('stage')!=stage or x.get('pass') is not True:
        raise SystemExit(f'prior gate did not pass: {stage}')
print('prior autopsy/ranker gates verified')
PY

say(){ echo "$*" | tee -a "$W/RESULTS.txt"; }
jnnw_count(){ python3 - "$1" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(8)
if len(b)!=8 or b[:4]!=b'JNNW': raise SystemExit(2)
print(struct.unpack('<I',b[4:8])[0])
PY
}
trap 'rc=$?; set +e; cp "$W/RESULTS.txt" "$ART/RESULTS.txt" 2>/dev/null; find "$W" -maxdepth 1 -name "candidate-*.pjtw" -exec sh -c '\''for f; do gzip -n -c "$f" > "$ART/$(basename "$f").gz"; done'\'' sh {} + 2>/dev/null; exit "$rc"' EXIT
say "=== $JASS_JOB_ID code=$(git rev-parse HEAD) eta=${APPROVED_ETA_MIN}min ==="

python3 -m py_compile pattern_jass/tools/rank_finetune.py jobs/tools/gen2_p3_decision_verdict.py
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$BUILD_JOBS" --target jass > "$W/build.log" 2>&1
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"

say "=== leaf-mode hard pairs ==="
for split in train holdout; do
  parents="$HARD_PAIR_DIR/$split/parents.jnnw"
  good="$HARD_PAIR_DIR/$split/good_moves.bin"
  bad="$HARD_PAIR_DIR/$split/bad_moves.bin"
  [[ -f "$parents" && -f "$good" && -f "$bad" ]] || { say "ABORT missing $split pair assets"; exit 4; }
  pairs=$(jnnw_count "$parents")
  [[ "$pairs" -gt 0 ]] || { say "ABORT empty $split pairs"; exit 4; }
  "$J" --gen-siblings "$parents" "$W/$split-b3.jnnw" "$LEAF_DEPTH" --nnue "$GEN2_PATTERN" \
    --played-moves "$good" --dominated-moves "$bad" --leaf-mode --keep-all-pairs \
    > "$W/$split-leaf.log" 2>&1
  [[ "$(( $(jnnw_count "$W/$split-b3.jnnw") / 2 ))" -eq "$pairs" ]] || { say "ABORT $split leaf pair loss"; exit 4; }
done
"$J" --dump-eval-features "$W/train-b3.jnnw" "$W/train.feat" > "$W/dump-feat.log" 2>&1

awk -v limit="$NOPEN" '/^[[:space:]]*#/ {next} {sub(/#.*/,""); if (NF) {print; n++; if(n>=limit) exit}}' \
  "$OPENINGS_FILE" > "$W/openings.fen"
[[ "$(wc -l < "$W/openings.fen")" -eq "$NOPEN" ]] || { say "ABORT insufficient openings"; exit 4; }

passed=0
for anchor in $ANCHORS; do
  tag=${anchor/./p}
  candidate="$W/candidate-a${tag}.pjtw"
  say "=== fit anchor=$anchor ==="
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
    python3 pattern_jass/tools/rank_finetune.py --champion "$GEN2_PATTERN" \
      --pairs "$W/train-b3.jnnw" --feat "$W/train.feat" --out "$candidate" \
      --tools pattern_jass/tools --lam "$RANK_LAM" --anchor "$anchor" \
      --min-pairs "$MIN_PAIRS" --color-fold --tempo-stage --max-iter "$MAX_ITER" \
      --chunk "$CHUNK" --leaf-pov --verify-jass "$J" --verify-n 80 \
      > "$W/fit-a${tag}.log" 2>&1

  python3 jobs/tools/conv_fixed_wdl.py --jass "$J" --pattern "$candidate" \
    --defender-pattern "$DEFENDER_PATTERN" --search-params "$SEARCH_PARAMS" \
    --defender-search-params "$SEARCH_PARAMS" --pool-jnnw "$P3_POOL" \
    --depth "$CONV_DEPTH" --out "$W/conv-a${tag}.json" > "$W/conv-a${tag}.log" 2>&1
  python3 jobs/tools/run_jass_gate_bounded.py --jass "$J" --pattern-a "$candidate" \
    --pattern-b "$GEN2_PATTERN" --openings-file "$W/openings.fen" \
    --search-params-a "$SEARCH_PARAMS" --search-params-b "$SEARCH_PARAMS" \
    --depth "$GATE_DEPTH" --pairs 1 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout "$SHARD_TIMEOUT" --work-dir "$W/depth-a${tag}" --out "$W/depth-a${tag}.json" \
    > "$W/depth-a${tag}.log" 2>&1
  python3 jobs/tools/run_jass_gate_bounded.py --jass "$J" --pattern-a "$candidate" \
    --pattern-b "$GEN2_PATTERN" --openings-file "$W/openings.fen" \
    --search-params-a "$SEARCH_PARAMS" --search-params-b "$SEARCH_PARAMS" \
    --movetime "$MOVETIME" --pairs 1 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout "$SHARD_TIMEOUT" --work-dir "$W/mt-a${tag}" --out "$W/mt-a${tag}.json" \
    > "$W/mt-a${tag}.log" 2>&1
  if python3 jobs/tools/gen2_p3_decision_verdict.py candidate \
      --input "$W/conv-a${tag}.json" --baseline "$BASELINE_P3_JSON" \
      --depth-gate "$W/depth-a${tag}.json" --movetime-gate "$W/mt-a${tag}.json" \
      --out "$ART/verdict-a${tag}.json" | tee -a "$W/RESULTS.txt"; then
    passed=$((passed+1))
  fi
  cp "$W/conv-a${tag}.json" "$W/depth-a${tag}.json" "$W/mt-a${tag}.json" "$ART/"
done
say "passing_candidates=$passed"
[[ "$passed" -gt 0 ]] || exit 3
say "=== end $JASS_JOB_ID; candidates require a separate fresh confirmation ==="
