#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Evaluation-only recovery of the 0922 G1 2x2 screen.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"
: "${JASS_RESULT_DIR:?}"
: "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"
: "${EXPECTED_JOB_ID:?}"
: "${EXPECTED_CODE_SHA:?}"
: "${SCAN_BIN:?}"
: "${EXPECTED_SCAN_SHA256:?}"
: "${EXPECTED_SCAN_RUNTIME_SHA256:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
INPUTS="$W/inputs"
MATRIX="$W/matrix"
BALANCED="$W/balanced"
mkdir -p "$W" "$ART" "$INPUTS" "$MATRIX" "$BALANCED"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }

BASE_SEED=271828
MATRIX_SHARD_TIMEOUT=900
BALANCED_SHARD_TIMEOUT=900
JASS_BUILD_JOBS=4
BOOTSTRAP=10000
BALANCED_OPENINGS=64
BALANCED_GAMES=128
TOTAL_MATRIX_GAMES=$((384 * (1 + 4 * 3)))
SOURCE_PREFIX="r2:jass-data/runs/cpx62-0922bis-l3-conversion-2x2-g1-screen-v1/20260723T152652Z-03f7e50a"
SOURCE_JOB_ID="cpx62-0922bis-l3-conversion-2x2-g1-screen-v1"
SOURCE_ATTEMPT_ID="20260723T152652Z-03f7e50a"
SOURCE_CODE_SHA="03f7e50a08ba1a0abc41fff0f6cbcbeb98f09b6c"
POOL_SHA256="dfdbc788b715c7faab1c2e1dc1a1a7a7f7016eb1c4920b3544deacf973b569d0"
PROOF_SHA256="70daef6cd5a4c9c57d48c0afaaa4622092a25141b70fc8ce3a838e073b2a9e02"
G0_SHA256="4dd50bd836375d825234fa263a964a2b684e865c6513cd7813d5ff93dbe97864"
SEARCH_SHA256="61cdaf50cc1948537990331d78f5b296dc6aee71cc7c2b98bcbd0969977619e1"
CAP_CANDIDATE="standard_off"
CAP_ARM="g0_g4"
CAP_POSITION_ID="9bc75f637c4afd1d9ccb4ed29ea854d784ef32dbb6f5d58f67eb917c40c9b69f"
CAP_CELL="16v18|adv=B|stm=W"
CAP_SHARD=10
CANDIDATES=(standard_off standard_on top3_off top3_on)
MATRIX_ARMS=(g4_g0 g0_g4 g4_g4)

L3_SEARCH_PARAMS="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
PHASE="$W/phase.txt"
: > "$RES"
: > "$PROG"
printf '%s\n' initializing > "$PHASE"

say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
set_phase(){ printf '%s\n' "$1" > "$PHASE.tmp"; mv "$PHASE.tmp" "$PHASE"; }

MONITOR_PID=""
ACTIVE_PIDS=()
SOURCE_BACKUPS=()
SOURCE_PATHS=()

