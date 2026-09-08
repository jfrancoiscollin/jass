#!/usr/bin/env bash
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_STAGE_SPEC:?}"; : "${JASS_JOB_ID:?}"; : "${ED2_PAIRED_GO:?}"
cd "$JASS_CODE_DIR"
export PYTHONPATH="$JASS_CODE_DIR" PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"; RES="$W/RESULTS.txt"; : >"$RES"
phase(){ printf 'phase=%s time_utc=%s\n' "$1" "$(date -u +%FT%TZ)" | tee -a "$RES"; }
finalize(){
 rc=$?; trap - EXIT ERR TERM INT; set +e
 cp "$RES" "$ART/RESULTS.txt"
 mkdir -p "$ART/execution-logs" "$ART/native"
 for table in "$W"/*native.tsv; do [ ! -f "$table" ] || gzip -n -c "$table" >"$ART/native/$(basename "$table").gz"; done
 find "$W" -maxdepth 1 -name '*.log' -type f -exec cp {} "$ART/execution-logs/" \;
 exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; printf "TECHNICAL_ABORT line=%s rc=%s\n" "$LINENO" "$rc" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT
[ "$ED2_PAIRED_GO" = 1 ]; [ "$(hostname)" = cpx62 ]
[ "$(env -u OMP_NUM_THREADS -u OMP_THREAD_LIMIT nproc)" -eq 16 ]
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ]
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -gt 3000 ]
[ "$(uname -m)" = x86_64 ]; grep -qw popcnt /proc/cpuinfo
PY="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}/bin/python"
[ -x "$PY" ]; "$PY" -c 'import numpy,scipy'
SPEC_CODE=$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["code_sha"])' "$JASS_STAGE_SPEC")
[ "$(git rev-parse HEAD)" = "$SPEC_CODE" ]
unset JASS_DENSE_REMAP JASS_T3_F6_MODEL JASS_TB_MOVE_ORDER_POLICY JASS_DSSD_MOVE_ORDER_POLICY || true
fetch(){
 local prefix="$1" receipt="$2"; shift 2
 timeout 300s python3 jobs/tools/fetch_result_files.py --prefix "$prefix" --expected-state completed \
  --out-dir "$IN" --report "$ART/$receipt.json" "$@" >"$W/$receipt.log" 2>&1
 "$PY" - "$ART/$receipt.json" "$prefix" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]));job,attempt=sys.argv[2].rstrip('/').split('/')[-2:]
assert (r['job_id'],r['attempt_id'],r['result_state'],r['exit_code'])==(job,attempt,'completed',0)
assert r['code_sha'].startswith(attempt.split('-')[-1])
PY
}
P0=r2:jass-data/runs/cpx62-1875-l3-ed2-data-teacher-preflight-v1/20260908T171140Z-bc30d685
phase authenticate-p0-ready-before-any-teacher
fetch "$P0" verified-p0-ready --file artefacts/ed2-preflight.json=ed2-preflight.json
"$PY" - "$IN/ed2-preflight.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
assert p['verdict']=='ED2_DATA_AND_TEACHER_PREFLIGHT_READY_V1'
assert p['fits']==0 and p['training_labels_generated']==0 and p['test_labels_generated']==0
assert 0<p['projected_teacher_plus_fit_seconds']<=2700
PY
files=()
for name in parents.jnnw children.jnnw parents.tsv groups.tsv source.json; do
 files+=(--file "artefacts/source/$name=source/$name")
done
fetch "$P0" verified-p0-data "${files[@]}" \
 --file artefacts/ed2-source-seal.json=ed2-source-seal.json \
 --file artefacts/benchmark-exclusions.txt=benchmark-exclusions.txt
phase authenticate-frozen-value-and-historical-wdl-source
fetch r2:jass-data/runs/cpx62-1849-l3-decision-math-d1-wdl-listwise-fit-stage-env-recovery-requeue-v1/20260906T222203Z-08fd187a verified-base \
 --file artefacts/WDL_CONTROL.pjtw.gz=WDL_CONTROL.pjtw.gz
fetch r2:jass-data/runs/cpx62-1340-jass-megacorpus-comparative-fit-v1/20260814T123246Z-2ce07222 verified-current-targets \
 --file artefacts/current_2m-context30.npy.gz=current-context30.npy.gz \
 --file artefacts/current_2m-manifest.json=current-manifest.json
fetch r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984 verified-current-source \
 --file artefacts/turnover1to1.jnnw.gz=turnover.jnnw.gz \
 --file artefacts/turnover1to1.jsm.gz=turnover.jsm.gz
for name in turnover.jnnw turnover.jsm; do gunzip -c "$IN/$name.gz" >"$W/$name"; done
[ "$(sha256sum "$W/turnover.jnnw" | awk '{print $1}')" = 9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d ]
[ "$(sha256sum "$W/turnover.jsm" | awk '{print $1}')" = acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682 ]
timeout 300s python3 tools/selfplay_frontier.py split --data "$W/turnover.jnnw" --meta "$W/turnover.jsm" \
 --out-data "$W/current.jnnw" --out-meta "$W/current.jsm" --holdout-mod 10 --seed 577215 \
 --manifest "$W/current-manifest.json" >"$W/split.log" 2>&1
cmp "$W/current-manifest.json" "$IN/current-manifest.json"
gunzip -c "$IN/current-context30.npy.gz" >"$W/current-context30.npy"
gunzip -c "$IN/WDL_CONTROL.pjtw.gz" >"$W/BASE.pjtw"
[ "$(sha256sum "$W/BASE.pjtw" | awk '{print $1}')" = e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0 ]
phase authenticate-unchanged-official-scan
fetch r2:jass-data/runs/home-1650-l3-scan-ceiling-preflight-v1/20260829T132800Z-28e12fba verified-scan-runtime \
 --file artefacts/scan-build-manifest.json=scan-build-manifest.json \
 --file artefacts/scan-home-compiled.gz=scan-home-compiled.gz \
 --file artefacts/scan-data-eval=scan-data-eval --file artefacts/scan.ini=scan.ini
mkdir -p "$W/scan/data"
gunzip -c "$IN/scan-home-compiled.gz" >"$W/scan/scan"; chmod 0555 "$W/scan/scan"
cp "$IN/scan-data-eval" "$W/scan/data/eval"; cp "$IN/scan.ini" "$W/scan/scan.ini"
phase build-isolated-native-evaluator-probe
mkdir "$W/src"; git archive HEAD | tar -x -C "$W/src"
(cd "$W/src" && python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf) >"$W/geometry.log" 2>&1
cat >>"$W/src/CMakeLists.txt" <<'CMAKE'

add_executable(jass_ed2_value_probe jobs/tools/ed2_value_probe.cpp)
target_link_libraries(jass_ed2_value_probe PRIVATE jass_lib)
CMAKE
timeout 180s cmake -S "$W/src" -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
 -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
timeout 600s cmake --build "$W/build" -j16 --target jass_ed2_value_probe >"$W/build.log" 2>&1
phase paired-pipeline-train-before-sealed-test
"$PY" jobs/tools/ed2_value_entrypoint.py run \
 --source "$IN/source" --exclusions "$IN/benchmark-exclusions.txt" \
 --source-seal "$IN/ed2-source-seal.json" --preflight "$IN/ed2-preflight.json" \
 --base "$W/BASE.pjtw" --current "$W/current.jnnw" --meta "$W/current.jsm" --targets "$W/current-context30.npy" \
 --scan "$W/scan/scan" --scan-build "$IN/scan-build-manifest.json" \
 --probe "$W/build/jass_ed2_value_probe" --art "$ART" --work "$W" >"$W/pipeline.log" 2>&1
"$PY" - "$ART/scientific-summary.json" "$SPEC_CODE" "$JASS_JOB_ID" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]);r=json.loads(p.read_text())
r.update(code_sha=sys.argv[2],job_id=sys.argv[3]);p.write_text(json.dumps(r,indent=2,sort_keys=True,allow_nan=False)+'\n')
assert r['strength_games']==0 and r['fits'] in (0,2)
print(r['verdict'])
PY
phase terminal-no-automatic-runtime-or-elo
