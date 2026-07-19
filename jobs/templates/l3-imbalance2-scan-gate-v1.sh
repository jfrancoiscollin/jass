#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Plateau-only final benchmark: Gen2-MMTO lower reference, Scan upper reference.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${SCAN_BIN:?}"
: "${CANDIDATE_MODEL_URI:?}"; : "${CANDIDATE_MODEL_SHA256:?}"
: "${PLATEAU_REPORT_URI:?}"; : "${PLATEAU_REPORT_SHA256:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; INPUTS="$JASS_RESULT_DIR/inputs"
mkdir -p "$W" "$ART" "$INPUTS"
exec 9>"$JASS_RESULT_DIR/job.lock"; flock -n 9 || { echo "ABORT: active instance" >&2; exit 3; }
DEPTH="${DEPTH:-10}"; NSHARDS="${NSHARDS:-8}"; PAR="${PAR:-8}"; MAXPLIES="${MAXPLIES:-400}"
BENCH_PER_STRATUM="${BENCH_PER_STRATUM:-24}"; BASE_SEED="${BASE_SEED:-271828}"
GLOBAL_POINT_MARGIN="${GLOBAL_POINT_MARGIN:-0.03}"; GLOBAL_CI_MARGIN="${GLOBAL_CI_MARGIN:-0.05}"
STRATUM_POINT_MARGIN="${STRATUM_POINT_MARGIN:-0.10}"; MIN_PER_STRATUM="${MIN_PER_STRATUM:-20}"
GEN2_COST_MARGIN="${GEN2_COST_MARGIN:-0.02}"; GEN2_CI_MARGIN="${GEN2_CI_MARGIN:-0.05}"
SEARCH_PARAMS="${SEARCH_PARAMS:?fully resolved Q00 fingerprint required}"
EGDB_CACHE_MB="${JASS_EGDB_CACHE_MB:-128}"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$*" | tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }
fetch_input(){ local src="$1" dst="$2"; if [ -f "$src" ]; then cp "$src" "$dst"; elif [[ "$src" == r2:* ]]; then rclone copyto "$src" "$dst"; else die "missing input $src"; fi; }
finalize(){ rc=$?; trap - EXIT; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; rm -rf "$W/build-candidate" "$W/build-gen2" 2>/dev/null || true; exit "$rc"; }; trap finalize EXIT
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ "${SCIENTIFIC_GO:-0}" = 1 ] || die "SCIENTIFIC_GO=1 missing"
[ "${PLATEAU_APPROVED:-0}" = 1 ] || die "external references forbidden before PLATEAU_APPROVED=1"
[ "$NSHARDS" -eq 8 ] || die "benchmark requires 8 shards"
[ "$DEPTH" -eq 10 ] || die "material benchmark compatibility requires d10"
[ "$MAXPLIES" -eq 400 ] || die "material benchmark compatibility requires maxplies=400"
[ "$(awk -F, '{print NF}' <<<"$SEARCH_PARAMS")" -eq 63 ] || die "63 candidate search keys required"
[ -x "$SCAN_BIN" ] || die "Scan binary missing"

fetch_input "$PLATEAU_REPORT_URI" "$W/plateau-report.json"
echo "$PLATEAU_REPORT_SHA256  $W/plateau-report.json" | sha256sum -c -
python3 - "$W/plateau-report.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
assert p.get('plateau_confirmed') is True
assert len(p.get('generations',[])) >= 4
assert p.get('same_search_budget') is True
assert p.get('external_references_used') in (False, [], None)
PY
cp "$W/plateau-report.json" "$ART/plateau-report.json"

fetch_input "$CANDIDATE_MODEL_URI" "$W/candidate.pjtw.gz"
echo "$CANDIDATE_MODEL_SHA256  $W/candidate.pjtw.gz" | sha256sum -c -
gzip -dc "$W/candidate.pjtw.gz" > "$W/candidate.pjtw"
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$INPUTS" --report "$ART/verified-gen2-input.json" > "$W/fetch-gen2.log" 2>&1 || die "Gen2-MMTO input unavailable"
gzip -dc "$INPUTS/gen2.pjtw.gz" > "$W/gen2.pjtw"

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl > "$W/clone-egdb.log" 2>&1
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }; done
[ -n "$EGDIR" ] || die "exact EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$EGDB_CACHE_MB"
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"

python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen-8cf.log" 2>&1
cmake -S . -B "$W/build-candidate" $FLAGS > "$W/cmake-candidate.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake-candidate.log" || die "candidate build has no exact EGDB"
cmake --build "$W/build-candidate" -j8 --target jass > "$W/build-candidate.log" 2>&1
JCAND="$W/build-candidate/jass"

