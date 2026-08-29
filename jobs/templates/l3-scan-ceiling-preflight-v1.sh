#!/usr/bin/env bash
# HOME-only technical preflight for the preregistered Scan ceiling benchmark.
# Fixed sentinels only: no scientific cohort, fit, calibration, game or metric.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_ATTEMPT_ID:?}"
: "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_HOST:?}"
: "${FULL_RUN_APPROVED:?}"; : "${SCIENTIFIC_GO:?}"

export SCAN_BENCHMARK_ONLY=true
SCAN_COMMIT="7aae17e7b7bfc47744601afb1ee7655e18983ce5"
SCAN_TREE="023eace16a90ec543b6b6174c79cfc42488a356e"
MAKEFILE_BLOB="7598768214fd8b3120067b65702de4756e9d8b83"
PROTOCOL_BLOB="a65b0943bb4e026b2d54df5b9c638e3d80de92ca"
SCAN_SOURCE_URL="https://github.com/rhalbersma/scan"
CURRICULUM_PREFIX="r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/20260814T191555Z-18c38a33"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
CXXFLAGS_EXACT="-pthread -std=c++14 -fno-rtti -O2 -mpopcnt -flto -DNDEBUG"
LDFLAGS_EXACT="-pthread -O2 -flto"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
IN="$JASS_RESULT_DIR/inputs"
ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
STAGE="$W/.stage"
: >"$RES"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

DFA=$(df -Pm /root | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 3000 ] || { say "ABORT disque HOME <3Go"; exit 3; }
say "disk_free_mb=$DFA"

arch_assert(){
  local ref="$1" scratch="$W/arch-ref"
  mkdir -p "$scratch/src"
  for file in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/movegen.cpp src/movegen.hpp; do
    git show "$ref:$file" >"$scratch/$file" || die "cannot materialize arch ref $ref:$file"
    cmp -s "$scratch/$file" "$file" || die "arch source is not byte-exact: $file"
  done
  grep -q 'g_emasks' src/scan_eval.cpp || die "arch guard: scan_eval missing g_emasks"
  grep -q 'has_any_capture' src/search.cpp || die "arch guard: search missing has_any_capture"
  grep -q 'has_any_capture' src/movegen.cpp || die "arch guard: movegen missing has_any_capture"
  say "arch_guard=PASS ref=$ref byte_exact=5 g_emasks=1 has_any_capture=2"
}

MON=""
monitor(){
  (t0=$(date +%s); while true; do
    {
      printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
      printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
      printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
      printf 'scan_benchmark_only=true\n'
    } >"$PROG.tmp"
    mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120
  done) & MON="$!"
}
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^home-[0-9]+-l3-scan-ceiling-preflight-v1$ ]] || die "HOME job nomenclature drift"
[ "$(hostname)" = "$EXPECTED_HOST" ] || die "HOME host mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$FULL_RUN_APPROVED" = 1 ] && [ "$SCIENTIFIC_GO" = 1 ] || die "execution GO missing"
[ "$(nproc)" -eq 16 ] || die "HOME 16-CPU contract mismatch"
[ "$SCAN_BENCHMARK_ONLY" = true ] || die "benchmark-only guard missing"
for command in git g++ make cmake python3 rclone lscpu sha256sum cmp timeout df; do
  command -v "$command" >/dev/null || die "$command missing"
done
unset JASS_TB_MOVE_ORDER_POLICY JASS_DSSD_MOVE_ORDER_POLICY JASS_T3_F6_MODEL
NUMERIC_VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
[ -f "$NUMERIC_VENV/.jass-runtime-ready-v1" ] || die "numeric test runtime absent"
NUMERIC_PY="$NUMERIC_VENV/bin/python"
"$NUMERIC_PY" -c 'import numpy; assert numpy.__version__' || die "NumPy test runtime invalid"
monitor