restore_src(){
  local index
  for index in "${!SOURCE_PATHS[@]}"; do
    [ -f "${SOURCE_BACKUPS[$index]}" ] || continue
    cp "${SOURCE_BACKUPS[$index]}" "${SOURCE_PATHS[$index]}"
  done
}
stop_monitor(){
  [ -n "$MONITOR_PID" ] || return 0
  kill "$MONITOR_PID" 2>/dev/null || true
  wait "$MONITOR_PID" 2>/dev/null || true
  MONITOR_PID=""
}
start_monitor(){
  local started="$1"
  (
    while true; do
      python3 - "$W" "$started" "$PROG.tmp" "$PHASE" "$TOTAL_MATRIX_GAMES" <<'PY'
import datetime as dt, glob, json, os, sys, time
root, started, out, phase_path, total = sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4], int(sys.argv[5])
try:
    phase = open(phase_path, encoding="utf-8").read().strip()
except OSError:
    phase = "unknown"
completed = 0
for path in glob.glob(os.path.join(root, "matrix", "**", "*.progress.json"), recursive=True):
    try:
        completed += int(json.load(open(path, encoding="utf-8")).get("completed", 0))
    except (OSError, ValueError):
        pass
now = dt.datetime.now(dt.timezone(dt.timedelta(hours=2)))
with open(out, "w", encoding="utf-8") as handle:
    handle.write(f"time_fr={now.isoformat()}\nphase={phase}\n")
    handle.write(f"elapsed_s={max(time.time()-started, 0):.0f}\n")
    handle.write(f"matrix_games={completed}/{total}\n")
PY
      mv "$PROG.tmp" "$PROG"
      cp "$PROG" "$ART/.PROGRESS.txt.tmp"
      mv "$ART/.PROGRESS.txt.tmp" "$ART/PROGRESS.txt"
      sleep 60
    done
  ) &
  MONITOR_PID="$!"
}
run_pids(){
  local label="$1"; shift
  local failed=0 pid
  ACTIVE_PIDS=("$@")
  for pid in "$@"; do wait "$pid" || failed=$((failed + 1)); done
  ACTIVE_PIDS=()
  [ "$failed" -eq 0 ] || die "$label: $failed failed/timed-out process(es)"
}
finalize(){
  rc=$?
  trap - EXIT ERR INT TERM
  set +e
  stop_monitor
  if [ "${#ACTIVE_PIDS[@]}" -gt 0 ]; then
    kill "${ACTIVE_PIDS[@]}" 2>/dev/null || true
    for pid in "${ACTIVE_PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done
  fi
  restore_src
  [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  [ -d "$MATRIX" ] && tar -C "$W" -czf "$ART/conversion-2x2-matrix-raw.tar.gz" matrix 2>/dev/null || true
  [ -d "$BALANCED" ] && tar -C "$W" -czf "$ART/conversion-2x2-balanced-raw.tar.gz" balanced 2>/dev/null || true
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$INPUTS" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 130' INT
trap 'exit 143' TERM

say "=== $JASS_JOB_ID — 0922ter evaluation-only recovery ==="
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ -z "$(git branch --show-current)" ] || die "code worktree must be detached"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ "${SCIENTIFIC_GO:-0}" = 1 ] || die "SCIENTIFIC_GO=1 missing"
[ "${CONVERSION_2X2_EVAL_GO:-0}" = 1 ] || die "CONVERSION_2X2_EVAL_GO=1 missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "NO_AUTOMATIC_CONTINUATION=1 missing"
[ "$MATRIX_SHARD_TIMEOUT" -eq 900 ] && [ "$BALANCED_SHARD_TIMEOUT" -eq 900 ] || die "evaluation timeout drift"
[ "$BOOTSTRAP" -eq 10000 ] && [ "$BALANCED_GAMES" -eq 128 ] || die "reporting contract drift"

JOB_STARTED_EPOCH="$(date +%s)"
start_monitor "$JOB_STARTED_EPOCH"
set_phase preflight

find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
NPROC="$(nproc)"
[ "$NPROC" -eq 16 ] || die "CPX62 nproc drift: expected 16, got $NPROC"
MEM_MB="$(awk '/MemTotal:/ {printf "%d", $2/1024}' /proc/meminfo)"
[ "${MEM_MB:-0}" -ge 30000 ] || die "requires CPX62 >=30 GiB"
FREE_MB="$(df -Pm /root | awk 'NR==2 {print $4}')"
[ "${FREE_MB:-0}" -gt 10000 ] || die "free disk below 10 GiB"
[ -x "$SCAN_BIN" ] || die "Scan binary missing"
[ "$(sha256sum "$SCAN_BIN" | awk '{print $1}')" = "$EXPECTED_SCAN_SHA256" ] || die "Scan SHA mismatch"
[ "$(printf '%s' "$L3_SEARCH_PARAMS" | sha256sum | awk '{print $1}')" = "$SEARCH_SHA256" ] || die "search fingerprint mismatch"
say "sizing: nproc=16 evaluation=4992_matrix+512_balanced; measured_0921=2688_games/363s; ETA=12-18min; hard_cap=30min"
say "preflight: mem_mb=$MEM_MB free_mb=$FREE_MB shard_timeouts=${MATRIX_SHARD_TIMEOUT}s/${BALANCED_SHARD_TIMEOUT}s"

set_phase smoke_tests
bash -n "$0"
python3 -m py_compile jobs/tools/l3_conversion_2x2_report.py jobs/tools/stable_conversion_matrix.py jobs/tools/fetch_result_files.py jobs/tools/jass_vs_jass_arch.py
python3 -m unittest jobs.tests.test_l3_conversion_2x2_report jobs.tests.test_l3_conversion_2x2_job jobs.tests.test_stable_conversion_matrix -v > "$W/smoke.log" 2>&1 \
  || die "reporting/matrix round-trip tests failed"