python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 > "$W/gen-v4.log" 2>&1
cmake -S . -B "$W/build-gen2" $FLAGS > "$W/cmake-gen2.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake-gen2.log" || die "Gen2 build has no exact EGDB"
cmake --build "$W/build-gen2" -j8 --target jass > "$W/build-gen2.log" 2>&1
JGEN2="$W/build-gen2/jass"

python3 jobs/tools/make_imbalance2_pools.py --out-dir "$W/pools" --train-per-side 1 \
  --bench-per-stratum "$BENCH_PER_STRATUM" --plateau-per-stratum 1 --seed "$BASE_SEED" > "$W/pools.log"

run_engine(){
  local pool="$1" engine="$2" jass="$3" pattern="$4" listfile="$5"
  local -a pids=() outputs=(); local shard out
  for shard in $(seq 0 $((NSHARDS-1))); do
    out="$W/${pool}.${engine}.s${shard}.json"; outputs+=("$out")
    cmd=(python3 jobs/tools/imbalance2_scan_gate.py run --engine "$engine" --jass "$jass"
      --pool "$W/pools/benchmark-${pool}.jnnw" --meta "$W/pools/benchmark-${pool}.json"
      --depth "$DEPTH" --max-plies "$MAXPLIES" --shard "$shard" --nshards "$NSHARDS" --out "$out")
    if [ "$engine" = candidate ]; then cmd+=(--pattern "$pattern" --search-params "$SEARCH_PARAMS")
    elif [ "$engine" = gen2 ]; then cmd+=(--pattern "$pattern")
    else cmd+=(--scan "$SCAN_BIN" --scan-bb-size 0)
    fi
    "${cmd[@]}" > "$W/${pool}.${engine}.s${shard}.log" 2>&1 & pids+=("$!")
    if [ "${#pids[@]}" -ge "$PAR" ]; then for p in "${pids[@]}"; do wait "$p" || die "$pool $engine shard failed"; done; pids=(); fi
  done
  for p in "${pids[@]}"; do wait "$p" || die "$pool $engine shard failed"; done
  printf '%s\n' "${outputs[@]}" > "$listfile"
}

for pool in a b; do
  run_engine "$pool" candidate "$JCAND" "$W/candidate.pjtw" "$W/${pool}.candidate.list"
  run_engine "$pool" gen2 "$JGEN2" "$W/gen2.pjtw" "$W/${pool}.gen2.list"
  run_engine "$pool" scan "$JCAND" "" "$W/${pool}.scan.list"
  mapfile -t cand_out < "$W/${pool}.candidate.list"
  mapfile -t gen2_out < "$W/${pool}.gen2.list"
  mapfile -t scan_out < "$W/${pool}.scan.list"
  python3 jobs/tools/imbalance2_scan_gate.py aggregate \
    --candidate-inputs "${cand_out[@]}" --gen2-inputs "${gen2_out[@]}" --scan-inputs "${scan_out[@]}" \
    --out "$ART/pool-${pool}-decision.json" --seed $((BASE_SEED + 1000)) \
    --global-point-margin "$GLOBAL_POINT_MARGIN" --global-ci-margin "$GLOBAL_CI_MARGIN" \
    --stratum-point-margin "$STRATUM_POINT_MARGIN" --min-per-stratum "$MIN_PER_STRATUM" \
    --gen2-cost-margin "$GEN2_COST_MARGIN" --gen2-ci-margin "$GEN2_CI_MARGIN" --max-errors 0 \
    > "$W/${pool}-aggregate.log"
done
python3 - "$ART/pool-a-decision.json" "$ART/pool-b-decision.json" "$ART/stop-decision.json" <<'PY'
import json,sys
from pathlib import Path
a=json.loads(Path(sys.argv[1]).read_text()); b=json.loads(Path(sys.argv[2]).read_text())
stop=bool(a['pass'] and b['pass'])
out={'schema':3,'lineage':'L3-IMBALANCE2','protocol':'plateau_only_candidate_gen2_scan_selfplay',
     'perspective':'material_up_side','pool_a':a['decision'],'pool_b':b['decision'],
     'decision':'STOP_LINEAGE_SCAN_EQUIVALENT' if stop else 'PLATEAU_BELOW_SCAN_REDESIGN',
     'stop_authorized':stop,'scan_training_input':False,'gen2_training_input':False,
     'plateau_required':True,'automatic_next_job':None}
Path(sys.argv[3]).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(out['decision'])
PY
say "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["decision"])' "$ART/stop-decision.json")"