stage repository-contract-tests
python3 -m py_compile \
  jobs/tools/scan_ceiling_preflight.py jobs/tools/scan_ceiling_scan_score.py \
  jobs/tools/scan_ceiling_fen_to_jnnw.py jobs/tools/scan_ceiling_merge.py \
  jobs/tools/scan_ceiling_select.py jobs/tools/scan_ceiling_static_score.py \
  jobs/tools/scan_ceiling_readout.py jobs/tools/scan_ceiling_runtime_snapshot.py \
  jobs/tools/scan_ceiling_shard_timeouts.py
"$NUMERIC_PY" -m unittest jobs.tests.test_scan_ceiling_benchmark -v >"$W/unit-tests.log" 2>&1

stage locate-real-egdb
EGDIR=""
for directory in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$directory"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$directory"; break; }
done
[ -n "$EGDIR" ] || die "real HOME EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB=256

stage fetch-authenticate-curriculum
python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_PREFIX" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" >"$W/fetch-curriculum.log" 2>&1 \
  || die "CURRICULUM fetch failed"
gunzip -t "$IN/curriculum.pjtw.gz"
gunzip -c "$IN/curriculum.pjtw.gz" >"$IN/curriculum.pjtw"
[ "$(sha256sum "$IN/curriculum.pjtw" | awk '{print $1}')" = "$CURRICULUM_SHA" ] \
  || die "CURRICULUM raw SHA drift"

stage fetch-authenticate-pinned-official-scan-source
git clone "$SCAN_SOURCE_URL" "$W/scan-src" >"$W/scan-clone.log" 2>&1 \
  || die "official Scan source clone failed"
git -C "$W/scan-src" checkout --detach "$SCAN_COMMIT" >>"$W/scan-clone.log" 2>&1
[ "$(git -C "$W/scan-src" rev-parse HEAD)" = "$SCAN_COMMIT" ] || die "Scan commit drift"
[ "$(git -C "$W/scan-src" rev-parse 'HEAD^{tree}')" = "$SCAN_TREE" ] || die "Scan tree drift"
[ "$(git -C "$W/scan-src" rev-parse HEAD:src/Makefile)" = "$MAKEFILE_BLOB" ] || die "Scan Makefile blob drift"
[ "$(git -C "$W/scan-src" rev-parse HEAD:protocol.txt)" = "$PROTOCOL_BLOB" ] || die "Scan protocol blob drift"
[ -z "$(git -C "$W/scan-src" ls-files -m)" ] || die "Scan source dirty before build"
[ -f "$W/scan-src/data/eval" ] || die "official Scan eval missing"
[ -f "$W/scan-src/scan.ini" ] || die "official Scan ini missing"

stage compile-unmodified-official-scan-on-home
make -C "$W/scan-src/src" -j8 >"$W/scan-build.log" 2>&1
SCAN="$W/scan-runtime/scan_home"
mkdir -p "$W/scan-runtime/data"
cp "$W/scan-src/src/scan" "$SCAN"
cp "$W/scan-src/data/eval" "$W/scan-runtime/data/eval"
cp "$W/scan-src/scan.ini" "$W/scan-runtime/scan.ini"
chmod 0555 "$SCAN"
[ -z "$(git -C "$W/scan-src" ls-files -m)" ] || die "tracked Scan source changed during build"

stage compile-technical-official-move-adapter
SCAN_SOURCES=()
while IFS= read -r source; do SCAN_SOURCES+=("$source"); done < <(
  find "$W/scan-src/src" -maxdepth 1 -type f -name '*.cpp' ! -name main.cpp | sort
)
[ "${#SCAN_SOURCES[@]}" -eq 25 ] || die "unexpected Scan source file count for technical adapter"
PROBE="$W/scan-runtime/scan_move_probe"
g++ -pthread -std=c++14 -fno-rtti -O2 -mpopcnt -flto -DNDEBUG \
  -I"$W/scan-src/src" jobs/tools/scan_ceiling_scan_move_probe.cpp \
  "${SCAN_SOURCES[@]}" -pthread -O2 -flto -o "$PROBE" >"$W/scan-probe-build.log" 2>&1
chmod 0555 "$PROBE"

