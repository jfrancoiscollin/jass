#!/usr/bin/env bash
# JFI-D: post-freeze ACTIVE_4M materialization, Context30 reconstruction and one
# zero-centred fit. Publishes JASS_NATIVE_ACTIVE_V1; no force or promotion.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${D_SELECTION_ROOT:?}"; : "${EXPECTED_D_SELECTION_JOB:?}"; : "${EXPECTED_D_SELECTION_ATTEMPT:?}"; : "${EXPECTED_D_SELECTION_CODE_SHA:?}"
: "${BOUNDARY_B_ROOT:?}"
: "${JFI_AB_ROOT:?}"; : "${EXPECTED_JFI_AB_JOB:?}"
: "${EXPECTED_JFI_AB_ATTEMPT:?}"; : "${EXPECTED_JFI_AB_CODE_SHA:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"; GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$IN" "$ART" "$GEOM"; RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*"|tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }
AB_ROOT="$JFI_AB_ROOT"; AB_JOB="$EXPECTED_JFI_AB_JOB"
AB_ATTEMPT="$EXPECTED_JFI_AB_ATTEMPT"; AB_CODE_SHA="$EXPECTED_JFI_AB_CODE_SHA"
UNIFORM_ROOT="r2:jass-data/runs/home-1044-l3-pure-hard-replay-large-source-v1/20260729T070032Z-477da64d"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"; PY="$VENV/bin/python"; TRAIN=4000000
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null||true; rm -rf "$W/build" "$IN" "$GEOM" 2>/dev/null||true; rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat "$W"/*.npy "$W"/*.pjtw 2>/dev/null||true; exit "$rc"; }
trap finalize EXIT; trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-jfi-d-active4-fit-v1$ ]] || die "nomenclature mismatch"
[ "${JFI_D_FIT_AUTHORIZED:-0}" = 1 ] && [ "${SELECTION_FROZEN_AUTHORIZED:-0}" = 1 ] || die "JFI-D authorization missing"
[ "${NO_TARGET_READS_BEFORE_SELECTION_FREEZE:-0}" = 1 ] && [ "${NO_SCAN_READS:-0}" = 1 ] || die "read guard missing"
[ "${NO_FRESH_OPENINGS:-0}" = 1 ] && [ "${NO_STRENGTH_GAMES:-0}" = 1 ] && [ "${NO_PROMOTION:-0}" = 1 ] || die "force guard missing"
[ "$AB_ROOT" = "$JASS_OBJSTORE_REMOTE/runs/$AB_JOB/$AB_ATTEMPT" ] || die "JFI-A/B root identity mismatch"
[[ "$AB_JOB" =~ ^cpx62-[0-9]+-l3-jfi-factorial-l2-fit-v1$ ]] || die "JFI-A/B job nomenclature drift"
[[ "$AB_ATTEMPT" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$ ]] || die "JFI-A/B attempt nomenclature drift"
[ "$AB_CODE_SHA" = "25bb488e19bb4bf6e7d696294defaf083142f927" ] || die "JFI-A/B scientific code drift"
[[ "$AB_ATTEMPT" == *"-${AB_CODE_SHA:0:8}" ]] || die "JFI-A/B attempt/code drift"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] && [ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "source drift"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX62 contract mismatch"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "numeric runtime absent"

timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$D_SELECTION_ROOT" \
 --file artefacts/JFI_D_SELECTION_MANIFEST.json=d-selection.json \
 --file artefacts/JFI_D_SELECTION_CERTIFICATE.json=d-certificate.json \
 --file artefacts/JFI_D_ACTIVE4_INDICES.npy.gz=active4-indices.npy.gz \
 --file artefacts/JFI_D_ACTIVE4_ROW_IDS.npy.gz=active4-row-ids.npy.gz \
 --file artefacts/JFI_D_SELECTION_FROZEN=SELECTION_FROZEN \
 --out-dir "$IN" --report "$ART/verified-d-selection.json" >"$W/fetch-selection.log" 2>&1
"$PY" - "$IN/d-certificate.json" "$ART/verified-d-selection.json" "$EXPECTED_D_SELECTION_JOB" \
 "$EXPECTED_D_SELECTION_ATTEMPT" "$EXPECTED_D_SELECTION_CODE_SHA" <<'PY'
import json,sys
c=json.load(open(sys.argv[1])); v=json.load(open(sys.argv[2]))
if (v.get('job_id'),v.get('attempt_id'),v.get('code_sha'),v.get('result_state'))!=(sys.argv[3],sys.argv[4],sys.argv[5],'completed'):
 raise SystemExit('JFI-D selection identity drift')
if c.get('active_rows')!=4000000 or c.get('markers')!={'TARGET_READS_TOTAL':0,'SCAN_READS':0,
 'FULL_FITS':0,'FRESH_OPENINGS':0,'STRENGTH_GAMES':0}:
 raise SystemExit('JFI-D selection certificate drift')
PY
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$BOUNDARY_B_ROOT" \
 --file artefacts/JFI_C_CANDIDATE_UNIVERSE.json=candidate-manifest.json \
 --file artefacts/JFI_C_CANDIDATE_10M.jnnw.gz=candidate.jnnw.gz \
 --file artefacts/JFI_C_CANDIDATE_10M.jsm.gz=candidate.jsm.gz \
 --file artefacts/JFI_C_CANDIDATE_ORIGIN.npy.gz=origin.npy.gz \
 --out-dir "$IN" --report "$ART/verified-candidate.json" >"$W/fetch-candidate.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$AB_ROOT" \
 --file artefacts/JFI_B_FISHER.npy.gz=base-fisher.npy.gz --file artefacts/JFI_B_SELECTED_L2.txt=selected-l2.txt \
 --out-dir "$IN" --report "$ART/verified-jfi-b.json" >"$W/fetch-b.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$UNIFORM_ROOT" \
 --file artefacts/uniform.jnnw.gz=uniform.raw.jnnw.gz --file artefacts/uniform.jsm.gz=uniform.raw.jsm.gz \
 --out-dir "$IN" --report "$ART/verified-source.json" >"$W/fetch-source.log" 2>&1
for name in candidate.jnnw candidate.jsm origin.npy base-fisher.npy uniform.raw.jnnw uniform.raw.jsm active4-indices.npy; do gunzip -c "$IN/$name.gz" >"$W/$name"; done
SELECTED_L2=$(cat "$IN/selected-l2.txt"); CANDIDATE_TRAIN=$("$PY" -c "import json;print(json.load(open('$IN/candidate-manifest.json'))['selection']['train_candidates'])")
"$PY" - "$IN/d-selection.json" "$IN/candidate-manifest.json" "$W/base-fisher.npy" "$SELECTED_L2" <<'PY'
import hashlib,json,sys
d=json.load(open(sys.argv[1])); sha=lambda p:hashlib.sha256(open(p,'rb').read()).hexdigest()
if d['inputs']['candidate_manifest']['sha256']!=sha(sys.argv[2]) or d['inputs']['fisher']['sha256']!=sha(sys.argv[3]):
 raise SystemExit('JFI-D frozen input link drift')
if float(d['l2'])!=float(sys.argv[4]): raise SystemExit('JFI-D lambda drift')
PY
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
timeout 14400s "$W/build/jass" --dump-eval-features "$W/candidate.jnnw" "$W/candidate.feat" >"$W/features.log" 2>&1
env PYTHONPATH=. "$PY" jobs/tools/jfi_active4_materialize.py --candidate-data "$W/candidate.jnnw" \
 --candidate-meta "$W/candidate.jsm" --candidate-feat "$W/candidate.feat" --candidate-manifest "$IN/candidate-manifest.json" \
 --origin-indices "$W/origin.npy" --source-data "$W/uniform.raw.jnnw" --source-meta "$W/uniform.raw.jsm" \
 --selection-manifest "$IN/d-selection.json" --active-indices "$W/active4-indices.npy" --train-count "$CANDIDATE_TRAIN" \
 --out-data "$W/active4.jnnw" --out-meta "$W/active4.jsm" --out-feat "$W/active4.feat" \
 --manifest "$ART/JFI_D_MATERIALIZATION.json" --production >"$W/materialize.log" 2>&1
DEV=$("$PY" -c "import json;print(json.load(open('$ART/JFI_D_MATERIALIZATION.json'))['counts']['dev_eval'])")
timeout 21600s "$PY" jobs/tools/l3_conditional_targets.py --data "$W/active4.jnnw" --meta "$W/active4.jsm" \
 --feat "$W/active4.feat" --train-count "$TRAIN" --aligned-out "$W/active4-context30.npy" \
 --shuffled-out "$W/shuffled.npy" --report "$ART/JFI_D_CONTEXT30.json" --alpha 0.30 >"$W/targets.log" 2>&1
rm -f "$W/shuffled.npy"; gzip -n -c "$W/active4-context30.npy" >"$ART/JFI_D_CONTEXT30.npy.gz"
/usr/bin/time -f '%e' -o "$W/fit.seconds" timeout 86400s env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
 "$PY" pattern_jass/tools/train_stream.py --data "$W/active4.jnnw" --feat "$W/active4.feat" --out "$W/JASS_NATIVE_ACTIVE_V1.pjtw" \
 --target external --target-values "$W/active4-context30.npy" --targets-report "$ART/JFI_D_TARGET_CONSUMPTION.json" \
 --loss logistic --exact-fold --tempo-stage --holdout-count "$DEV" --l2 "$SELECTED_L2" --max-iter 2000 --chunk 20000 \
 --lbfgs-maxcor 20 --lbfgs-gtol 1e-4 --prune --init-mode zero --optimizer-report "$ART/JFI_D_OPTIMIZER.json" >"$W/fit.log" 2>&1
"$PY" jobs/tools/verify_optimizer_convergence.py --report "$ART/JFI_D_OPTIMIZER.json" --label JFI_D \
 --expected-max-iterations 2000 --expected-maxcor 20 --expected-gtol 1e-4 --receipt "$ART/JFI_D_CONVERGENCE.json"
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" "$PY" jobs/tools/jfi_patterneval_identifiability.py \
 --data "$W/active4.jnnw" --feat "$W/active4.feat" --targets "$W/active4-context30.npy" \
 --model "$W/JASS_NATIVE_ACTIVE_V1.pjtw" --train-count "$TRAIN" --l2 "$SELECTED_L2" --chunk 20000 \
 --fisher-out "$W/d-fisher.npy" --diagnostics-out "$ART/JFI_D_COORDINATES.npz" --out "$ART/JFI_D_IDENTIFIABILITY.json" >"$W/ident.log" 2>&1
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" "$PY" jobs/tools/jfi_d_readout.py \
 --data "$W/active4.jnnw" --meta "$W/active4.jsm" --feat "$W/active4.feat" --targets "$W/active4-context30.npy" \
 --model "$W/JASS_NATIVE_ACTIVE_V1.pjtw" --identifiability "$ART/JFI_D_IDENTIFIABILITY.json" --train-count "$TRAIN" \
 --out "$ART/JFI_D_CANDIDATE_MANIFEST.json" >"$W/readout.log" 2>&1
gzip -n -c "$W/JASS_NATIVE_ACTIVE_V1.pjtw" >"$ART/JASS_NATIVE_ACTIVE_V1.pjtw.gz"; gzip -n -c "$W/d-fisher.npy" >"$ART/JFI_D_FISHER.npy.gz"
printf '1\n' >"$ART/FULL_FITS__1"; printf '0\n' >"$ART/SCAN_READS__0"; printf '0\n' >"$ART/STRENGTH_GAMES__0"; printf '0\n' >"$ART/FRESH_OPENINGS__0"
printf 'FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"; printf 'BOUNDARY C\n' >"$ART/NEXT_BOUNDARY__BOUNDARY_C"
touch "$ART/VERDICT__JFI_D_JASS_NATIVE_ACTIVE_V1_FROZEN"
say "JFI_D_JASS_NATIVE_ACTIVE_V1_FROZEN FULL_FITS=1 STRENGTH_GAMES=0 NEXT_BOUNDARY=BOUNDARY_C"