say "smoke: syntax + compile + reporting round-trip OK"

set_phase fetch_and_verify_0922bis_models
python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_PREFIX" --expected-state failed \
  --file artefacts/2x2-training-manifest.json=training-manifest.json \
  --file artefacts/g0-material.pjtw.gz=g0-material.pjtw.gz \
  --file artefacts/standard_off.pjtw.gz=standard_off.pjtw.gz \
  --file artefacts/standard_on.pjtw.gz=standard_on.pjtw.gz \
  --file artefacts/top3_off.pjtw.gz=top3_off.pjtw.gz \
  --file artefacts/top3_on.pjtw.gz=top3_on.pjtw.gz \
  --file artefacts/stable-top3.fen=stable-top3.fen \
  --file artefacts/stable-top3.proof.jsonl=stable-top3.proof.jsonl \
  --file artefacts/pool-contract.json=pool-contract.json \
  --out-dir "$INPUTS" --report "$ART/verified-0922bis-source.json" > "$W/fetch-source.log" 2>&1
gzip -dc "$INPUTS/g0-material.pjtw.gz" > "$W/g0-material.pjtw"
for candidate in "${CANDIDATES[@]}"; do
  gzip -dc "$INPUTS/$candidate.pjtw.gz" > "$W/$candidate.pjtw"
done
python3 - "$ART/verified-0922bis-source.json" "$INPUTS/training-manifest.json" "$W" \
  "$SOURCE_PREFIX" "$SOURCE_JOB_ID" "$SOURCE_ATTEMPT_ID" "$SOURCE_CODE_SHA" \
  "$POOL_SHA256" "$PROOF_SHA256" "$G0_SHA256" "$ART/source-model-verification.json" <<'PY'
