#!/usr/bin/env bash
# template: L3-PURE C0/P1 direct reinforcement v1
# description: larger direct comparison under identical Q00 search; no training or automatic continuation
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${C0_PREFIX:?}"; : "${P1_PREFIX:?}"
: "${EXPECTED_C0_JOB:?}"; : "${EXPECTED_P1_JOB:?}"

NOPEN="${NOPEN:-768}"
NSH_GATE="${NSH_GATE:-16}"
PAR_GATE="${PAR_GATE:-12}"
DEPTH="${DEPTH:-9}"
MOVETIME="${MOVETIME:-0.3}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-10800}"
# Per-game wall-clock cap (s) → draw. Bounds the movetime-endgame overshoot so a
# shard's games (<= NOPEN*2/nshards) finish well within SHARD_TIMEOUT instead of
# accumulating to tens of hours (the 0894 15h hang).
GAME_TIMEOUT="${GAME_TIMEOUT:-100}"
CACHE_MB="${CACHE_MB:-128}"
JASS_BUILD_JOBS="${JASS_BUILD_JOBS:-8}"
FULL_RUN_APPROVED="${FULL_RUN_APPROVED:-0}"
SCIENTIFIC_GO="${SCIENTIFIC_GO:-0}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; INPUTS="$JASS_RESULT_DIR/inputs"
C0="$JASS_RESULT_DIR/c0"; P1="$JASS_RESULT_DIR/p1"
mkdir -p "$W" "$ART" "$INPUTS" "$C0" "$P1"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/STAGE.txt"
: > "$RES"; echo preflight > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
set_stage(){ echo "$1" > "$STAGE"; say "stage=$1 time_fr=$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"; }
MONITOR_PID=""
monitor(){ ( while true; do { TZ=Europe/Paris date '+time_fr=%Y-%m-%dT%H:%M:%S%z'; printf 'stage=%s\n' "$(cat "$STAGE" 2>/dev/null||echo ?)"; df -Pm "$JASS_RESULT_DIR"|awk 'NR==2{printf "free_mb=%s\n",$4}'; printf 'gate_results=%s\n' "$(find "$W" -type f -name 'gate.*.log' -exec grep -h '^RESULT ' {} + 2>/dev/null|wc -l)"; } > "$PROG.tmp"; mv "$PROG.tmp" "$PROG"; sleep 300; done ) & MONITOR_PID="$!"; }
finalize(){ rc=$?; trap - EXIT TERM INT; set +e; [ -n "$MONITOR_PID" ] && { kill "$MONITOR_PID" 2>/dev/null; wait "$MONITOR_PID" 2>/dev/null; }; [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"; [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"; [ -d "$W" ] && (cd "$W" && find . -type f -name '*.log' -print0|tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null||true; rm -rf "$W/build8" "$W"/gate-* "$INPUTS" "$C0" "$P1" 2>/dev/null||true; exit "$rc"; }
trap finalize EXIT TERM INT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR

say "=== $JASS_JOB_ID — L3-PURE strengthened direct C0/P1 confrontation ==="
[ "$FULL_RUN_APPROVED" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ "$SCIENTIFIC_GO" = 1 ] || die "SCIENTIFIC_GO=1 missing"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "$NOPEN" -eq 768 ] || die "reinforcement requires NOPEN=768"
[ "$NSH_GATE" -eq 16 ] && [ "$PAR_GATE" -eq 12 ] || die "reinforcement requires 16 shards / 12 parallel"
[ "$DEPTH" -eq 9 ] && [ "$MOVETIME" = 0.3 ] || die "budget contract mismatch"
[ "$(nproc)" -ge 16 ] || die "requires cpx62 >=16 CPUs"
[ "$(df -Pm "$JASS_RESULT_DIR"|awk 'NR==2{print $4}')" -ge 8000 ] || die "<8 GiB free"
monitor
python3 -m py_compile jobs/tools/fetch_result_files.py jobs/tools/l3_pure_m0_sources.py jobs/tools/run_jass_gate_bounded.py jobs/tools/l3_pure_c0_p1_reinforcement.py jobs/tools/validate_opening_pool.py
python3 jobs/tests/test_run_jass_gate.py > "$W/test-gate.log" 2>&1 || die "gate tests red"
python3 jobs/tests/test_l3_pure_c0_p1_reinforcement.py > "$W/test-reinforcement.log" 2>&1 || die "reinforcement tests red"
python3 jobs/tests/test_validate_opening_pool.py > "$W/test-openings.log" 2>&1 || die "opening-pool tests red"

set_stage fetch-verified-sources
python3 jobs/tools/fetch_result_files.py --prefix "$C0_PREFIX" \
  --file artefacts/g3.pjtw.gz=g3.pjtw.gz --file artefacts/l3-pure-manifest.json=manifest.json \
  --out-dir "$C0" --report "$ART/verified-c0-source.json" > "$W/fetch-c0.log" 2>&1 || die "C0 source unavailable"
python3 jobs/tools/fetch_result_files.py --prefix "$P1_PREFIX" \
  --file artefacts/g4.pjtw.gz=g4.pjtw.gz --file artefacts/l3-pure-p1-manifest.json=manifest.json \
  --out-dir "$P1" --report "$ART/verified-p1-source.json" > "$W/fetch-p1.log" 2>&1 || die "P1 source unavailable"
if ! python3 jobs/tools/l3_pure_m0_sources.py \
  --c0-dir "$C0" --p1-dir "$P1" --verified-c0 "$ART/verified-c0-source.json" --verified-p1 "$ART/verified-p1-source.json" \
  --expected-c0-job "$EXPECTED_C0_JOB" --expected-p1-job "$EXPECTED_P1_JOB" --out "$ART/reinforcement-source-contract.json" > "$W/source-contract.log" 2>&1; then
  cat "$W/source-contract.log" | tee -a "$RES"; die "source contract validation failed"
fi
cat "$W/source-contract.log" | tee -a "$RES"
gunzip -c "$C0/g3.pjtw.gz" > "$W/c0-a-g3.pjtw"
gunzip -c "$P1/g4.pjtw.gz" > "$W/p1-0842-g4.pjtw"
Q00_SEARCH="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["p1_q00_search_params"])' "$ART/reinforcement-source-contract.json")"
[ "$(awk -F, '{print NF}' <<< "$Q00_SEARCH")" -eq 63 ] || die "Q00 is not fully pinned"

set_stage build-8cf
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl > "$W/clone.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || die "EGDB unavailable"; export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
cmake --build "$W/build8" -j"$JASS_BUILD_JOBS" --target jass > "$W/build8.log" 2>&1
J8="$W/build8/jass"; [ -x "$J8" ] || die "missing jass binary"

# M0 consumed the complete 305-position DILF corpus. Build a deterministic,
# synthetic and public pool from fresh random legal trajectories instead of
# pretending that DILF contains another 768 positions (0888ter abort proof).
OPENING_SEED=271828
"$J8" --gen-opening-pool "$NOPEN" "$W/open-independent.fen" 8 32 20 "$OPENING_SEED" \
  > "$W/opening-generation.log" 2>&1
python3 jobs/tools/validate_opening_pool.py --pool "$W/open-independent.fen" \
  --expected "$NOPEN" --exclude data/dilf_combinations.fen --generator-seed "$OPENING_SEED" \
  --out "$ART/reinforcement-openings-manifest.json" > "$W/opening-validation.log" 2>&1 \
  || die "independent opening-pool validation failed"
sha256sum "$W/open-independent.fen" > "$ART/reinforcement-openings.sha256"

run_gate(){ local label="$1"; shift; timeout 21600 python3 jobs/tools/run_jass_gate_bounded.py \
  --jass "$J8" --pattern-a "$W/p1-0842-g4.pjtw" --pattern-b "$W/c0-a-g3.pjtw" \
  --search-params-a "$Q00_SEARCH" --search-params-b "$Q00_SEARCH" --openings-file "$W/open-independent.fen" \
  --pairs 1 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" --timeout "$SHARD_TIMEOUT" \
  --game-timeout "$GAME_TIMEOUT" \
  --work-dir "$W/gate-$label" --out "$ART/$label.json" "$@" > "$W/$label.log" 2>&1 || { cat "$W/$label.log" | tee -a "$RES"; die "$label failed"; }; }

set_stage q00-depth9-direct
run_gate q00-depth9-p1-vs-c0 --depth "$DEPTH"
set_stage q00-movetime-direct
run_gate q00-movetime-p1-vs-c0 --movetime "$MOVETIME"

set_stage aggregate-verdict
if ! python3 jobs/tools/l3_pure_c0_p1_reinforcement.py \
  --q00-depth "$ART/q00-depth9-p1-vs-c0.json" --q00-movetime "$ART/q00-movetime-p1-vs-c0.json" \
  --out "$ART/c0-p1-reinforcement-verdict.json" --summary-out "$ART/JASS_CONTROL_SUMMARY.json" > "$W/aggregate.log" 2>&1; then
  cat "$W/aggregate.log" | tee -a "$RES"; die "reinforcement aggregation failed"
fi
cat "$W/aggregate.log" | tee -a "$RES"
python3 - "$ART/c0-p1-reinforcement-verdict.json" "$ART" "$RES" <<'PY'
import json,sys
from pathlib import Path
p=json.load(open(sys.argv[1])); art=Path(sys.argv[2]); res=Path(sys.argv[3]); c=p['combined']
def safe(v): return ('P' if v>=0 else 'M')+f'{abs(v):.1f}'.replace('.','_')
markers=[f"VERDICT__{p['decision']}",f"RECOMMENDED_PARENT__{p['recommended_parent']}",f"P1_COMBINED_ELO_VS_C0__{safe(c['p1_elo_vs_c0'])}",'M1_AUTHORIZED__FALSE','PROMOTION_AUTHORIZED__FALSE']
for name in markers: (art/name).write_text(name+'\n')
with res.open('a') as f:
 f.write(f"decision={p['decision']} recommended_parent={p['recommended_parent']}\n")
 f.write(f"combined_p1_score={c['p1_score_rate']:.6f} ci95=[{c['ci_low']:.6f},{c['ci_high']:.6f}] elo={c['p1_elo_vs_c0']:.2f} n={c['n']}\n")
 f.write('m1_authorized=false promotion_authorized=false automatic_next_job=null\n')
PY
set_stage completed
say "=== direct reinforcement complete; human review required ==="
