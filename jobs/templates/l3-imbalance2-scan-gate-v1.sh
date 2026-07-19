#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Two independent fixed-pool W/D/L equivalence checks against Scan.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${SCAN_BIN:?}"
: "${CANDIDATE_MODEL_URI:?}"; : "${CANDIDATE_MODEL_SHA256:?}"
: "${DEFENDER_MODEL_URI:?}"; : "${DEFENDER_MODEL_SHA256:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; mkdir -p "$W" "$ART"
exec 9>"$JASS_RESULT_DIR/job.lock"; flock -n 9 || { echo "ABORT: active instance" >&2; exit 3; }
DEPTH="${DEPTH:-8}"; NSHARDS="${NSHARDS:-8}"; PAR="${PAR:-8}"; MAXPLIES="${MAXPLIES:-260}"
BENCH_PER_STRATUM="${BENCH_PER_STRATUM:-24}"; BASE_SEED="${BASE_SEED:-271828}"
GLOBAL_POINT_MARGIN="${GLOBAL_POINT_MARGIN:-0.03}"; GLOBAL_CI_MARGIN="${GLOBAL_CI_MARGIN:-0.05}"
STRATUM_POINT_MARGIN="${STRATUM_POINT_MARGIN:-0.10}"; MIN_PER_STRATUM="${MIN_PER_STRATUM:-20}"
SEARCH_PARAMS="${SEARCH_PARAMS:?fully resolved Q00 fingerprint required}"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$*" | tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }
fetch_input(){ local src="$1" dst="$2"; if [ -f "$src" ]; then cp "$src" "$dst"; elif [[ "$src" == r2:* ]]; then rclone copyto "$src" "$dst"; else die "missing input $src"; fi; }
finalize(){ rc=$?; trap - EXIT; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; exit "$rc"; }; trap finalize EXIT
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ "${SCIENTIFIC_GO:-0}" = 1 ] || die "SCIENTIFIC_GO=1 missing"
[ "$NSHARDS" -eq 8 ] || die "gate requires 8 shards"
[ "$(awk -F, '{print NF}' <<<"$SEARCH_PARAMS")" -eq 63 ] || die "63 search keys required"
[ -x "$SCAN_BIN" ] || die "Scan binary missing"
fetch_input "$CANDIDATE_MODEL_URI" "$W/candidate.pjtw.gz"; echo "$CANDIDATE_MODEL_SHA256  $W/candidate.pjtw.gz" | sha256sum -c -
fetch_input "$DEFENDER_MODEL_URI" "$W/defender.pjtw.gz"; echo "$DEFENDER_MODEL_SHA256  $W/defender.pjtw.gz" | sha256sum -c -
gzip -dc "$W/candidate.pjtw.gz" > "$W/candidate.pjtw"; gzip -dc "$W/defender.pjtw.gz" > "$W/defender.pjtw"
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
cmake -S . -B "$W/build" $FLAGS > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass > "$W/build.log" 2>&1
J="$W/build/jass"
python3 jobs/tools/make_imbalance2_pools.py --out-dir "$W/pools" --train-per-stratum 1 \
  --bench-per-stratum "$BENCH_PER_STRATUM" --seed "$BASE_SEED" > "$W/pools.log"
for pool in a b; do
  pids=(); outputs=()
  for shard in $(seq 0 $((NSHARDS-1))); do
    out="$W/${pool}.s${shard}.json"; outputs+=("$out")
    python3 jobs/tools/imbalance2_scan_gate.py run --jass "$J" --scan "$SCAN_BIN" \
      --candidate "$W/candidate.pjtw" --defender "$W/defender.pjtw" \
      --pool "$W/pools/benchmark-${pool}.jnnw" --meta "$W/pools/benchmark-${pool}.json" \
      --search-params "$SEARCH_PARAMS" --defender-search-params "$SEARCH_PARAMS" \
      --depth "$DEPTH" --max-plies "$MAXPLIES" --scan-bb-size 0 \
      --shard "$shard" --nshards "$NSHARDS" --out "$out" > "$W/${pool}.s${shard}.log" 2>&1 &
    pids+=("$!")
    if [ "${#pids[@]}" -ge "$PAR" ]; then for p in "${pids[@]}"; do wait "$p" || die "gate shard failed"; done; pids=(); fi
  done
  for p in "${pids[@]}"; do wait "$p" || die "gate shard failed"; done
  python3 jobs/tools/imbalance2_scan_gate.py aggregate --inputs "${outputs[@]}" --out "$ART/pool-${pool}-decision.json" \
    --seed $((BASE_SEED + 1000)) --global-point-margin "$GLOBAL_POINT_MARGIN" \
    --global-ci-margin "$GLOBAL_CI_MARGIN" --stratum-point-margin "$STRATUM_POINT_MARGIN" \
    --min-per-stratum "$MIN_PER_STRATUM" --max-errors 0 > "$W/${pool}-aggregate.log"
done
python3 - "$ART/pool-a-decision.json" "$ART/pool-b-decision.json" "$ART/stop-decision.json" <<'PY'
import json,sys
from pathlib import Path
a=json.loads(Path(sys.argv[1]).read_text()); b=json.loads(Path(sys.argv[2]).read_text())
stop=bool(a['pass'] and b['pass'])
out={'schema':1,'lineage':'L3-IMBALANCE2','pool_a':a['decision'],'pool_b':b['decision'],
     'decision':'STOP_LINEAGE_SCAN_EQUIVALENT' if stop else 'CONTINUE_NEXT_PHASE',
     'stop_authorized':stop,'scan_training_input':False,'automatic_next_job':None}
Path(sys.argv[3]).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(out['decision'])
PY
say "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["decision"])' "$ART/stop-decision.json")"