stage publish-build-provenance-before-smoke
cp "$W/scan-src/src/Makefile" "$ART/scan-official-Makefile"
cp "$W/scan-src/protocol.txt" "$ART/scan-official-protocol.txt"
python3 - "$ART/scan-build-manifest.json" "$SCAN" "$PROBE" \
  "$W/scan-src" "$CXXFLAGS_EXACT" "$LDFLAGS_EXACT" <<'PY_BUILD'
import hashlib,json,os,platform,subprocess,sys
from pathlib import Path
out,scan,probe,source=map(Path,sys.argv[1:5]); cxx,ld=sys.argv[5:7]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
run=lambda a:subprocess.run(a,text=True,check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT).stdout.strip()
payload={
 'schema':'jass.scan_ceiling_scan_home_build.v1',
 'source_url':'https://github.com/rhalbersma/scan',
 'release':'Scan 3.1','source_tag':None,
 'source_commit':'7aae17e7b7bfc47744601afb1ee7655e18983ce5',
 'source_tree':'023eace16a90ec543b6b6174c79cfc42488a356e',
 'makefile_blob':'7598768214fd8b3120067b65702de4756e9d8b83',
 'protocol_blob':'a65b0943bb4e026b2d54df5b9c638e3d80de92ca',
 'compiler_command':'g++','compiler_version':run(['g++','--version']),
 'cxxflags':cxx,'ldflags':ld,'official_make_command':'make -C scan-src/src -j8',
 'operating_system':run(['uname','-a']),'cpu_information':run(['lscpu']),
 'logical_cpus':os.cpu_count(),'threads_per_search':1,'scan_bb_size':0,
 'scan_binary_sha256':sha(scan),'scan_move_probe_sha256':sha(probe),
 'scan_eval_sha256':sha(source/'data/eval'),'scan_ini_sha256':sha(source/'scan.ini'),
 'source_transport':'git clone official URL plus detached exact commit',
 'source_bundle_sha256':None,
 'makefile_raw_sha256':sha(source/'src/Makefile'),
 'protocol_raw_sha256':sha(source/'protocol.txt'),
 'tracked_scan_source_modified':bool(run(['git','-C',str(source),'ls-files','-m'])),
 'scan_algorithms_modified':False,'benchmark_only':True,
}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_BUILD

stage build-jass-technical-adapters
arch_assert "$EXPECTED_CODE_SHA"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen-patterns.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON \
  -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target \
  jass_scan_ceiling_parent_filter jass_scan_ceiling_source_generator \
  jass_scan_ceiling_sibling_export jass_scan_ceiling_jass_ladder \
  >"$W/jass-build.log" 2>&1

stage score-free-source-generator-rate-smoke
SOURCE_RATE_COUNT=200
SOURCE_RATE_T0=$(date +%s%N)
timeout -k 120s 600s "$W/build/jass_scan_ceiling_source_generator" \
  "$SOURCE_RATE_COUNT" "$W/source-rate-smoke.jnnw" "$W/source-rate-smoke-report.json" \
  2026091399 8 160 9 >"$W/source-rate-smoke.log" 2>&1
SOURCE_RATE_T1=$(date +%s%N)
SOURCE_RATE_NS=$((SOURCE_RATE_T1-SOURCE_RATE_T0))
[ "$SOURCE_RATE_NS" -gt 0 ] || die "source rate smoke has non-positive duration"
python3 - "$W/source-rate-smoke-report.json" "$ART/source-rate-smoke.json" \
  "$SOURCE_RATE_COUNT" "$SOURCE_RATE_NS" <<'PY_SOURCE_RATE'
import json,sys
from pathlib import Path
report,out=map(Path,sys.argv[1:3]); count,elapsed_ns=map(int,sys.argv[3:])
p=json.loads(report.read_text())
if p.get('records')!=count or p.get('scores_generated')!=0 or p.get('wdl_generated')!=0 or p.get('evaluations')!=0:
 raise SystemExit('score-free source rate smoke drift')
