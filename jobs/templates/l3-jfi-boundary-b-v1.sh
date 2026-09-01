#!/usr/bin/env bash
# JFI Boundary B: authenticate A/B and Jass-only 40M, freeze the exact 10M
# zero-label universe, then run one bounded 20k selector timing probe. No arm
# selection, target reconstruction, full fit, fresh opening, game or Scan read.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"; mkdir -p "$W" "$IN" "$ART" "$GEOM"
RES="$W/RESULTS.txt"; STAGE="$W/.stage"; : >"$RES"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

AB_ROOT="r2:jass-data/runs/cpx62-1749-l3-jfi-factorial-l2-fit-v1/20260901T225526Z-25bb488e"
AB_JOB="cpx62-1749-l3-jfi-factorial-l2-fit-v1"
AB_ATTEMPT="20260901T225526Z-25bb488e"
AB_CODE_SHA="25bb488e19bb4bf6e7d696294defaf083142f927"
BOUNDARY_A_ROOT="r2:jass-data/runs/cpx62-1747-l3-jfi-boundary-a-v1/20260901T223356Z-25bb488e"
UNIFORM_ROOT="r2:jass-data/runs/home-1044-l3-pure-hard-replay-large-source-v1/20260729T070032Z-477da64d"
UNIFORM_JOB="home-1044-l3-pure-hard-replay-large-source-v1"
UNIFORM_ATTEMPT="20260729T070032Z-477da64d"
UNIFORM_CODE_SHA="477da64da2dea09c8ceb1f1e8e79e2c54d023a5a"
SOURCE_RECORDS=40000000; CANDIDATE_RECORDS=10000000; SIZER_RECORDS=20000
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
PY="$VENV/bin/python"

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
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-jfi-boundary-b-v1$ ]] || die "invalid job nomenclature"
[ "${BOUNDARY_B_APPROVED:-0}" = 1 ] || die "Boundary B authorization missing"
[ "${NO_JFI_C_FULL_FITS:-0}" = 1 ] || die "NO_JFI_C_FULL_FITS guard missing"
[ "${NO_TARGET_READS_BEFORE_SELECTION_FREEZE:-0}" = 1 ] || die "target-read guard missing"
[ "${NO_FRESH_OPENINGS:-0}" = 1 ] || die "fresh-opening guard missing"
[ "${NO_STRENGTH_GAMES:-0}" = 1 ] || die "strength-game guard missing"
[ "${NO_SCAN_READS:-0}" = 1 ] || die "Scan-read guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX62 contract mismatch"
CPU_MODEL=$(lscpu | awk -F: '/^Model name:/{sub(/^[[:space:]]+/,"",$2);print $2}')
ISA_FLAGS=$(lscpu | awk -F: '/^Flags:/{sub(/^[[:space:]]+/,"",$2);print $2}')
[[ " $ISA_FLAGS " == *" avx2 "* ]] && [[ " $ISA_FLAGS " == *" bmi2 "* ]] || die "AVX2/BMI2 absent"
export CPU_MODEL ISA_FLAGS
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "numeric runtime absent"
"$PY" -c 'import numpy,scipy; assert numpy.__version__ and scipy.__version__'

stage authenticate-jfi-a-b
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$AB_ROOT" \
  --file artefacts/JFI_A_B_CERTIFICATE.json=ab-certificate.json \
  --file artefacts/JFI_A_PATH_INDEPENDENCE.json=path.json \
  --file artefacts/JFI_B_L2_CURVE.json=l2.json \
  --file artefacts/JFI_B_SELECTED_L2.txt=selected-l2.txt \
  --file artefacts/JFI_B_IDENTIFIABILITY.json=identifiability.json \
  --file artefacts/JFI_B_FISHER.npy.gz=fisher.npy.gz \
  --file artefacts/NEXT_BOUNDARY__GO_JFI_ACTIVE=NEXT_BOUNDARY__GO_JFI_ACTIVE \
  --out-dir "$IN" --report "$ART/verified-jfi-a-b.json" >"$W/fetch-ab.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$BOUNDARY_A_ROOT" \
  --file artefacts/JFI_BOUNDARY_A_FACTS.json=boundary-a.json \
  --out-dir "$IN" --report "$ART/verified-boundary-a.json" >"$W/fetch-boundary-a.log" 2>&1
