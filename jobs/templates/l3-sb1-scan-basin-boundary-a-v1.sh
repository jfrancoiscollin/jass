#!/usr/bin/env bash
# SB1 Boundary A only: authenticate frozen inputs, read-only audit, feature timing,
# and bounded consumed-data optimizer sizing. Never runs either full A/B fit.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$IN" "$ART" "$GEOM"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

PREREG_MERGE_SHA="b43645ede4a10192dcc9b68d20b08613ff7a30ec"
ABC_ROOT="r2:jass-data/runs/cpx62-1340-jass-megacorpus-comparative-fit-v1/20260814T123246Z-2ce07222"
ABC_JOB="cpx62-1340-jass-megacorpus-comparative-fit-v1"
ABC_ATTEMPT="20260814T123246Z-2ce07222"
ABC_CODE="2ce07222f86c1468a1081fbdc53e9e17a0c5326e"
CURRICULUM_ROOT="r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/20260814T191555Z-18c38a33"
CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
TURNOVER_ROOT="r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984"
TURNOVER_JOB="home-0977-l3-pure-turnover1to1-train-v1"
TURNOVER_ATTEMPT="20260726T071254Z-336bb984"
TURNOVER_CORPUS_SHA="9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
TURNOVER_META_SHA="acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
SCAN_ROOT="r2:jass-data/runs/home-0957-l3-pure-m1-scan-gap-causal-v1/20260725T104131Z-ebf919fe"
SCAN_JOB="home-0957-l3-pure-m1-scan-gap-causal-v1"
SCAN_ATTEMPT="20260725T104131Z-ebf919fe"
SCAN_EVAL_SHA="0e7161c38af605f5e367f3f8fe17525d1c40db722714c68921971b386e58abba"
HOLDOUT_MOD=10; SPLIT_SEED=577215; EXPECTED_RECORDS=2000000; EXPECTED_EXTRAS=120
SIZER_RECORDS=100000; SIZER_HOLDOUT=10000; SIZER_MAXIT=3; CHUNK=20000
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
VENV_READY="$VENV/.jass-runtime-ready-v1"

MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR"|awk 'NR==2{print $4}')"
      } >"$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120
    done ) & MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -maxdepth 1 -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat "$W"/*.npy "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-([0-9]+)-l3-sb1-scan-basin-boundary-a-v1$ ]] || die "invalid SB1 Boundary-A job nomenclature"
[ "${BOUNDARY_A_APPROVED:-0}" = 1 ] || die "Boundary A authorization missing"
[ "${NO_FULL_FITS:-0}" = 1 ] || die "NO_FULL_FITS guard missing"
[ "${NO_FRESH_FORCE:-0}" = 1 ] || die "NO_FRESH_FORCE guard missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX62 16-CPU contract mismatch"
FREE_MB=$(df -Pm "$JASS_RESULT_DIR"|awk 'NR==2{print $4}')
[ "${FREE_MB:-0}" -gt 20480 ] || die "less than 20 GiB free"
[ -f "$VENV_READY" ] || die "persistent numeric runtime absent"
PY="$VENV/bin/python"
"$PY" -c 'import numpy,scipy; assert numpy.__version__ and scipy.__version__' || die "numeric runtime invalid"
monitor

stage machine-and-scope
{
  echo "hostname=$(hostname)"; echo "nproc=$(nproc)"; echo "disk_free_mb=$FREE_MB"
  echo "kernel=$(uname -srvmo)"; echo "cpu_model=$(lscpu|awk -F: '/Model name/{gsub(/^[ \t]+/,"",$2);print $2;exit}')"
  echo "isa_flags=$(lscpu|awk -F: '/Flags/{gsub(/^[ \t]+/,"",$2);print $2;exit}')"
  echo "hotpath=shared_feature_dump_plus_train_stream_lbfgs_chunked"
} >"$ART/machine.txt"
python3 jobs/tools/sb1_scope_guard.py --base "$PREREG_MERGE_SHA" --head HEAD --out "$ART/scope-guard.json" >"$W/scope.log" 2>&1
python3 -m py_compile jobs/tools/sb1_weight_audit.py jobs/tools/sb1_fit_contract.py jobs/tools/sb1_subset.py jobs/tools/sb1_scope_guard.py
"$PY" -m unittest jobs.tests.test_l3_scan_weight_basin_prior >"$W/tests.log" 2>&1

stage fetch-authenticate-immutable-inputs
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$ABC_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=abc-summary.json \
  --file artefacts/mega_full_4m.pjtw.gz=C.pjtw.gz \
  --file artefacts/current_2m-context30.npy.gz=current-context30.npy.gz \
  --file artefacts/current_2m-manifest.json=current-manifest.json \
  --file artefacts/current_2m-conditional-targets.json=current-targets.json \
  --out-dir "$IN" --report "$ART/verified-abc.json" >"$W/fetch-abc.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=CURRICULUM.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" >"$W/fetch-curriculum.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_ROOT" \
  --file artefacts/turnover1to1.jnnw.gz=turnover.jnnw.gz \
  --file artefacts/turnover1to1.jsm.gz=turnover.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-turnover.json" >"$W/fetch-turnover.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$SCAN_ROOT" \
  --file artefacts/scan-exact-8cf.pjtw.gz=SCAN_EXACT.pjtw.gz \
  --file artefacts/scan-exact-port-manifest.json=scan-port.json \
  --file artefacts/scan-static-parity.json=scan-parity.json \
  --out-dir "$IN" --report "$ART/verified-scan.json" >"$W/fetch-scan.log" 2>&1

gunzip -c "$IN/C.pjtw.gz" >"$W/C.pjtw"
gunzip -c "$IN/CURRICULUM.pjtw.gz" >"$W/CURRICULUM.pjtw"
gunzip -c "$IN/SCAN_EXACT.pjtw.gz" >"$W/SCAN_EXACT.pjtw"
gunzip -c "$IN/current-context30.npy.gz" >"$W/current-context30.npy"
gunzip -c "$IN/turnover.jnnw.gz" >"$W/turnover.raw.jnnw"
gunzip -c "$IN/turnover.jsm.gz" >"$W/turnover.raw.jsm"
[ "$(sha256sum "$W/CURRICULUM.pjtw"|awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM raw SHA drift"
[ "$(sha256sum "$W/turnover.raw.jnnw"|awk '{print $1}')" = "$TURNOVER_CORPUS_SHA" ] || die "TURNOVER corpus SHA drift"
[ "$(sha256sum "$W/turnover.raw.jsm"|awk '{print $1}')" = "$TURNOVER_META_SHA" ] || die "TURNOVER meta SHA drift"
"$PY" - "$IN/abc-summary.json" "$ART/verified-abc.json" "$ART/verified-curriculum.json" "$ART/verified-turnover.json" "$ART/verified-scan.json" "$IN/scan-port.json" "$IN/scan-parity.json" "$W/C.pjtw" "$W/SCAN_EXACT.pjtw" "$ART/input-auth.json" <<'PY'
import hashlib,json,sys
from pathlib import Path
summary,abc,cur,turn,scan,port,parity=(json.load(open(p)) for p in sys.argv[1:8])
c_path,scan_path,out=sys.argv[8:11]
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
if (abc.get('job_id'),abc.get('attempt_id'),abc.get('code_sha'),abc.get('result_state')) != ('cpx62-1340-jass-megacorpus-comparative-fit-v1','20260814T123246Z-2ce07222','2ce07222f86c1468a1081fbdc53e9e17a0c5326e','completed'): raise SystemExit('ABC identity/state drift')
if (cur.get('job_id'),cur.get('attempt_id'),cur.get('result_state')) != ('cpx62-1341-jass-megacorpus-arm-d-fit-v1','20260814T191555Z-18c38a33','completed'): raise SystemExit('CURRICULUM identity/state drift')
if (turn.get('job_id'),turn.get('attempt_id'),turn.get('result_state')) != ('home-0977-l3-pure-turnover1to1-train-v1','20260726T071254Z-336bb984','completed'): raise SystemExit('TURNOVER identity/state drift')
if (scan.get('job_id'),scan.get('attempt_id'),scan.get('result_state')) != ('home-0957-l3-pure-m1-scan-gap-causal-v1','20260725T104131Z-ebf919fe','completed'): raise SystemExit('SCAN identity/state drift')
if summary.get('verdict')!='JASS_MEGACORPUS_ABC_FITS_READY': raise SystemExit('ABC verdict drift')
recipe=summary.get('fixed_recipe') or {}
if (recipe.get('architecture'),recipe.get('target'),recipe.get('l2'),recipe.get('max_iterations')) != ('8cf_exact_fold_tempo_120_extras','CONTEXT_30_ALIGNED_alpha_0.30',1e-5,2000): raise SystemExit('ABC recipe drift')
c_sha=sha(c_path)
if c_sha != summary['arms']['MEGA_FULL_4M']['model_raw_sha256']: raise SystemExit('arm C raw hash drift')
if port.get('source',{}).get('sha256')!='0e7161c38af605f5e367f3f8fe17525d1c40db722714c68921971b386e58abba': raise SystemExit('Scan eval source SHA drift')
scan_sha=sha(scan_path)
if port.get('output',{}).get('sha256') != scan_sha: raise SystemExit('Scan port output SHA drift')
cmp=parity.get('comparison') or {}
if parity.get('verdict')!='SCAN_STATIC_PORT_EXACT' or (cmp.get('positions'),cmp.get('exact_matches'),cmp.get('mismatches'),cmp.get('max_abs_delta')) != (600,600,0,0): raise SystemExit('historical Scan static parity drift')
if parity.get('pjtw',{}).get('sha256') != scan_sha: raise SystemExit('parity port SHA drift')
payload={'schema':'jass.sb1.input_auth.v1','ABC':{'job':abc['job_id'],'attempt':abc['attempt_id'],'code_sha':abc['code_sha']},'C_raw_sha256':c_sha,'CURRICULUM_raw_sha256':'319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1','SCAN_EXACT_raw_sha256':scan_sha,'SCAN_eval_sha256':port['source']['sha256'],'SCAN_static_parity':cmp,'TURNOVER_job':turn['job_id'],'target_source_job':abc['job_id'],'recipe':recipe,'markers':{'FULL_FITS':0,'FRESH_FORCE':0,'STRENGTH_GAMES':0,'SCIENTIFIC_DECISION':False}}
open(out,'w').write(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY

stage reproduce-current-split
python3 tools/selfplay_frontier.py split --data "$W/turnover.raw.jnnw" --meta "$W/turnover.raw.jsm" \
  --out-data "$W/current.jnnw" --out-meta "$W/current.jsm" --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$W/current-manifest-reproduced.json" >"$W/split.log" 2>&1
cmp "$W/current-manifest-reproduced.json" "$IN/current-manifest.json" || die "CURRENT split manifest does not reproduce archived source"
read -r RECORDS TRAIN HOLDOUT < <("$PY" - "$IN/current-manifest.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); print(d['records'],d['train_records'],d['holdout_records'])
PY
)
[ "$RECORDS" -eq "$EXPECTED_RECORDS" ] && [ "$TRAIN" -gt 0 ] && [ "$HOLDOUT" -gt 0 ] || die "CURRENT counts drift"

stage build-and-time-shared-feature-dump
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "missing Jass executable"
/usr/bin/time -f '%e' -o "$W/feature.seconds" timeout 7200s "$J" --dump-eval-features "$W/current.jnnw" "$W/current.feat" >"$W/features.log" 2>&1
K=$(python3 -c 'import struct,sys;f=open(sys.argv[1],"rb");assert f.read(4)==b"FEAT";print(struct.unpack("<II",f.read(8))[1])' "$W/current.feat")
[ "$K" -eq "$EXPECTED_EXTRAS" ] || die "feature architecture drift extras=$K"

stage read-only-common-coordinate-audit
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" "$PY" jobs/tools/sb1_weight_audit.py \
  --data "$W/current.jnnw" --feat "$W/current.feat" --train-count "$TRAIN" \
  --model C="$W/C.pjtw" --model CURRICULUM="$W/CURRICULUM.pjtw" --model SCAN_EXACT="$W/SCAN_EXACT.pjtw" \
  --chunk "$CHUNK" --out "$ART/sb1-weight-audit.json" >"$W/audit.log" 2>&1

stage bounded-consumed-subset-optimizer-sizer
"$PY" jobs/tools/sb1_subset.py --data "$W/current.jnnw" --feat "$W/current.feat" --target-values "$W/current-context30.npy" \
  --records "$SIZER_RECORDS" --holdout-count "$SIZER_HOLDOUT" --out-data "$W/sizer.jnnw" --out-feat "$W/sizer.feat" \
  --out-target-values "$W/sizer-target.npy" --manifest "$ART/sizer-subset.json"
for arm in SELF_BASIN SCAN_BASIN; do
  /usr/bin/time -f '%e' -o "$W/$arm.sizer.seconds" timeout 7200s env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" PYTHONUNBUFFERED=1 \
    "$PY" jobs/tools/sb1_fit_contract.py --arm "$arm" --python "$PY" --data "$W/sizer.jnnw" --feat "$W/sizer.feat" \
    --target-values "$W/sizer-target.npy" --prior-c "$W/C.pjtw" --prior-scan "$W/SCAN_EXACT.pjtw" \
    --out "$W/$arm.sizer.pjtw" --targets-report "$W/$arm.sizer-targets.json" --optimizer-report "$W/$arm.sizer-optimizer.json" \
    --holdout-count "$SIZER_HOLDOUT" --sizer-max-iter "$SIZER_MAXIT" --receipt "$ART/$arm-sizer-contract.json" \
    >"$W/$arm.sizer.log" 2>&1
done

stage publish-boundary-a-facts
{
  sha256sum "$J" jobs/tools/sb1_weight_audit.py jobs/tools/sb1_fit_contract.py jobs/tools/sb1_subset.py jobs/tools/sb1_scope_guard.py \
    jobs/tools/scan_exact_eval_port.py pattern_jass/tools/train_stream.py jobs/tools/fetch_result_files.py
} >"$ART/executable-tool-sha256.txt"
"$PY" - "$ART/SB1_BOUNDARY_A_FACTS.json" "$ART/input-auth.json" "$ART/sb1-weight-audit.json" "$ART/machine.txt" "$W/feature.seconds" "$W/SELF_BASIN.sizer.seconds" "$W/SCAN_BASIN.sizer.seconds" "$W/SELF_BASIN.sizer-optimizer.json" "$W/SCAN_BASIN.sizer-optimizer.json" "$EXPECTED_CODE_SHA" "$RECORDS" "$TRAIN" "$HOLDOUT" "$SIZER_RECORDS" "$SIZER_MAXIT" <<'PY'
import json,math,sys
out,authp,auditp,machinep,fp,asp,bsp,aop,bop,code=sys.argv[1:11]
records,train,holdout,sizer_records,sizer_maxit=map(int,sys.argv[11:16])
feature_s=float(open(fp).read().strip()); a_s=float(open(asp).read().strip()); b_s=float(open(bsp).read().strip())
aopt=json.load(open(aop)); bopt=json.load(open(bop))
def its(d): return int(d.get('iterations',sizer_maxit))
def arm(sec,opt):
    n=max(1,its(opt)); sec_per_iter_per_million=sec/n*1_000_000/sizer_records
    eta=sec_per_iter_per_million*records*2000/1_000_000
    return {'seconds':sec,'optimizer_iterations_observed':n,'seconds_per_iteration_per_million_rows':sec_per_iter_per_million,'naive_full_2000_iteration_eta_seconds':eta}
a=arm(a_s,aopt); b=arm(b_s,bopt); eta=max(a['naive_full_2000_iteration_eta_seconds'],b['naive_full_2000_iteration_eta_seconds'])
timeout=max(14400,int(math.ceil(eta*1.75/900.0)*900))
payload={'schema':'jass.sb1.boundary_a_facts.v1','verdict':'SB1_BOUNDARY_A_READY','code_sha':code,'machine':open(machinep).read().splitlines(),'current':{'records':records,'train_records':train,'holdout_records':holdout},'feature_dump':{'shared_for_future_ab':True,'seconds':feature_s,'rows_per_second':records/feature_s},'sizer':{'role':'bounded_consumed_subset_no_full_fit','records':sizer_records,'max_iterations':sizer_maxit,'SELF_BASIN':a,'SCAN_BASIN':b},'recommended_fit_timeout_seconds_per_arm':timeout,'input_auth':json.load(open(authp)),'weight_audit_path':'sb1-weight-audit.json','tool_sha_path':'executable-tool-sha256.txt','markers':{'FULL_FITS':0,'FRESH_FORCE':0,'STRENGTH_GAMES':0,'SCIENTIFIC_DECISION':False},'next_boundary':'GO SB1 FIT'}
open(out,'w').write(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY
printf '0\n' >"$ART/FULL_FITS__0"; printf '0\n' >"$ART/FRESH_FORCE__0"; printf '0\n' >"$ART/STRENGTH_GAMES__0"; printf 'FALSE\n' >"$ART/SCIENTIFIC_DECISION__FALSE"
printf 'SB1_BOUNDARY_A_READY\n' >"$ART/VERDICT__SB1_BOUNDARY_A_READY"
printf 'FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"; printf 'NULL\n' >"$ART/AUTOMATIC_NEXT_JOB__NULL"
stage complete
say "SB1_BOUNDARY_A_READY FULL_FITS=0 FRESH_FORCE=0 STRENGTH_GAMES=0 SCIENTIFIC_DECISION=FALSE"