elapsed=elapsed_ns/1_000_000_000
out.write_text(json.dumps({'schema':'jass.scan_ceiling_source_rate_smoke.v1',
 'planning_only_not_scientific_metric':True,'records':count,'elapsed_seconds':elapsed,
 'records_per_second':count/elapsed,'scores_generated':0,'wdl_generated':0,
 'selection_seed_used':False,'technical_smoke_only':True,
 'eligible_for_scientific_cohort':False},indent=2,sort_keys=True)+'\n')
PY_SOURCE_RATE

stage fixed-sentinel-export-no-scientific-score
python3 jobs/tools/scan_ceiling_fen_to_jnnw.py \
  --input jobs/fixtures/scan_ceiling_smoke_parents.fen \
  --output "$W/smoke-parents.jnnw" --expected-count 7 \
  --report "$ART/smoke-parent-conversion.json" >"$W/fen-convert.log" 2>&1
EXPORT_RATE_T0=$(date +%s%N)
timeout -k 120s 600s "$W/build/jass_scan_ceiling_sibling_export" \
  "$W/smoke-parents.jnnw" "$W/smoke-children.jnnw" "$W/smoke-groups.tsv" \
  "$ART/smoke-export.json" "$IN/curriculum.pjtw" "$EGDIR" 0 1 256 \
  >"$W/smoke-export.log" 2>&1
EXPORT_RATE_T1=$(date +%s%N)
EXPORT_RATE_NS=$((EXPORT_RATE_T1-EXPORT_RATE_T0))
[ "$EXPORT_RATE_NS" -gt 0 ] || die "sibling export rate smoke has non-positive duration"
python3 - "$ART/source-rate-smoke.json" "$ART/smoke-export.json" \
  "$ART/selection-operational-rate-smokes.json" "$EXPORT_RATE_NS" <<'PY_SELECTION_RATES'
import json,sys
from pathlib import Path
source,export,out=map(Path,sys.argv[1:4]); elapsed_ns=int(sys.argv[4])
s=json.loads(source.read_text()); e=json.loads(export.read_text()); elapsed=elapsed_ns/1_000_000_000
parents=int(e['input_parents'])
if parents!=7 or elapsed<=0: raise SystemExit('sibling export operational rate drift')
out.write_text(json.dumps({'schema':'jass.scan_ceiling_selection_operational_rates.v1',
 'planning_only_not_scientific_metric':True,'source_generator':s,
 'sibling_export':{'parents':parents,'elapsed_seconds':elapsed,'parents_per_second':parents/elapsed},
 'scientific_metrics_published':0},indent=2,sort_keys=True)+'\n')
PY_SELECTION_RATES

stage mapping-node-pov-determinism-preflight
set +e
python3 jobs/tools/scan_ceiling_preflight.py \
  --scan "$SCAN" --scan-source "$W/scan-src" --scan-probe "$PROBE" \
  --build-manifest "$ART/scan-build-manifest.json" \
  --parents-fen jobs/fixtures/scan_ceiling_smoke_parents.fen \
  --parents-jnnw "$W/smoke-parents.jnnw" --children-jnnw "$W/smoke-children.jnnw" \
  --groups "$W/smoke-groups.tsv" --export-report "$ART/smoke-export.json" \
  --jass-ladder "$W/build/jass_scan_ceiling_jass_ladder" \
  --curriculum "$IN/curriculum.pjtw" --egdb "$EGDIR" --workdir "$W" \
  --output "$ART/scan-technical-preflight.json" \
  --transcript "$ART/scan-technical-transcript.txt" \
  >"$W/preflight.log" 2>&1
PREFLIGHT_RC=$?
set -e
if [ "$PREFLIGHT_RC" -eq 0 ]; then
  python3 - "$ART/scan-technical-preflight.json" \
    "$ART/selection-operational-rate-smokes.json" <<'PY_INJECT_RATES'