gunzip -c "$IN/fisher.npy.gz" >"$W/fisher.npy"
"$PY" - "$IN" "$ART/verified-jfi-a-b.json" "$AB_JOB" "$AB_ATTEMPT" "$AB_CODE_SHA" <<'PY'
import json,sys
root,verified,job,attempt,code=sys.argv[1:]
load=lambda name:json.load(open(f'{root}/{name}'))
v=json.load(open(verified)); cert=load('ab-certificate.json'); path=load('path.json')
l2=load('l2.json'); ident=load('identifiability.json')
if (v.get('job_id'),v.get('attempt_id'),v.get('code_sha'),v.get('result_state'))!=(job,attempt,code,'completed'):
 raise SystemExit('JFI-A/B result identity drift')
if path.get('verdict')!='JFI_OPTIMIZER_PATH_INDEPENDENCE_ESTABLISHED':
 raise SystemExit('optimizer path gate did not pass')
if cert.get('full_fits')!=7 or cert.get('path_verdict')!=path['verdict']:
 raise SystemExit('JFI-A/B certificate drift')
selected=float(open(f'{root}/selected-l2.txt').read())
if selected not in (1e-6,1e-5,1e-4) or l2.get('selected_l2')!=selected or ident.get('selected_l2')!=selected:
 raise SystemExit('selected positive lambda drift')
if cert.get('selected_l2')!=selected or not cert.get('identifiability_published'):
 raise SystemExit('JFI-B publication drift')
if cert.get('markers')!={'FULL_FITS':7,'FRESH_OPENINGS':0,'STRENGTH_GAMES':0,
 'SCAN_WEIGHT_READS':0,'SCAN_SCORE_READS':0,'SCAN_TARGET_READS':0,'PROMOTION_AUTHORIZED':False}:
 raise SystemExit('JFI-A/B markers drift')
PY

stage authenticate-jass-only-40m
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$UNIFORM_ROOT" \
  --file artefacts/uniform.jnnw.gz=uniform.jnnw.gz \
  --file artefacts/uniform.jsm.gz=uniform.jsm.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=uniform-summary.json \
  --out-dir "$IN" --report "$ART/verified-uniform.json" >"$W/fetch-uniform.log" 2>&1
read -r SOURCE_DATA_SHA SOURCE_META_SHA < <("$PY" - "$IN/uniform-summary.json" \
  "$ART/verified-uniform.json" "$UNIFORM_JOB" "$UNIFORM_ATTEMPT" "$UNIFORM_CODE_SHA" "$SOURCE_RECORDS" <<'PY'
import json,sys
summary=json.load(open(sys.argv[1])); verified=json.load(open(sys.argv[2])); records=int(sys.argv[6])
if (verified.get('job_id'),verified.get('attempt_id'),verified.get('code_sha'),verified.get('result_state')) != \
   (sys.argv[3],sys.argv[4],sys.argv[5],'completed'): raise SystemExit('40M result identity drift')
arm=(summary.get('arms') or {}).get('uniform') or {}; policy=summary.get('policy') or {}
if summary.get('verdict')!='L3_PURE_HARD_REPLAY_LARGE_SOURCE_READY' or summary.get('external_teacher_inputs')!=0:
 raise SystemExit('40M is not authenticated Jass-only source')
if policy.get('name')!='uniform' or arm.get('records')!=records or (arm.get('generation') or {}).get('topk_ranked_plies')!=0:
 raise SystemExit('40M source policy/count drift')
data,meta=arm.get('data_raw_sha256'),arm.get('meta_raw_sha256')
if not all(isinstance(x,str) and len(x)==64 for x in (data,meta)): raise SystemExit('40M raw hashes absent')
print(data,meta)
PY
)
gunzip -c "$IN/uniform.jnnw.gz" >"$W/uniform.raw.jnnw"
gunzip -c "$IN/uniform.jsm.gz" >"$W/uniform.raw.jsm"
[ "$(sha256sum "$W/uniform.raw.jnnw"|awk '{print $1}')" = "$SOURCE_DATA_SHA" ] || die "40M data SHA drift"
[ "$(sha256sum "$W/uniform.raw.jsm"|awk '{print $1}')" = "$SOURCE_META_SHA" ] || die "40M meta SHA drift"

