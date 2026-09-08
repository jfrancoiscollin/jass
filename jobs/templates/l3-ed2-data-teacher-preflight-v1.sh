#!/usr/bin/env bash
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_STAGE_SPEC:?}"; : "${JASS_JOB_ID:?}"; : "${ED2_PREFLIGHT_GO:?}"
cd "$JASS_CODE_DIR"
export PYTHONPATH="$JASS_CODE_DIR" PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"; RES="$W/RESULTS.txt"; : >"$RES"
phase(){ printf 'phase=%s time_utc=%s\n' "$1" "$(date -u +%FT%TZ)" | tee -a "$RES"; }
finalize(){
 rc=$?; trap - EXIT ERR TERM INT; set +e
 cp "$RES" "$ART/RESULTS.txt"
 mkdir -p "$ART/execution-logs"
 find "$W" -maxdepth 1 -name '*.log' -type f -exec cp {} "$ART/execution-logs/" \;
 python3 "$JASS_CODE_DIR/jobs/tools/ed2_cleanup_scratch.py" --work "$W" --artifact "$ART" >"$ART/execution-logs/scratch-cleanup.log" 2>&1
 cleanup_rc=$?
 if [ "$rc" -eq 0 ] && [ "$cleanup_rc" -ne 0 ]; then rc=$cleanup_rc; fi
 exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; printf "TECHNICAL_ABORT line=%s rc=%s\n" "$LINENO" "$rc" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT
[ "$ED2_PREFLIGHT_GO" = 1 ]
[ "$(hostname)" = cpx62 ]
NCPU=$(env -u OMP_NUM_THREADS -u OMP_THREAD_LIMIT nproc); [ "$NCPU" -eq 16 ]
printf 'host=cpx62 available_cpus=%s numeric_threads=1\n' "$NCPU" >>"$RES"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ]
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -gt 3000 ]
[ "$(uname -m)" = x86_64 ]; grep -qw popcnt /proc/cpuinfo
PY="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}/bin/python"
[ -x "$PY" ]; "$PY" -c 'import numpy, scipy'
SPEC_CODE=$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1]))["code_sha"])' "$JASS_STAGE_SPEC")
[ "$(git rev-parse HEAD)" = "$SPEC_CODE" ]; export ED2_CODE_SHA="$SPEC_CODE"
fetch(){
 local prefix="$1" receipt="$2"; shift 2
 timeout 300s python3 jobs/tools/fetch_result_files.py --prefix "$prefix" --expected-state completed \
  --out-dir "$IN" --report "$ART/$receipt.json" "$@" >"$W/$receipt.log" 2>&1
}
phase authenticate-terminal-and-benchmark-exclusions
fetch r2:jass-data/runs/cpx62-1874-l3-ed1-partial-order-audit-openmp-recovery-v1/20260908T161858Z-941faa2d verified-ed1 \
 --file artefacts/scientific-summary.json=ed1-summary.json
"$PY" - "$IN/ed1-summary.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
assert p['verdict']=='ED1_PARTIAL_ORDER_LABEL_SIGNAL_V1'
assert p['fit_authorized'] is False and p['benchmark_training_allowed'] is False
assert all(p['cohorts'][c]['supported'] for c in ('A','B'))
PY
fetch r2:jass-data/runs/home-1651-l3-scan-ceiling-selection-v1/20260829T133348Z-28e12fba verified-exclusions \
 --file artefacts/parents.jnnw.gz=benchmark-parents.jnnw.gz \
 --file artefacts/children.jnnw.gz=benchmark-children.jnnw.gz
for name in parents children; do gunzip -c "$IN/benchmark-$name.jnnw.gz" >"$W/benchmark-$name.jnnw"; done
"$PY" jobs/tools/ed2_preflight.py exclude --parents "$W/benchmark-parents.jnnw" \
 --children "$W/benchmark-children.jnnw" --out "$ART/benchmark-exclusions.txt" >"$W/exclude.log" 2>&1
phase build-isolated-scorefree-generator
mkdir "$W/src"; git archive HEAD | tar -x -C "$W/src"
cat >>"$W/src/CMakeLists.txt" <<'CMAKE'

add_executable(jass_ed2_source jobs/tools/ed2_source.cpp)
target_link_libraries(jass_ed2_source PRIVATE jass_lib)
CMAKE
timeout 180s cmake -S "$W/src" -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
 -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
timeout 600s cmake --build "$W/build" -j16 --target jass_ed2_source >"$W/build.log" 2>&1
phase generate-and-seal-independent-data
timeout 240s "$W/build/jass_ed2_source" "$ART/benchmark-exclusions.txt" "$ART/source" production >"$W/generate.log" 2>&1
"$PY" jobs/tools/ed2_preflight.py seal --source "$ART/source" --exclusions "$ART/benchmark-exclusions.txt" \
 --out "$ART/ed2-source-seal.json" >"$W/seal.log" 2>&1
phase authenticate-official-scan-runtime
fetch r2:jass-data/runs/home-1650-l3-scan-ceiling-preflight-v1/20260829T132800Z-28e12fba verified-scan-runtime \
 --file artefacts/scan-build-manifest.json=scan-build-manifest.json \
 --file artefacts/scan-home-compiled.gz=scan-home-compiled.gz \
 --file artefacts/scan-data-eval=scan-data-eval \
 --file artefacts/scan.ini=scan.ini
mkdir -p "$W/scan/data"
gunzip -c "$IN/scan-home-compiled.gz" >"$W/scan/scan"; chmod 0555 "$W/scan/scan"
cp "$IN/scan-data-eval" "$W/scan/data/eval"; cp "$IN/scan.ini" "$W/scan/scan.ini"
phase measure-calibration-only-maximum-4335000-requested-nodes
timeout 240s "$PY" jobs/tools/ed2_preflight.py measure --source "$ART/source" --seal "$ART/ed2-source-seal.json" \
 --scan "$W/scan/scan" --build "$IN/scan-build-manifest.json" --out "$ART/ed2-preflight.json" >"$W/measure.log" 2>&1
"$PY" - "$ART" "$SPEC_CODE" "$JASS_JOB_ID" <<'PY'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); r=json.loads((art/'ed2-preflight.json').read_text())
r.update(code_sha=sys.argv[2],job_id=sys.argv[3])
assert r['fits']==0 and r['test_labels_generated']==0 and r['training_labels_generated']==0
with (art/'scientific-summary.json').open('x') as f: json.dump(r,f,sort_keys=True,indent=2,allow_nan=False); f.write('\n')
(art/('VERDICT__'+r['verdict'])).write_text(r['verdict']+'\n')
print(r['verdict'])
PY
phase terminal-no-automatic-fit