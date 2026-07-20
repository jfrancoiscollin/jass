#!/usr/bin/env bash
# template: L3-PURE maturity M0 generalist triangle v1
# description: read-only C0 A-G3 / P1-0842 G4 / gen2-mmto force benchmark
# expected_duration: 60-120 min on cpx62; no training or automatic continuation
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${C0_PREFIX:?}"; : "${P1_PREFIX:?}"
: "${EXPECTED_C0_JOB:?}"; : "${EXPECTED_P1_JOB:?}"

NOPEN="${NOPEN:-300}"
NSH_GATE="${NSH_GATE:-12}"
PAR_GATE="${PAR_GATE:-3}"
DEPTH="${DEPTH:-9}"
NATIVE_MOVETIME="${NATIVE_MOVETIME:-0.3}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-7200}"
CACHE_MB="${CACHE_MB:-128}"
JASS_BUILD_JOBS="${JASS_BUILD_JOBS:-8}"
FULL_RUN_APPROVED="${FULL_RUN_APPROVED:-0}"
SCIENTIFIC_GO="${SCIENTIFIC_GO:-0}"
HISTORICAL_SEARCH="qs_forcing_depth=6,qs_promo_depth=6"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"
INPUTS="$JASS_RESULT_DIR/inputs"; C0="$JASS_RESULT_DIR/c0"; P1="$JASS_RESULT_DIR/p1"
mkdir -p "$W" "$ART" "$INPUTS" "$C0" "$P1"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/STAGE.txt"
: > "$RES"; echo preflight > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
set_stage(){ echo "$1" > "$STAGE"; say "stage=$1 time_fr=$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"; }
run_pids(){ local label="$1"; shift; local fail=0 pid; for pid in "$@"; do wait "$pid" || fail=$((fail+1)); done; [ "$fail" -eq 0 ] || die "$label: $fail failed"; }
MONITOR_PID=""
monitor(){ ( while true; do { TZ=Europe/Paris date '+time_fr=%Y-%m-%dT%H:%M:%S%z'; printf 'stage=%s\n' "$(cat "$STAGE" 2>/dev/null||echo ?)"; df -Pm "$JASS_RESULT_DIR"|awk 'NR==2{printf "free_mb=%s\n",$4}'; printf 'gate_results=%s\n' "$(find "$W" -type f -name 'gate.*.log' -exec grep -h '^RESULT ' {} + 2>/dev/null|wc -l)"; } > "$PROG.tmp"; mv "$PROG.tmp" "$PROG"; sleep 300; done ) & MONITOR_PID="$!"; }
finalize(){ rc=$?; trap - EXIT; set +e; [ -n "$MONITOR_PID" ] && { kill "$MONITOR_PID" 2>/dev/null; wait "$MONITOR_PID" 2>/dev/null; }; [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"; [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"; [ -d "$W" ] && (cd "$W" && find . -type f -name '*.log' -print0|tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null||true; rm -rf "$W/build8" "$W/build32" "$W"/gate-* "$INPUTS" "$C0" "$P1" 2>/dev/null||true; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR

say "=== $JASS_JOB_ID — L3-PURE M0 triangle ==="
[ "$FULL_RUN_APPROVED" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ "$SCIENTIFIC_GO" = 1 ] || die "SCIENTIFIC_GO=1 missing"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "$NOPEN" -eq 300 ] || die "M0 requires NOPEN=300"
[ "$DEPTH" -eq 9 ] || die "M0 fixed-depth view requires d9"
[ "$NATIVE_MOVETIME" = 0.3 ] || die "M0 native view requires 0.3 s/move"
NPROC="$(nproc)"; [ "$NPROC" -ge 16 ] || die "M0 triangle requires cpx62 >=16 CPUs"
FREE_MB="$(df -Pm "$JASS_RESULT_DIR"|awk 'NR==2{print $4}')"; [ "${FREE_MB:-0}" -ge 8000 ] || die "<8 GiB free"
say "preflight: nproc=$NPROC free_mb=$FREE_MB views=3 matches_per_view=3 games_per_match=$((NOPEN*2))"
monitor
python3 -m py_compile jobs/tools/fetch_result_files.py jobs/tools/fetch_t1bis_inputs.py jobs/tools/run_jass_gate_bounded.py jobs/tools/l3_pure_m0_verdict.py
python3 jobs/tests/test_run_jass_gate.py > "$W/test-gate.log" 2>&1 || die "gate tests red"
python3 jobs/tests/test_l3_pure_m0.py > "$W/test-m0.log" 2>&1 || die "M0 tests red"

set_stage fetch-verified-inputs
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$INPUTS" --report "$ART/verified-fixed-inputs.json" > "$W/fetch-inputs.log" 2>&1 || die "fixed inputs unavailable"
python3 jobs/tools/fetch_result_files.py --prefix "$C0_PREFIX" \
  --file artefacts/g3.pjtw.gz=g3.pjtw.gz \
  --file artefacts/l3-pure-manifest.json=manifest.json \
  --out-dir "$C0" --report "$ART/verified-c0-source.json" > "$W/fetch-c0.log" 2>&1 || die "C0 source unavailable"
python3 jobs/tools/fetch_result_files.py --prefix "$P1_PREFIX" \
  --file artefacts/g4.pjtw.gz=g4.pjtw.gz \
  --file artefacts/l3-pure-p1-manifest.json=manifest.json \
  --out-dir "$P1" --report "$ART/verified-p1-source.json" > "$W/fetch-p1.log" 2>&1 || die "P1 source unavailable"
python3 - "$C0" "$P1" "$ART" "$EXPECTED_C0_JOB" "$EXPECTED_P1_JOB" <<'PY'
import hashlib,json,sys
from pathlib import Path
c0,p1,art=map(Path,sys.argv[1:4]); c0job,p1job=sys.argv[4:6]
c0m=json.loads((c0/'manifest.json').read_text()); p1m=json.loads((p1/'manifest.json').read_text())
c0v=json.loads((art/'verified-c0-source.json').read_text()); p1v=json.loads((art/'verified-p1-source.json').read_text())
if c0v.get('job_id')!=c0job or p1v.get('job_id')!=p1job: raise SystemExit('source job mismatch')
if c0m.get('lineage')!='L3-PURE' or c0m.get('arm')!='A' or c0m.get('generations')!=3 or c0m.get('scientific_status')!='complete_generation_chain': raise SystemExit('invalid C0 A manifest')
if p1m.get('experiment')!='L3-PURE-P1' or p1m.get('variant')!='FROZEN_BASELINE' or p1m.get('scientific_status')!='complete_p1_training': raise SystemExit('invalid P1 manifest')
if p1m.get('recipe',{}).get('generations')!=4: raise SystemExit('P1 is not G1-G4')
for root,man,name,key in ((c0,c0m,'g3.pjtw.gz','champion_sha256'),(p1,p1m,'g4.pjtw.gz','student_sha256')):
    got=hashlib.sha256((root/name).read_bytes()).hexdigest()
    if man.get(key,{}).get(name)!=got: raise SystemExit(f'{name} checksum mismatch')
c0_search=c0m.get('search_params','')
p1_search=p1m.get('search_params') or p1m.get('recipe',{}).get('search_params','')
if len(c0_search.split(','))!=5: raise SystemExit('C0 fingerprint is not the reviewed five-key fingerprint')
if len(p1_search.split(','))!=63: raise SystemExit('P1 Q00 fingerprint is not complete')
(art/'m0-source-contract.json').write_text(json.dumps({'schema':1,'c0_job':c0job,'p1_job':p1job,'c0_search_params':c0_search,'p1_q00_search_params':p1_search,'gen2_search_params':'qs_forcing_depth=6,qs_promo_depth=6'},indent=2,sort_keys=True)+'\n')
PY
gunzip -c "$C0/g3.pjtw.gz" > "$W/c0-a-g3.pjtw"
gunzip -c "$P1/g4.pjtw.gz" > "$W/p1-0842-g4.pjtw"
gunzip -c "$INPUTS/gen2.pjtw.gz" > "$W/gen2.pjtw"
for f in c0-a-g3.pjtw p1-0842-g4.pjtw gen2.pjtw; do [ -s "$W/$f" ] || die "missing $f"; done
C0_SEARCH="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["c0_search_params"])' "$ART/m0-source-contract.json")"
Q00_SEARCH="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["p1_q00_search_params"])' "$ART/m0-source-contract.json")"

set_stage build-8cf-and-32cf
for s in src/scan_eval.cpp src/search.cpp src/movegen.cpp; do git show "HEAD:$s" > "$W/exp-$(basename "$s")"; cmp -s "$s" "$W/exp-$(basename "$s")" || die "$s differs from pinned HEAD"; done
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl > "$W/clone.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || die "EGDB unavailable"; export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1; cmake --build "$W/build8" -j"$JASS_BUILD_JOBS" --target jass > "$W/build8.log" 2>&1
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 > "$W/gen32.log" 2>&1
cmake -S . -B "$W/build32" $FLAGS > "$W/cmake32.log" 2>&1; cmake --build "$W/build32" -j"$JASS_BUILD_JOBS" --target jass > "$W/build32.log" 2>&1
J8="$W/build8/jass"; J32="$W/build32/jass"
python3 jobs/tools/cache_guard.py --cache-mb "$CACHE_MB" --procs 12 > "$ART/cache-gates.json" || die "cache guard"
awk -v limit="$NOPEN" '/^[[:space:]]*#/ {next} {sub(/#.*/,""); if(NF){print; n++; if(n>=limit) exit}}' data/dilf_combinations.fen > "$W/open.fen"
[ "$(wc -l < "$W/open.fen")" -eq "$NOPEN" ] || die "not enough fixed openings"

run_view(){ local view="$1" budget="$2" a_search="$3" p_search="$4" g_search="$5"; local -a pids=(); local budget_args=(); if [ "$budget" = depth ]; then budget_args=(--depth "$DEPTH"); else budget_args=(--movetime "$NATIVE_MOVETIME"); fi
  timeout 21600 python3 jobs/tools/run_jass_gate_bounded.py --jass-a "$J8" --jass-b "$J32" --pattern-a "$W/c0-a-g3.pjtw" --pattern-b "$W/gen2.pjtw" --search-params-a "$a_search" --search-params-b "$g_search" --openings-file "$W/open.fen" "${budget_args[@]}" --pairs 1 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" --timeout "$SHARD_TIMEOUT" --work-dir "$W/gate-$view-a-gen2" --out "$ART/$view-c0-a-vs-gen2.json" > "$W/$view-a-gen2.log" 2>&1 & pids+=("$!")
  timeout 21600 python3 jobs/tools/run_jass_gate_bounded.py --jass-a "$J8" --jass-b "$J32" --pattern-a "$W/p1-0842-g4.pjtw" --pattern-b "$W/gen2.pjtw" --search-params-a "$p_search" --search-params-b "$g_search" --openings-file "$W/open.fen" "${budget_args[@]}" --pairs 1 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" --timeout "$SHARD_TIMEOUT" --work-dir "$W/gate-$view-p1-gen2" --out "$ART/$view-p1-g4-vs-gen2.json" > "$W/$view-p1-gen2.log" 2>&1 & pids+=("$!")
  timeout 21600 python3 jobs/tools/run_jass_gate_bounded.py --jass "$J8" --pattern-a "$W/p1-0842-g4.pjtw" --pattern-b "$W/c0-a-g3.pjtw" --search-params-a "$p_search" --search-params-b "$a_search" --openings-file "$W/open.fen" "${budget_args[@]}" --pairs 1 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" --timeout "$SHARD_TIMEOUT" --work-dir "$W/gate-$view-p1-a" --out "$ART/$view-p1-g4-vs-c0-a.json" > "$W/$view-p1-a.log" 2>&1 & pids+=("$!")
  run_pids "$view gates" "${pids[@]}"; }

set_stage historical-0795-depth9
run_view historical depth "$HISTORICAL_SEARCH" "$HISTORICAL_SEARCH" "$HISTORICAL_SEARCH"
set_stage common-q00-depth9
run_view q00 depth "$Q00_SEARCH" "$Q00_SEARCH" "$Q00_SEARCH"
set_stage native-equal-time
run_view native movetime "$C0_SEARCH" "$Q00_SEARCH" "$HISTORICAL_SEARCH"

set_stage aggregate-verdict
python3 jobs/tools/l3_pure_m0_verdict.py \
  --historical-a-gen2 "$ART/historical-c0-a-vs-gen2.json" --historical-p1-gen2 "$ART/historical-p1-g4-vs-gen2.json" --historical-p1-a "$ART/historical-p1-g4-vs-c0-a.json" \
  --q00-a-gen2 "$ART/q00-c0-a-vs-gen2.json" --q00-p1-gen2 "$ART/q00-p1-g4-vs-gen2.json" --q00-p1-a "$ART/q00-p1-g4-vs-c0-a.json" \
  --native-a-gen2 "$ART/native-c0-a-vs-gen2.json" --native-p1-gen2 "$ART/native-p1-g4-vs-gen2.json" --native-p1-a "$ART/native-p1-g4-vs-c0-a.json" \
  --out "$ART/m0-triangle-verdict.json" --summary-out "$ART/JASS_CONTROL_SUMMARY.json" | tee -a "$RES"
python3 - "$ART/m0-triangle-verdict.json" "$ART" <<'PY'
import json,sys
from pathlib import Path
p=json.load(open(sys.argv[1])); art=Path(sys.argv[2])
def safe(v): return ('P' if v>=0 else 'M')+f'{abs(v):.1f}'.replace('.','_')
n=p['views']['native']; parent=p['recommended_parent_for_human_review']
markers=[f"VERDICT__{p['decision']}",f"RECOMMENDED_PARENT__{parent}",f"C0_A_NATIVE_ELO_VS_GEN2__{safe(n['c0_a_vs_gen2']['elo'])}",f"P1_0842_NATIVE_ELO_VS_GEN2__{safe(n['p1_g4_vs_gen2']['elo'])}",f"P1_0842_NATIVE_ELO_VS_C0_A__{safe(n['p1_g4_vs_c0_a']['elo'])}","M1_AUTHORIZED__FALSE"]
for name in markers: (art/name).write_text(name+'\n')
PY
set_stage complete
say "=== M0 triangle complete; recommendation only, M1 remains unauthorized ==="