stage freeze-exact-target-blind-10m-universe
/usr/bin/time -f '%e' -o "$W/candidate.seconds" timeout 7200s "$PY" \
  jobs/tools/jfi_candidate_universe.py --data "$W/uniform.raw.jnnw" --meta "$W/uniform.raw.jsm" \
  --expected-data-sha "$SOURCE_DATA_SHA" --expected-meta-sha "$SOURCE_META_SHA" \
  --records "$CANDIDATE_RECORDS" --split-seed 2026120102 --dev-mod 10 \
  --out-data "$W/candidate.jnnw" --out-meta "$W/candidate.jsm" \
  --origin-indices-out "$W/origin.npy" --roles-out "$W/roles.npy" \
  --manifest "$ART/JFI_C_CANDIDATE_UNIVERSE.json" >"$W/candidate.log" 2>&1
gzip -n -c "$W/candidate.jnnw" >"$ART/JFI_C_CANDIDATE_10M.jnnw.gz"
gzip -n -c "$W/candidate.jsm" >"$ART/JFI_C_CANDIDATE_10M.jsm.gz"
gzip -n -c "$W/origin.npy" >"$ART/JFI_C_CANDIDATE_ORIGIN.npy.gz"
gzip -n -c "$W/roles.npy" >"$ART/JFI_C_CANDIDATE_ROLES.npy.gz"

stage bounded-20k-selector-sizer
"$PY" jobs/tools/jfi_candidate_prefix.py --data "$W/candidate.jnnw" \
  --origin-indices "$W/origin.npy" --records "$SIZER_RECORDS" \
  --out-data "$W/sizer.jnnw" --out-origin-indices "$W/sizer-origin.npy" \
  --report "$ART/JFI_C_SELECTOR_PREFIX.json"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
/usr/bin/time -f '%e' -o "$W/features.seconds" timeout 1800s \
  "$W/build/jass" --dump-eval-features "$W/sizer.jnnw" "$W/sizer.feat" >"$W/features.log" 2>&1
TRAIN_CANDIDATES=$("$PY" - "$ART/JFI_C_CANDIDATE_UNIVERSE.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['selection']['train_candidates'])
PY
)
SELECTED_L2=$(cat "$IN/selected-l2.txt")
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH=".:$GEOM:pattern_jass/tools" \
  "$PY" jobs/tools/jfi_active_selector_sizer.py --data "$W/sizer.jnnw" \
  --feat "$W/sizer.feat" --origin-indices "$W/sizer-origin.npy" \
  --fisher "$W/fisher.npy" --l2 "$SELECTED_L2" --full-train-candidates "$TRAIN_CANDIDATES" \
  --out "$ART/JFI_C_SELECTOR_SIZER.json" >"$W/selector-sizer.log" 2>&1

stage publish-boundary-b-facts
"$PY" - "$ART/JFI_BOUNDARY_B_INPUT.json" "$EXPECTED_CODE_SHA" "$ART" "$IN" "$W" \
  "$SOURCE_DATA_SHA" "$SOURCE_META_SHA" "$AB_JOB" "$AB_ATTEMPT" "$AB_CODE_SHA" <<'PY'