import json,math,sys
from pathlib import Path
report,rates=map(Path,sys.argv[1:3]); p=json.loads(report.read_text()); r=json.loads(rates.read_text())
source_rate=float(r['source_generator']['records_per_second'])
export_rate=float(r['sibling_export']['parents_per_second'])
source_healthy=50000/source_rate; export_healthy=125/export_rate
source_timeout=max(300,math.ceil(source_healthy*1.3+120))
export_timeout=max(300,math.ceil(export_healthy*1.3+120))
selection={
 'planning_only_not_scientific_metric':True,'source_records_per_shard':50000,
 'export_parents_per_shard_upper':125,'source_records_per_second':source_rate,
 'export_parents_per_second':export_rate,'safety_factor':1.3,'grace_seconds':120,
 'source_healthy_seconds_per_shard':source_healthy,
 'source_timeout_seconds_per_shard':source_timeout,
 'export_healthy_seconds_per_shard':export_healthy,
 'export_timeout_seconds_per_shard':export_timeout,
 'two_wave_healthy_eta_seconds_excluding_fetch_build_and_merge':2*(source_healthy+export_healthy),
}
planning=p['throughput_and_eta']; planning['selection_runtime']=selection
planning['stage_eta_ranges']['selection']={
 'eta':'rate_measured_on_home_preflight',
 'two_wave_healthy_eta_seconds_excluding_fetch_build_and_merge':selection['two_wave_healthy_eta_seconds_excluding_fetch_build_and_merge'],
 'source_timeout_seconds_per_shard':source_timeout,
 'export_timeout_seconds_per_shard':export_timeout,
}
report.write_text(json.dumps(p,indent=2,sort_keys=True)+'\n')
PY_INJECT_RATES
fi
cp "$ART/scan-technical-preflight.json" "$ART/JASS_CONTROL_SUMMARY.json"
if [ "$PREFLIGHT_RC" -ne 0 ]; then
  : >"$ART/VERDICT__SCAN_MAPPING_TECHNICAL_STOP"
  die "SCAN_MAPPING_TECHNICAL_STOP; inspect technical transcript"
fi
python3 - "$ART/scan-technical-preflight.json" <<'PY_PASS'
import json,sys
p=json.load(open(sys.argv[1]))
assert p['passed'] is True and p['verdict']=='SCAN_MAPPING_TECHNICAL_PASS'
assert p['scientific_metrics_published']==0 and p['guards']['fits']==0
PY_PASS

stage freeze-byte-identical-home-runtime
gzip -n -c "$SCAN" >"$ART/scan-home-compiled.gz"
gzip -n -c "$PROBE" >"$ART/scan-move-probe.gz"
cp "$W/scan-runtime/data/eval" "$ART/scan-data-eval"
cp "$W/scan-runtime/scan.ini" "$ART/scan.ini"
gzip -n -c "$W/build/jass_scan_ceiling_sibling_export" >"$ART/jass-sibling-export.gz"
gzip -n -c "$W/build/jass_scan_ceiling_jass_ladder" >"$ART/jass-search-ladder.gz"
cp "$IN/curriculum.pjtw" "$ART/curriculum.pjtw"
python3 - "$ART/runtime-payload-manifest.json" "$ART" <<'PY_PAYLOAD'
import hashlib,json,sys
from pathlib import Path
out,root=map(Path,sys.argv[1:3]); names=['scan-home-compiled.gz','scan-move-probe.gz','scan-data-eval','scan.ini','jass-sibling-export.gz','jass-search-ladder.gz','curriculum.pjtw']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
out.write_text(json.dumps({'schema':'jass.scan_ceiling_runtime_payload.v1','benchmark_only':True,
 'files':{n:{'sha256':sha(root/n),'size_bytes':(root/n).stat().st_size} for n in names}},indent=2,sort_keys=True)+'\n')
PY_PAYLOAD
: >"$ART/VERDICT__SCAN_MAPPING_TECHNICAL_PASS"
: >"$ART/SCAN_BENCHMARK_ONLY__TRUE"
: >"$ART/STRENGTH_GAMES__0"
printf 'PROMOTION_AUTHORIZED__FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'AUTOMATIC_NEXT_JOB__NULL\n' >"$ART/AUTOMATIC_NEXT_JOB__NULL"
say "SCAN_MAPPING_TECHNICAL_PASS source=$SCAN_COMMIT binary=$(sha256sum "$SCAN" | awk '{print $1}')"
say "scientific_metrics=0 fits=0 strength_games=0 promotion=false"
