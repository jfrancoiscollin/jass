#!/usr/bin/env bash
# JFI-C post-freeze target reconstruction, two zero-centred fits and common-DEV
# gate. The separately completed selector result is mandatory and immutable.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${BOUNDARY_B_ROOT:?}"; : "${EXPECTED_BOUNDARY_B_JOB:?}"; : "${EXPECTED_BOUNDARY_B_ATTEMPT:?}"
: "${SELECTION_ROOT:?}"; : "${EXPECTED_SELECTION_JOB:?}"; : "${EXPECTED_SELECTION_ATTEMPT:?}"
: "${EXPECTED_SELECTION_CODE_SHA:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"; mkdir -p "$W" "$IN" "$ART" "$GEOM"
RES="$W/RESULTS.txt"; STAGE="$W/.stage"; : >"$RES"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

AB_ROOT="r2:jass-data/runs/cpx62-1749-l3-jfi-factorial-l2-fit-v1/20260901T225526Z-25bb488e"
UNIFORM_ROOT="r2:jass-data/runs/home-1044-l3-pure-hard-replay-large-source-v1/20260729T070032Z-477da64d"
UNIFORM_JOB="home-1044-l3-pure-hard-replay-large-source-v1"
UNIFORM_ATTEMPT="20260729T070032Z-477da64d"
UNIFORM_CODE_SHA="477da64da2dea09c8ceb1f1e8e79e2c54d023a5a"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
PY="$VENV/bin/python"; ARM_COUNT=2000000; MAXIT=2000; CHUNK=20000
FIT_TIMEOUT="${JFI_ACTIVE_FIT_TIMEOUT_SECONDS:-86400}"

finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  (cd "$W" && find . -maxdepth 1 -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat "$W"/*.npy "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-jfi-active-fit-v1$ ]] || die "invalid job nomenclature"
[ "${GO_JFI_ACTIVE:-0}" = 1 ] || die "GO JFI ACTIVE missing"
[ "${SELECTION_FROZEN_AUTHORIZED:-0}" = 1 ] || die "selection-frozen authorization missing"
[ "${NO_TARGET_READS_BEFORE_SELECTION_FREEZE:-0}" = 1 ] || die "pre-freeze target guard missing"
[ "${NO_FRESH_OPENINGS:-0}" = 1 ] || die "fresh-opening guard missing"
[ "${NO_STRENGTH_GAMES:-0}" = 1 ] || die "strength-game guard missing"
[ "${NO_SCAN_READS:-0}" = 1 ] || die "Scan-read guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX62 contract mismatch"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "numeric runtime absent"

stage authenticate-completed-target-blind-selection
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$SELECTION_ROOT" \
  --file artefacts/JFI_C_SELECTION_MANIFEST.json=selection-manifest.json \
  --file artefacts/JFI_C_SELECTION_CERTIFICATE.json=selection-certificate.json \
  --file artefacts/JFI_C_ACTIVE_INDICES.npy.gz=active-indices.npy.gz \
  --file artefacts/JFI_C_UNIFORM_INDICES.npy.gz=uniform-indices.npy.gz \
  --file artefacts/JFI_C_ACTIVE_ROW_IDS.npy.gz=active-row-ids.npy.gz \
  --file artefacts/JFI_C_UNIFORM_ROW_IDS.npy.gz=uniform-row-ids.npy.gz \
  --file artefacts/TARGET_READS_TOTAL__0=TARGET_READS_TOTAL__0 \
  --file artefacts/SELECTION_FROZEN=SELECTION_FROZEN \
  --out-dir "$IN" --report "$ART/verified-selection.json" >"$W/fetch-selection.log" 2>&1
"$PY" - "$IN/selection-certificate.json" "$ART/verified-selection.json" \
  "$EXPECTED_SELECTION_JOB" "$EXPECTED_SELECTION_ATTEMPT" "$EXPECTED_SELECTION_CODE_SHA" <<'PY'
import json,sys
cert=json.load(open(sys.argv[1])); verified=json.load(open(sys.argv[2]))
if (verified.get('job_id'),verified.get('attempt_id'),verified.get('code_sha'),verified.get('result_state')) != \
   (sys.argv[3],sys.argv[4],sys.argv[5],'completed'): raise SystemExit('selection result identity drift')
if cert.get('schema')!='jass.jfi.c_selection_certificate.v1': raise SystemExit('selection certificate schema drift')
if cert.get('active_rows')!=2000000 or cert.get('uniform_rows')!=2000000 or not cert.get('active_uniform_disjoint'):
 raise SystemExit('selection count/disjointness drift')
if cert.get('markers')!={'TARGET_READS_BEFORE_SELECTION_FREEZE':0,'TARGET_READS_TOTAL':0,
 'SCAN_READS':0,'FULL_FITS':0,'FRESH_OPENINGS':0,'STRENGTH_GAMES':0}:
 raise SystemExit('selection zero-marker drift')
PY
gunzip -c "$IN/active-indices.npy.gz" >"$W/active-indices.npy"
gunzip -c "$IN/uniform-indices.npy.gz" >"$W/uniform-indices.npy"
gunzip -c "$IN/active-row-ids.npy.gz" >"$W/active-row-ids.npy"
gunzip -c "$IN/uniform-row-ids.npy.gz" >"$W/uniform-row-ids.npy"

stage authenticate-candidate-universe-and-jfi-b
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$BOUNDARY_B_ROOT" \
  --file artefacts/JFI_BOUNDARY_B_FACTS.json=boundary-b.json \
  --file artefacts/JFI_C_CANDIDATE_UNIVERSE.json=candidate-manifest.json \
  --file artefacts/JFI_C_CANDIDATE_10M.jnnw.gz=candidate.jnnw.gz \
  --file artefacts/JFI_C_CANDIDATE_10M.jsm.gz=candidate.jsm.gz \
  --file artefacts/JFI_C_CANDIDATE_ORIGIN.npy.gz=origin.npy.gz \
  --out-dir "$IN" --report "$ART/verified-boundary-b.json" >"$W/fetch-boundary-b.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$AB_ROOT" \
  --file artefacts/JFI_B_FISHER.npy.gz=base-fisher.npy.gz \
  --file artefacts/JFI_B_SELECTED_L2.txt=selected-l2.txt \
  --out-dir "$IN" --report "$ART/verified-jfi-b.json" >"$W/fetch-jfi-b.log" 2>&1
"$PY" - "$IN/boundary-b.json" "$ART/verified-boundary-b.json" \
  "$EXPECTED_BOUNDARY_B_JOB" "$EXPECTED_BOUNDARY_B_ATTEMPT" <<'PY'
import json,sys
facts=json.load(open(sys.argv[1])); verified=json.load(open(sys.argv[2]))
if (verified.get('job_id'),verified.get('attempt_id'),verified.get('result_state')) != \
   (sys.argv[3],sys.argv[4],'completed'): raise SystemExit('Boundary-B result identity drift')
if facts.get('schema')!='jass.jfi.boundary_b_facts.v1' or facts.get('verdict')!='JFI_BOUNDARY_B_READY':
 raise SystemExit('Boundary-B facts drift')
if facts.get('code_sha')!=verified.get('code_sha'): raise SystemExit('Boundary-B code SHA drift')
PY
gunzip -c "$IN/candidate.jnnw.gz" >"$W/candidate.jnnw"
gunzip -c "$IN/candidate.jsm.gz" >"$W/candidate.jsm"
gunzip -c "$IN/origin.npy.gz" >"$W/origin.npy"
gunzip -c "$IN/base-fisher.npy.gz" >"$W/base-fisher.npy"
SELECTED_L2=$(cat "$IN/selected-l2.txt")
"$PY" - "$IN/selection-manifest.json" "$IN/candidate-manifest.json" "$W/base-fisher.npy" \
  "$SELECTED_L2" <<'PY'
import hashlib,json,sys
selection=json.load(open(sys.argv[1])); candidate=sys.argv[2]
sha=lambda p:hashlib.sha256(open(p,'rb').read()).hexdigest()
if (selection.get('inputs') or {}).get('candidate_manifest',{}).get('sha256')!=sha(candidate):
 raise SystemExit('selection candidate-manifest link drift')
if (selection.get('inputs') or {}).get('fisher',{}).get('sha256')!=sha(sys.argv[3]):
 raise SystemExit('selection Fisher link drift')
if float(selection.get('l2',0))!=float(sys.argv[4]): raise SystemExit('selection lambda drift')
PY

stage authenticate-40m-label-source-post-freeze
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$UNIFORM_ROOT" \
  --file artefacts/uniform.jnnw.gz=uniform.jnnw.gz \
  --file artefacts/uniform.jsm.gz=uniform.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-uniform.json" >"$W/fetch-uniform.log" 2>&1
"$PY" - "$ART/verified-uniform.json" "$UNIFORM_JOB" "$UNIFORM_ATTEMPT" "$UNIFORM_CODE_SHA" <<'PY'
import json,sys
v=json.load(open(sys.argv[1]))
if (v.get('job_id'),v.get('attempt_id'),v.get('code_sha'),v.get('result_state')) != \
   (sys.argv[2],sys.argv[3],sys.argv[4],'completed'): raise SystemExit('40M source identity drift')
PY
gunzip -c "$IN/uniform.jnnw.gz" >"$W/uniform.raw.jnnw"
gunzip -c "$IN/uniform.jsm.gz" >"$W/uniform.raw.jsm"

stage reproduce-full-candidate-features
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
timeout 14400s "$W/build/jass" --dump-eval-features "$W/candidate.jnnw" \
  "$W/candidate.feat" >"$W/features.log" 2>&1

stage post-freeze-materialization-with-source-labels
TRAIN_CANDIDATES=$("$PY" - "$IN/candidate-manifest.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['selection']['train_candidates'])
PY
)
env PYTHONPATH=. "$PY" jobs/tools/jfi_active_materialize.py \
  --candidate-data "$W/candidate.jnnw" --candidate-meta "$W/candidate.jsm" \
  --candidate-feat "$W/candidate.feat" --candidate-manifest "$IN/candidate-manifest.json" \
  --origin-indices "$W/origin.npy" --source-data "$W/uniform.raw.jnnw" \
  --source-meta "$W/uniform.raw.jsm" --selection-manifest "$IN/selection-manifest.json" \
  --active-indices "$W/active-indices.npy" --uniform-indices "$W/uniform-indices.npy" \
  --train-count "$TRAIN_CANDIDATES" --reference-data "$W/reference.jnnw" \
  --reference-meta "$W/reference.jsm" --reference-feat "$W/reference.feat" \
  --active-data "$W/active.jnnw" --active-meta "$W/active.jsm" --active-feat "$W/active.feat" \
  --uniform-data "$W/uniform.jnnw" --uniform-meta "$W/uniform.jsm" --uniform-feat "$W/uniform.feat" \
  --manifest "$ART/JFI_C_MATERIALIZATION.json" --production >"$W/materialize.log" 2>&1
DEV_COUNT=$("$PY" - "$ART/JFI_C_MATERIALIZATION.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['counts']['dev_eval'])
PY
)

stage reconstruct-one-common-context30-target
timeout 21600s "$PY" jobs/tools/l3_conditional_targets.py --data "$W/reference.jnnw" \
  --meta "$W/reference.jsm" --feat "$W/reference.feat" --train-count 4000000 \
  --aligned-out "$W/reference-context30.npy" --shuffled-out "$W/reference-shuffled.npy" \
  --report "$ART/JFI_C_COMMON_CONTEXT30.json" --alpha 0.30 >"$W/targets.log" 2>&1
rm -f "$W/reference-shuffled.npy"
"$PY" jobs/tools/jfi_active_targets.py --reference-targets "$W/reference-context30.npy" \
  --arm-count "$ARM_COUNT" --dev-count "$DEV_COUNT" --active-out "$W/active-context30.npy" \
  --uniform-out "$W/uniform-context30.npy" --report "$ART/JFI_C_COMMON_TARGET_SPLIT.json"
gzip -n -c "$W/reference-context30.npy" >"$ART/JFI_C_REFERENCE_CONTEXT30.npy.gz"
gzip -n -c "$W/active-context30.npy" >"$ART/JFI_C_ACTIVE_CONTEXT30.npy.gz"
gzip -n -c "$W/uniform-context30.npy" >"$ART/JFI_C_UNIFORM_CONTEXT30.npy.gz"

fit_arm(){
  local arm="$1"
  stage "fit-$arm"
  /usr/bin/time -f '%e' -o "$W/$arm.seconds" timeout "${FIT_TIMEOUT}s" env \
    JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" PYTHONUNBUFFERED=1 \
    "$PY" pattern_jass/tools/train_stream.py --data "$W/$arm.jnnw" --feat "$W/$arm.feat" \
    --out "$W/$arm.pjtw" --target external --target-values "$W/$arm-context30.npy" \
    --targets-report "$ART/$arm-target-consumption.json" --loss logistic --exact-fold --tempo-stage \
    --holdout-count "$DEV_COUNT" --l2 "$SELECTED_L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
    --lbfgs-maxcor 20 --lbfgs-gtol 1e-4 --prune --init-mode zero \
    --optimizer-report "$ART/$arm-optimizer.json" >"$W/$arm-fit.log" 2>&1
  "$PY" jobs/tools/verify_optimizer_convergence.py --report "$ART/$arm-optimizer.json" \
    --label "$arm" --expected-max-iterations "$MAXIT" --expected-maxcor 20 \
    --expected-gtol 1e-4 --receipt "$ART/$arm-convergence.json"
  gzip -n -c "$W/$arm.pjtw" >"$ART/JFI_C_${arm^^}.pjtw.gz"
}

stage two-sequential-zero-centred-fits
fit_arm active
fit_arm uniform

stage arm-identifiability
for arm in active uniform; do
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
    "$PY" jobs/tools/jfi_patterneval_identifiability.py --data "$W/$arm.jnnw" \
    --feat "$W/$arm.feat" --targets "$W/$arm-context30.npy" --model "$W/$arm.pjtw" \
    --train-count "$ARM_COUNT" --l2 "$SELECTED_L2" --chunk "$CHUNK" \
    --fisher-out "$W/$arm-fisher.npy" --diagnostics-out "$ART/JFI_C_${arm^^}_COORDINATES.npz" \
    --out "$ART/JFI_C_${arm^^}_IDENTIFIABILITY.json" >"$W/$arm-identifiability.log" 2>&1
  gzip -n -c "$W/$arm-fisher.npy" >"$ART/JFI_C_${arm^^}_FISHER.npy.gz"
done

stage frozen-common-dev-gate
set +e
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
  "$PY" jobs/tools/jfi_active_readout.py --active-data "$W/active.jnnw" \
  --active-meta "$W/active.jsm" --active-feat "$W/active.feat" \
  --active-targets "$W/active-context30.npy" --active-model "$W/active.pjtw" \
  --active-identifiability "$ART/JFI_C_ACTIVE_IDENTIFIABILITY.json" \
  --uniform-data "$W/uniform.jnnw" --uniform-meta "$W/uniform.jsm" \
  --uniform-feat "$W/uniform.feat" --uniform-targets "$W/uniform-context30.npy" \
  --uniform-model "$W/uniform.pjtw" \
  --uniform-identifiability "$ART/JFI_C_UNIFORM_IDENTIFIABILITY.json" \
  --train-count "$ARM_COUNT" --bootstrap-samples 100000 --bootstrap-seed 2026120104 \
  --out "$ART/JFI_C_ACTIVE_VS_UNIFORM.json" >"$W/readout.log" 2>&1
READOUT_RC=$?
set -e
[ "$READOUT_RC" -eq 0 ] || [ "$READOUT_RC" -eq 3 ] || die "JFI-C readout technical failure rc=$READOUT_RC"

stage publish-jfi-c-certificate
"$PY" - "$ART/JFI_C_CERTIFICATE.json" "$ART/JFI_C_ACTIVE_VS_UNIFORM.json" \
  "$EXPECTED_CODE_SHA" "$SELECTED_L2" "$DEV_COUNT" "$W/active.seconds" "$W/uniform.seconds" <<'PY'
import json,sys
out,readout,code,l2,dev,active_s,uniform_s=sys.argv[1:]
r=json.load(open(readout)); passed=r['gate']['pass']
payload={'schema':'jass.jfi.c_certificate.v1','code_sha':code,'verdict':r['verdict'],
 'selected_l2':float(l2),'active_train_rows':2000000,'uniform_train_rows':2000000,
 'common_dev_rows':int(dev),'active_fit_seconds':float(open(active_s).read()),
 'uniform_fit_seconds':float(open(uniform_s).read()),
 'markers':{'TARGET_READS_BEFORE_SELECTION_FREEZE':0,'TARGET_READS_AFTER_SELECTION_FREEZE':1,
            'SCAN_READS':0,'FULL_FITS':2,'FRESH_OPENINGS':0,'STRENGTH_GAMES':0,
            'PROMOTION_AUTHORIZED':False},
 'next_stage':'JFI_D_CANDIDATE' if passed else None}
open(out,'w').write(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY
printf '0\n' >"$ART/TARGET_READS_BEFORE_SELECTION_FREEZE__0"
printf '1\n' >"$ART/TARGET_READS_AFTER_SELECTION_FREEZE__1"
printf '0\n' >"$ART/SCAN_READS__0"; printf '2\n' >"$ART/FULL_FITS__2"
printf '0\n' >"$ART/FRESH_OPENINGS__0"; printf '0\n' >"$ART/STRENGTH_GAMES__0"
printf 'FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"
if [ "$READOUT_RC" -eq 0 ]; then
  touch "$ART/VERDICT__JFI_ACTIVE_INFORMATION_GAIN_ESTABLISHED"
  printf 'JFI_D_CANDIDATE\n' >"$ART/NEXT_STAGE__JFI_D_CANDIDATE"
  say "JFI_ACTIVE_INFORMATION_GAIN_ESTABLISHED FULL_FITS=2 STRENGTH_GAMES=0"
else
  touch "$ART/VERDICT__JFI_ACTIVE_INFORMATION_GAIN_NOT_ESTABLISHED"
  say "JFI_ACTIVE_INFORMATION_GAIN_NOT_ESTABLISHED FULL_FITS=2 STOP"
fi
stage complete
