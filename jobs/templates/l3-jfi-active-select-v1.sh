#!/usr/bin/env bash
# JFI-C target-blind full selector. Publishes immutable ACTIVE/UNIFORM row-ID
# manifests in a completed result before any Context30/terminal target access.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${BOUNDARY_B_ROOT:?}"; : "${EXPECTED_BOUNDARY_B_JOB:?}"; : "${EXPECTED_BOUNDARY_B_ATTEMPT:?}"
: "${JFI_AB_ROOT:?}"; : "${EXPECTED_JFI_AB_JOB:?}"
: "${EXPECTED_JFI_AB_ATTEMPT:?}"; : "${EXPECTED_JFI_AB_CODE_SHA:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"; mkdir -p "$W" "$IN" "$ART" "$GEOM"
RES="$W/RESULTS.txt"; STAGE="$W/.stage"; : >"$RES"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

AB_ROOT="$JFI_AB_ROOT"; AB_JOB="$EXPECTED_JFI_AB_JOB"
AB_ATTEMPT="$EXPECTED_JFI_AB_ATTEMPT"; AB_CODE_SHA="$EXPECTED_JFI_AB_CODE_SHA"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
PY="$VENV/bin/python"; COUNT=2000000; TIE_SEED=2026120103

finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  (cd "$W" && find . -maxdepth 1 -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat "$W"/*.npy 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-jfi-active-select-v1$ ]] || die "invalid job nomenclature"
[ "${GO_JFI_ACTIVE:-0}" = 1 ] || die "GO JFI ACTIVE missing"
[ "${POST_BOUNDARY_B_AUTHORIZED:-0}" = 1 ] || die "post-Boundary-B authorization missing"
[ "${NO_TARGET_READS_BEFORE_SELECTION_FREEZE:-0}" = 1 ] || die "target-read guard missing"
[ "${NO_FULL_FITS:-0}" = 1 ] || die "full-fit guard missing"
[ "${NO_FRESH_OPENINGS:-0}" = 1 ] || die "fresh-opening guard missing"
[ "${NO_STRENGTH_GAMES:-0}" = 1 ] || die "strength-game guard missing"
[ "${NO_SCAN_READS:-0}" = 1 ] || die "Scan-read guard missing"
[ "$AB_ROOT" = "$JASS_OBJSTORE_REMOTE/runs/$AB_JOB/$AB_ATTEMPT" ] || die "JFI-A/B root identity mismatch"
[[ "$AB_JOB" =~ ^cpx62-[0-9]+-l3-jfi-factorial-l2-fit-v1$ ]] || die "JFI-A/B job nomenclature drift"
[[ "$AB_ATTEMPT" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$ ]] || die "JFI-A/B attempt nomenclature drift"
[ "$AB_CODE_SHA" = "25bb488e19bb4bf6e7d696294defaf083142f927" ] || die "JFI-A/B scientific code drift"
[[ "$AB_ATTEMPT" == *"-${AB_CODE_SHA:0:8}" ]] || die "JFI-A/B attempt/code drift"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX62 contract mismatch"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "numeric runtime absent"

stage authenticate-post-facts-boundary-b
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$BOUNDARY_B_ROOT" \
  --file artefacts/JFI_BOUNDARY_B_FACTS.json=boundary-b.json \
  --file artefacts/JFI_C_CANDIDATE_UNIVERSE.json=candidate-manifest.json \
  --file artefacts/JFI_C_CANDIDATE_10M.jnnw.gz=candidate.jnnw.gz \
  --file artefacts/JFI_C_CANDIDATE_10M.jsm.gz=candidate.jsm.gz \
  --file artefacts/JFI_C_CANDIDATE_ORIGIN.npy.gz=origin.npy.gz \
  --file artefacts/JFI_C_CANDIDATE_ROLES.npy.gz=roles.npy.gz \
  --file artefacts/NEXT_BOUNDARY__GO_JFI_ACTIVE=NEXT_BOUNDARY__GO_JFI_ACTIVE \
  --file artefacts/TARGET_READS_BEFORE_SELECTION_FREEZE__0=TARGET_READS_BEFORE_SELECTION_FREEZE__0 \
  --out-dir "$IN" --report "$ART/verified-boundary-b.json" >"$W/fetch-boundary-b.log" 2>&1
"$PY" - "$IN/boundary-b.json" "$ART/verified-boundary-b.json" \
  "$EXPECTED_CODE_SHA" "$EXPECTED_BOUNDARY_B_JOB" "$EXPECTED_BOUNDARY_B_ATTEMPT" <<'PY'
import json,sys
facts=json.load(open(sys.argv[1])); verified=json.load(open(sys.argv[2]))
if facts.get('schema')!='jass.jfi.boundary_b_facts.v1' or facts.get('verdict')!='JFI_BOUNDARY_B_READY':
 raise SystemExit('Boundary-B verdict drift')
if facts.get('code_sha')!=sys.argv[3] or facts.get('next_boundary')!='GO JFI ACTIVE':
 raise SystemExit('Boundary-B code/next-boundary drift')
if (verified.get('job_id'),verified.get('attempt_id'),verified.get('result_state')) != \
   (sys.argv[4],sys.argv[5],'completed'): raise SystemExit('Boundary-B result identity drift')
expected={'JFI_C_FULL_FITS':0,'TARGET_READS_BEFORE_SELECTION_FREEZE':0,'FRESH_OPENINGS':0,
          'STRENGTH_GAMES':0,'SCIENTIFIC_DECISION':False,'SCAN_READS':0}
if facts.get('markers')!=expected: raise SystemExit('Boundary-B zero-marker drift')
if (facts.get('candidate_universe') or {}).get('records')!=10000000:
 raise SystemExit('Boundary-B candidate count drift')
PY
gunzip -c "$IN/candidate.jnnw.gz" >"$W/candidate.jnnw"
gunzip -c "$IN/candidate.jsm.gz" >"$W/candidate.jsm"
gunzip -c "$IN/origin.npy.gz" >"$W/origin.npy"
gunzip -c "$IN/roles.npy.gz" >"$W/roles.npy"

stage authenticate-frozen-fisher-and-lambda
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$AB_ROOT" \
  --file artefacts/JFI_B_FISHER.npy.gz=fisher.npy.gz \
  --file artefacts/JFI_B_SELECTED_L2.txt=selected-l2.txt \
  --out-dir "$IN" --report "$ART/verified-jfi-b.json" >"$W/fetch-jfi-b.log" 2>&1
gunzip -c "$IN/fisher.npy.gz" >"$W/fisher.npy"
SELECTED_L2=$(cat "$IN/selected-l2.txt")
TRAIN_CANDIDATES=$("$PY" - "$IN/candidate-manifest.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); print(d['selection']['train_candidates'])
PY
)

stage full-candidate-feature-dump
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
/usr/bin/time -f '%e' -o "$W/features.seconds" timeout 14400s \
  "$W/build/jass" --dump-eval-features "$W/candidate.jnnw" "$W/candidate.feat" >"$W/features.log" 2>&1

stage full-target-blind-active-uniform-selection
/usr/bin/time -f '%e' -o "$W/selector.seconds" timeout 21600s env \
  JASS_PATTERNS_DIR="$GEOM" PYTHONPATH=".:$GEOM:pattern_jass/tools" \
  "$PY" jobs/tools/jfi_active_select_stream.py --data "$W/candidate.jnnw" \
  --feat "$W/candidate.feat" --candidate-manifest "$IN/candidate-manifest.json" \
  --origin-indices "$W/origin.npy" --roles "$W/roles.npy" --fisher "$W/fisher.npy" \
  --l2 "$SELECTED_L2" --train-count "$TRAIN_CANDIDATES" --count "$COUNT" \
  --tie-seed "$TIE_SEED" --active-indices-out "$W/active-indices.npy" \
  --uniform-indices-out "$W/uniform-indices.npy" \
  --active-row-ids-out "$W/active-row-ids.npy" \
  --uniform-row-ids-out "$W/uniform-row-ids.npy" \
  --manifest "$ART/JFI_C_SELECTION_MANIFEST.json" >"$W/selector.log" 2>&1

stage publish-immutable-selection-result
gzip -n -c "$W/active-indices.npy" >"$ART/JFI_C_ACTIVE_INDICES.npy.gz"
gzip -n -c "$W/uniform-indices.npy" >"$ART/JFI_C_UNIFORM_INDICES.npy.gz"
gzip -n -c "$W/active-row-ids.npy" >"$ART/JFI_C_ACTIVE_ROW_IDS.npy.gz"
gzip -n -c "$W/uniform-row-ids.npy" >"$ART/JFI_C_UNIFORM_ROW_IDS.npy.gz"
"$PY" - "$ART/JFI_C_SELECTION_CERTIFICATE.json" "$ART/JFI_C_SELECTION_MANIFEST.json" \
  "$EXPECTED_CODE_SHA" "$W/features.seconds" "$W/selector.seconds" <<'PY'
import hashlib,json,sys
out,manifest,code,features,selector=sys.argv[1:]
d=json.load(open(manifest)); sha=lambda p:hashlib.sha256(open(p,'rb').read()).hexdigest()
if d.get('active_rows')!=2000000 or d.get('uniform_rows')!=2000000 or not d.get('active_uniform_disjoint'):
 raise SystemExit('selection count/disjointness drift')
payload={'schema':'jass.jfi.c_selection_certificate.v1','code_sha':code,
 'selection_manifest_sha256':sha(manifest),'candidate_rows':d['candidate_rows'],
 'canonical_unique_rows':d['canonical_unique_rows'],'active_rows':d['active_rows'],
 'uniform_rows':d['uniform_rows'],'active_uniform_disjoint':True,'dev_excluded':d['dev_excluded'],
 'feature_dump_seconds':float(open(features).read()),'selector_seconds':float(open(selector).read()),
 'markers':{'TARGET_READS_BEFORE_SELECTION_FREEZE':0,'TARGET_READS_TOTAL':0,
            'SCAN_READS':0,'FULL_FITS':0,'FRESH_OPENINGS':0,'STRENGTH_GAMES':0}}
open(out,'w').write(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY
printf '0\n' >"$ART/TARGET_READS_BEFORE_SELECTION_FREEZE__0"
printf '0\n' >"$ART/TARGET_READS_TOTAL__0"; printf '0\n' >"$ART/SCAN_READS__0"
printf '0\n' >"$ART/FULL_FITS__0"; printf '0\n' >"$ART/FRESH_OPENINGS__0"
printf '0\n' >"$ART/STRENGTH_GAMES__0"; touch "$ART/SELECTION_FROZEN"
stage complete
say "JFI_C_SELECTION_FROZEN ACTIVE=2000000 UNIFORM=2000000 TARGET_READS_TOTAL=0 SCAN_READS=0 FULL_FITS=0"
