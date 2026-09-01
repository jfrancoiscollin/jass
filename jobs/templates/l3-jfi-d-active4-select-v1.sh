#!/usr/bin/env bash
# JFI-D ACTIVE_4M target-blind selection, authorized only by a passing JFI-C.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${JFI_C_ROOT:?}"; : "${EXPECTED_JFI_C_JOB:?}"; : "${EXPECTED_JFI_C_ATTEMPT:?}"; : "${EXPECTED_JFI_C_CODE_SHA:?}"
: "${BOUNDARY_B_ROOT:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"; GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$IN" "$ART" "$GEOM"; RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*"|tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }
AB_ROOT="r2:jass-data/runs/cpx62-1749-l3-jfi-factorial-l2-fit-v1/20260901T225526Z-25bb488e"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"; PY="$VENV/bin/python"
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null||true; rm -rf "$W/build" "$IN" "$GEOM" 2>/dev/null||true; rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat "$W"/*.npy 2>/dev/null||true; exit "$rc"; }
trap finalize EXIT; trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-jfi-d-active4-select-v1$ ]] || die "nomenclature mismatch"
[ "${JFI_C_PASS_AUTHORIZED:-0}" = 1 ] && [ "${NO_TARGET_READS_BEFORE_SELECTION_FREEZE:-0}" = 1 ] || die "JFI-D authorization missing"
[ "${NO_FULL_FITS:-0}" = 1 ] && [ "${NO_SCAN_READS:-0}" = 1 ] || die "zero-compute guard missing"
[ "${NO_FRESH_OPENINGS:-0}" = 1 ] && [ "${NO_STRENGTH_GAMES:-0}" = 1 ] || die "game guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] && [ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "source drift"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX62 contract mismatch"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "numeric runtime absent"

timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$JFI_C_ROOT" \
  --file artefacts/JFI_C_CERTIFICATE.json=jfi-c-certificate.json \
  --file artefacts/JFI_C_ACTIVE_VS_UNIFORM.json=jfi-c-readout.json \
  --file artefacts/VERDICT__JFI_ACTIVE_INFORMATION_GAIN_ESTABLISHED=PASS \
  --out-dir "$IN" --report "$ART/verified-jfi-c.json" >"$W/fetch-c.log" 2>&1
"$PY" - "$IN/jfi-c-certificate.json" "$IN/jfi-c-readout.json" "$ART/verified-jfi-c.json" \
 "$EXPECTED_JFI_C_JOB" "$EXPECTED_JFI_C_ATTEMPT" "$EXPECTED_JFI_C_CODE_SHA" <<'PY'
import json,sys
c=json.load(open(sys.argv[1])); r=json.load(open(sys.argv[2])); v=json.load(open(sys.argv[3]))
if (v.get('job_id'),v.get('attempt_id'),v.get('code_sha'),v.get('result_state'))!=(sys.argv[4],sys.argv[5],sys.argv[6],'completed'):
 raise SystemExit('JFI-C identity drift')
if c.get('verdict')!='JFI_ACTIVE_INFORMATION_GAIN_ESTABLISHED' or not r.get('gate',{}).get('pass'):
 raise SystemExit('JFI-C did not pass')
PY
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$BOUNDARY_B_ROOT" \
  --file artefacts/JFI_C_CANDIDATE_UNIVERSE.json=candidate-manifest.json \
  --file artefacts/JFI_C_CANDIDATE_10M.jnnw.gz=candidate.jnnw.gz \
  --file artefacts/JFI_C_CANDIDATE_10M.jsm.gz=candidate.jsm.gz \
  --file artefacts/JFI_C_CANDIDATE_ORIGIN.npy.gz=origin.npy.gz \
  --file artefacts/JFI_C_CANDIDATE_ROLES.npy.gz=roles.npy.gz \
  --out-dir "$IN" --report "$ART/verified-candidate.json" >"$W/fetch-candidate.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$AB_ROOT" \
  --file artefacts/JFI_B_FISHER.npy.gz=fisher.npy.gz --file artefacts/JFI_B_SELECTED_L2.txt=selected-l2.txt \
  --out-dir "$IN" --report "$ART/verified-jfi-b.json" >"$W/fetch-b.log" 2>&1
for name in candidate.jnnw candidate.jsm origin.npy roles.npy fisher.npy; do gunzip -c "$IN/$name.gz" >"$W/$name"; done
SELECTED_L2=$(cat "$IN/selected-l2.txt"); TRAIN=$("$PY" -c "import json;print(json.load(open('$IN/candidate-manifest.json'))['selection']['train_candidates'])")
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
timeout 14400s "$W/build/jass" --dump-eval-features "$W/candidate.jnnw" "$W/candidate.feat" >"$W/features.log" 2>&1
timeout 21600s env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH=".:$GEOM:pattern_jass/tools" "$PY" \
 jobs/tools/jfi_active_select_stream.py --stage d --data "$W/candidate.jnnw" --feat "$W/candidate.feat" \
 --candidate-manifest "$IN/candidate-manifest.json" --origin-indices "$W/origin.npy" --roles "$W/roles.npy" \
 --fisher "$W/fisher.npy" --l2 "$SELECTED_L2" --train-count "$TRAIN" --count 4000000 \
 --active-indices-out "$W/active4-indices.npy" --active-row-ids-out "$W/active4-row-ids.npy" \
 --manifest "$ART/JFI_D_SELECTION_MANIFEST.json" >"$W/select.log" 2>&1
gzip -n -c "$W/active4-indices.npy" >"$ART/JFI_D_ACTIVE4_INDICES.npy.gz"
gzip -n -c "$W/active4-row-ids.npy" >"$ART/JFI_D_ACTIVE4_ROW_IDS.npy.gz"
"$PY" - "$ART/JFI_D_SELECTION_MANIFEST.json" "$ART/JFI_D_SELECTION_CERTIFICATE.json" "$EXPECTED_CODE_SHA" <<'PY'
import hashlib,json,sys
d=json.load(open(sys.argv[1])); sha=hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest()
if d.get('schema')!='jass.jfi.d_active_selection.v1' or d.get('active_rows')!=4000000 or not d.get('dev_excluded'):
 raise SystemExit('JFI-D selection drift')
json.dump({'schema':'jass.jfi.d_selection_certificate.v1','code_sha':sys.argv[3],
 'selection_manifest_sha256':sha,'active_rows':4000000,
 'markers':{'TARGET_READS_TOTAL':0,'SCAN_READS':0,'FULL_FITS':0,
            'FRESH_OPENINGS':0,'STRENGTH_GAMES':0}},open(sys.argv[2],'w'),indent=2,sort_keys=True)
PY
printf '0\n' >"$ART/TARGET_READS_TOTAL__0"; printf '0\n' >"$ART/SCAN_READS__0"; printf '0\n' >"$ART/FULL_FITS__0"
printf '0\n' >"$ART/FRESH_OPENINGS__0"; printf '0\n' >"$ART/STRENGTH_GAMES__0"
touch "$ART/JFI_D_SELECTION_FROZEN"; say "JFI_D_ACTIVE4_SELECTION_FROZEN TARGET_READS_TOTAL=0 FULL_FITS=0"