import hashlib,json,os,platform,sys
out,code,art,inputs,work,data_sha,meta_sha,ab_job,ab_attempt,ab_code=sys.argv[1:]
load=lambda path:json.load(open(path)); artp=lambda name:f'{art}/{name}'
candidate=load(artp('JFI_C_CANDIDATE_UNIVERSE.json')); sizer=load(artp('JFI_C_SELECTOR_SIZER.json'))
ident=load(f'{inputs}/identifiability.json'); path=load(f'{inputs}/path.json')
cert=load(f'{inputs}/ab-certificate.json'); boundary_a=load(f'{inputs}/boundary-a.json')
stat=os.statvfs(work); selected=float(open(f'{inputs}/selected-l2.txt').read())
payload={'schema':'jass.jfi.boundary_b_input.v1','code_sha':code,
 'machine':{'host':platform.node(),'nproc':os.cpu_count(),'cpu_model':os.environ['CPU_MODEL'],
            'isa_flags':os.environ['ISA_FLAGS'],'avx2':True,'bmi2':True,'native_build':True},
 'numeric_env':{k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')},
 'disk':{'scratch_path':work,'scratch_free_bytes':stat.f_bavail*stat.f_frsize},
 'jfi_a_b':{'job_id':ab_job,'attempt_id':ab_attempt,'code_sha':ab_code,'full_fits':cert['full_fits'],
            'path_verdict':path['verdict'],'selected_l2':selected,
            'identifiability':{k:ident[k] for k in ('selected_l2','coordinates','effective_df','class_counts',
                                                    'fisher_quantiles','posterior_variance_proxy_quantiles')}},
 'source_40m':{'root':'r2:jass-data/runs/home-1044-l3-pure-hard-replay-large-source-v1/20260729T070032Z-477da64d',
               'records':40000000,'external_teacher_inputs':0,'data_sha256':data_sha,'meta_sha256':meta_sha},
 'candidate_universe':{'records':candidate['selection']['records'],
   'train_candidates':candidate['selection']['train_candidates'],'dev_eval':candidate['selection']['dev_eval'],
   'manifest_sha256':hashlib.sha256(open(artp('JFI_C_CANDIDATE_UNIVERSE.json'),'rb').read()).hexdigest(),
   'construction_seconds':float(open(f'{work}/candidate.seconds').read()),'target_reads':0,'scan_reads':0},
 'selector_sizer':sizer,
 'fit_projection':{'source':'Boundary A conservative 2000-iteration projection',
   'per_arm_seconds':boundary_a['sizer']['projected_seconds_per_2000_iteration_arm'],
   'two_arm_seconds':2*boundary_a['sizer']['projected_seconds_per_2000_iteration_arm'],
   'per_arm_timeout_seconds':86400},
 'feature_sizer':{'rows':20000,'seconds':float(open(f'{work}/features.seconds').read())},
 'markers':{'JFI_C_FULL_FITS':0,'TARGET_READS_BEFORE_SELECTION_FREEZE':0,
            'FRESH_OPENINGS':0,'STRENGTH_GAMES':0,'SCIENTIFIC_DECISION':False,'SCAN_READS':0}}
open(out,'w').write(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY
"$PY" jobs/tools/jfi_boundary_b.py --input "$ART/JFI_BOUNDARY_B_INPUT.json" \
  --out "$ART/JFI_BOUNDARY_B_FACTS.json" | tee -a "$RES"
printf '0\n' >"$ART/JFI_C_FULL_FITS__0"
printf '0\n' >"$ART/TARGET_READS_BEFORE_SELECTION_FREEZE__0"
printf '0\n' >"$ART/FRESH_OPENINGS__0"; printf '0\n' >"$ART/STRENGTH_GAMES__0"
printf '0\n' >"$ART/SCAN_READS__0"; printf 'FALSE\n' >"$ART/SCIENTIFIC_DECISION__FALSE"
printf 'GO JFI ACTIVE\n' >"$ART/NEXT_BOUNDARY__GO_JFI_ACTIVE"
stage complete
say "JFI_BOUNDARY_B_READY CANDIDATE_RECORDS=10000000 JFI_C_FULL_FITS=0 TARGET_READS_BEFORE_SELECTION_FREEZE=0 SCAN_READS=0 NEXT_BOUNDARY=GO_JFI_ACTIVE"