import hashlib, json, sys
from pathlib import Path
fetch_name, training_name, work_name, prefix, job, attempt, code, pool_sha, proof_sha, g0_sha, out_name = sys.argv[1:]
fetch=json.load(open(fetch_name,encoding="utf-8"))
training=json.load(open(training_name,encoding="utf-8"))
work=Path(work_name)
assert fetch["state"]=="verified" and fetch["result_state"]=="failed"
assert fetch["prefix"]==prefix and fetch["job_id"]==job and fetch["attempt_id"]==attempt
assert fetch["code_sha"]==code and training["code_sha"]==code
assert training["experiment"]=="L3-CONVERSION-2X2-G1"
observed={}
for candidate, expected in training["models"].items():
    raw=(work/f"{candidate}.pjtw").read_bytes()
    observed[candidate]={"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)}
    assert observed[candidate]==expected, candidate
assert hashlib.sha256((work/"g0-material.pjtw").read_bytes()).hexdigest()==g0_sha
assert hashlib.sha256((work/"inputs/stable-top3.fen").read_bytes()).hexdigest()==pool_sha
assert hashlib.sha256((work/"inputs/stable-top3.proof.jsonl").read_bytes()).hexdigest()==proof_sha
json.dump({"schema":1,"state":"verified","source_prefix":prefix,"source_job_id":job,
           "source_attempt_id":attempt,"source_code_sha":code,"models":observed,
           "g0_sha256":g0_sha,"pool_sha256":pool_sha,"proof_sha256":proof_sha},
          open(out_name,"w",encoding="utf-8"),indent=2,sort_keys=True)
open(out_name,"a",encoding="utf-8").write("\n")
PY
cp "$INPUTS/training-manifest.json" "$ART/2x2-training-manifest.json"
cp "$INPUTS/stable-top3.fen" "$ART/stable-top3.fen"
cp "$INPUTS/stable-top3.proof.jsonl" "$ART/stable-top3.proof.jsonl"
cp "$INPUTS/pool-contract.json" "$ART/pool-contract.json"

set_phase architecture_build
for source in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/movegen.cpp src/movegen.hpp; do
  backup="$W/original-$(basename "$source")"
  cp "$source" "$backup"
  SOURCE_PATHS+=("$source")
  SOURCE_BACKUPS+=("$backup")
  git show "$EXPECTED_CODE_SHA:$source" > "$source"
done
grep -q "g_emasks" src/scan_eval.cpp || die "architecture guard: scan_eval lacks g_emasks"
grep -q "has_any_capture" src/search.cpp || die "architecture guard: search lacks has_any_capture"
grep -q "has_any_capture" src/movegen.cpp || die "architecture guard: movegen lacks has_any_capture"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen-patterns.log" 2>&1
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
cmake -S . -B "$W/build" $FLAGS > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$JASS_BUILD_JOBS" --target jass > "$W/build.log" 2>&1
J="$W/build/jass"
[ -x "$J" ] || die "jass binary missing"

run_matrix_arm(){
  local candidate="$1" arm="$2" pattern="$3"
  local dir="$MATRIX/$candidate/$arm" shard failed=0 pid pids=()
  mkdir -p "$dir"
  for shard in $(seq 0 15); do
    timeout "$MATRIX_SHARD_TIMEOUT" python3 jobs/tools/stable_conversion_matrix.py run \
      --pool "$INPUTS/stable-top3.fen" --proof "$INPUTS/stable-top3.proof.jsonl" \
      --arm "$arm" --shard-index "$shard" --nshards 16 --depth 10 \
      --max-plies 400 --game-timeout 120 --jass "$J" --scan "$SCAN_BIN" \
      --scan-runtime-sha256 "$EXPECTED_SCAN_RUNTIME_SHA256" \
      --g0 "$W/g0-material.pjtw" --g4 "$pattern" \
      --search-params "$L3_SEARCH_PARAMS" --output "$dir/s${shard}.jsonl" \
      --progress-file "$dir/s${shard}.progress.json" > "$dir/s${shard}.log" 2>&1 &
    pids+=("$!")
  done
  ACTIVE_PIDS=("${pids[@]}")
  for pid in "${pids[@]}"; do wait "$pid" || failed=$((failed + 1)); done
  ACTIVE_PIDS=()
  if [ "$candidate/$arm" != "$CAP_CANDIDATE/$CAP_ARM" ]; then
    [ "$failed" -eq 0 ] || die "matrix $candidate/$arm: $failed failed/timed-out process(es)"
    return
  fi
  [ "$failed" -eq 1 ] || die "pinned-cap arm expected exactly one technical shard, got $failed"
  python3 - "$dir" "$CAP_POSITION_ID" "$CAP_CELL" "$CAP_SHARD" <<'PY'
import json, sys
from pathlib import Path
root, position_id, cell, expected_shard = Path(sys.argv[1]), sys.argv[2], sys.argv[3], int(sys.argv[4])
progress=[json.load(open(root/f"s{i}.progress.json",encoding="utf-8")) for i in range(16)]
assert all(item["completed"]==24 and item["expected"]==24 for item in progress), progress
bad=[item for item in progress if item["errors_or_caps"]]
assert len(bad)==1 and bad[0]["shard"]==expected_shard and bad[0]["errors_or_caps"]==1, bad
rows=[]
for path in sorted(root.glob("s*.jsonl")):
    rows += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
caps=[row for row in rows if row.get("error") or row.get("reason") in {"ply cap","game time cap"}]
assert len(rows)==384 and len(caps)==1, (len(rows),caps)
cap=caps[0]
assert cap["position_id"]==position_id and cap["cell"]==cell and cap["reason"]=="ply cap"
assert cap["plies"]==400 and cap["outcome_plus2"]=="D" and cap["error"] is None, cap
PY
}

set_phase stable_TOP3_matrix_4992_games
run_matrix_arm common g0_g0 "$W/g0-material.pjtw"
for candidate in "${CANDIDATES[@]}"; do
  for arm in "${MATRIX_ARMS[@]}"; do
    run_matrix_arm "$candidate" "$arm" "$W/$candidate.pjtw"
  done
done

set_phase balanced_guard_512_games
python3 - data/dilf_combinations.fen "$W/balanced-64.fen" "$BALANCED_OPENINGS" "$BASE_SEED" <<'PY'
import random, sys
rows=[]
for raw in open(sys.argv[1],encoding="utf-8"):
    line=raw.split("#",1)[0].strip()
    if line and line[0] in "WB" and ":W" in line and ":B" in line:
        rows.append(line)
want=int(sys.argv[3])
if len(rows)<want: raise SystemExit(f"need {want} balanced openings, got {len(rows)}")
open(sys.argv[2],"w",encoding="utf-8").write("\n".join(random.Random(int(sys.argv[4])).sample(rows,want))+"\n")
PY
for candidate in "${CANDIDATES[@]}"; do
  dir="$BALANCED/$candidate"
  mkdir -p "$dir"
  pids=()
  for shard in $(seq 0 7); do
    timeout "$BALANCED_SHARD_TIMEOUT" python3 jobs/tools/jass_vs_jass_arch.py \
      --jass-a "$J" --pattern-a "$W/$candidate.pjtw" \
      --jass-b "$J" --pattern-b "$W/g0-material.pjtw" \
      --depth 8 --pairs 1 --max-plies 400 --game-timeout 120 \
      --shard "$shard" --nshards 8 --quiet \
      --search-params-a "$L3_SEARCH_PARAMS" --search-params-b "$L3_SEARCH_PARAMS" \
      --openings-file "$W/balanced-64.fen" > "$dir/s${shard}.log" 2>&1 &
    pids+=("$!")
  done
  run_pids "balanced guard $candidate" "${pids[@]}"
done

set_phase aggregate_and_decide
python3 jobs/tools/l3_conversion_2x2_report.py \
  --pool "$INPUTS/stable-top3.fen" --proof "$INPUTS/stable-top3.proof.jsonl" \
  --matrix-root "$MATRIX" --balanced-root "$BALANCED" \
  --balanced-games "$BALANCED_GAMES" --balanced-floor 0.40 \
  --bootstrap "$BOOTSTRAP" --seed "$BASE_SEED" \
  --salvage-candidate "$CAP_CANDIDATE" --salvage-arm "$CAP_ARM" \
  --salvage-position-id "$CAP_POSITION_ID" --salvage-cell "$CAP_CELL" --salvage-plies 400 \
  --output "$ART/conversion-2x2-g1-report.json" > "$W/report.log" 2>&1

python3 - "$ART/conversion-2x2-g1-report.json" "$INPUTS/training-manifest.json" \
  "$W/g0-material.pjtw" "$ART/VERDICT__CONVERSION_2X2_G1_SCREEN_READY" "$RES" \
  "$CAP_POSITION_ID" <<'PY'
import hashlib, json, sys
report=json.load(open(sys.argv[1],encoding="utf-8"))
training=json.load(open(sys.argv[2],encoding="utf-8"))
assert report["decision"]=="CONVERSION_2X2_G1_SCREEN_READY"
assert report["technical_status"]=="derived_complete_single_ply_cap"
assert report["original_zero_cap_gate_ready"] is False
assert report["contract"]["positions"]==384 and report["contract"]["balanced_games_per_candidate"]==128
assert len(report["adjudications"])==1
assert report["adjudications"][0]["position_id"]==sys.argv[6]
assert report["adjudications"][0]["changes_to_raw_games"]==1
assert report["provenance"]["engine"]["g0"]==hashlib.sha256(open(sys.argv[3],"rb").read()).hexdigest()
for candidate, model in training["models"].items():
    assert report["provenance"]["candidate_g4"][candidate]==model["sha256"], candidate
open(sys.argv[4],"w",encoding="utf-8").write(report["decision"]+"\n")
with open(sys.argv[5],"a",encoding="utf-8") as out:
    out.write("decision="+report["decision"]+"\n")
    out.write("technical_status="+report["technical_status"]+"\n")
    out.write("balanced_guard="+str(report["balanced_guard"]["pass"]).lower()+"\n")
    out.write("factor_signals="+str(len(report["factor_signals_abs_ge_0_05_ci_excludes_zero"]))+"\n")
    for endpoint, factors in report["factor_effects"].items():
        out.write(endpoint+"="+json.dumps(factors,sort_keys=True)+"\n")
PY
printf '%s\n' "promotion_authorized=false" > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf '%s\n' "training_continuation_authorized=false" > "$ART/TRAINING_CONTINUATION_AUTHORIZED__FALSE"
printf '%s\n' "automatic_next_job=null" > "$ART/AUTOMATIC_NEXT_JOB__NULL"
set_phase complete
say "CONVERSION_2X2_G1_SCREEN_READY derived_single_cap=true promotion=false continuation=false automatic_next_job=null"
