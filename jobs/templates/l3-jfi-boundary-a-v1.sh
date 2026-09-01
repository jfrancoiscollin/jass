#!/usr/bin/env bash
# JFI Boundary A: immutable input authentication, shared feature timing and
# four bounded 20k-row/2-iteration optimizer probes. No full fit or game.
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

TURNOVER_ROOT="r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984"
ABC_ROOT="r2:jass-data/runs/cpx62-1340-jass-megacorpus-comparative-fit-v1/20260814T123246Z-2ce07222"
CURRICULUM_ROOT="r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/20260814T191555Z-18c38a33"
TURNOVER_SHA="9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
TURNOVER_META_SHA="acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
SPLIT_SEED=577215; EXPECTED_RECORDS=2000000; EXPECTED_EXTRAS=120
SIZER_RECORDS=20000; SIZER_HOLDOUT=2000; SIZER_MAXIT=2; CHUNK=20000
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
PY="$VENV/bin/python"

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
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-jfi-boundary-a-v1$ ]] || die "invalid job nomenclature"
[ "${BOUNDARY_A_APPROVED:-0}" = 1 ] || die "Boundary A authorization missing"
[ "${NO_FULL_FITS:-0}" = 1 ] || die "NO_FULL_FITS guard missing"
[ "${NO_FRESH_OPENINGS:-0}" = 1 ] || die "NO_FRESH_OPENINGS guard missing"
[ "${NO_STRENGTH_GAMES:-0}" = 1 ] || die "NO_STRENGTH_GAMES guard missing"
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

stage authenticate-inputs
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_ROOT" \
  --file artefacts/turnover1to1.jnnw.gz=turnover.jnnw.gz \
  --file artefacts/turnover1to1.jsm.gz=turnover.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-turnover.json" >"$W/fetch-turnover.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$ABC_ROOT" \
  --file artefacts/current_2m-context30.npy.gz=context30.npy.gz \
  --file artefacts/current_2m-manifest.json=source-manifest.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=abc-summary.json \
  --out-dir "$IN" --report "$ART/verified-abc.json" >"$W/fetch-abc.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" >"$W/fetch-curriculum.log" 2>&1
gunzip -c "$IN/turnover.jnnw.gz" >"$W/turnover.raw.jnnw"
gunzip -c "$IN/turnover.jsm.gz" >"$W/turnover.raw.jsm"
gunzip -c "$IN/context30.npy.gz" >"$W/context30.npy"
gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
[ "$(sha256sum "$W/turnover.raw.jnnw"|awk '{print $1}')" = "$TURNOVER_SHA" ] || die "TURNOVER SHA drift"
[ "$(sha256sum "$W/turnover.raw.jsm"|awk '{print $1}')" = "$TURNOVER_META_SHA" ] || die "TURNOVER meta SHA drift"
[ "$(sha256sum "$W/curriculum.pjtw"|awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM SHA drift"

stage reproduce-current-split
python3 tools/selfplay_frontier.py split --data "$W/turnover.raw.jnnw" --meta "$W/turnover.raw.jsm" \
  --out-data "$W/current.jnnw" --out-meta "$W/current.jsm" --holdout-mod 10 --seed "$SPLIT_SEED" \
  --manifest "$W/current-manifest.json" >"$W/split.log" 2>&1
cmp "$W/current-manifest.json" "$IN/source-manifest.json" || die "CURRENT split manifest drift"
read -r RECORDS TRAIN HOLDOUT < <("$PY" - "$W/current-manifest.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); print(d['records'],d['train_records'],d['holdout_records'])
PY
)
[ "$RECORDS" -eq "$EXPECTED_RECORDS" ] || die "CURRENT record drift"

stage shared-feature-dump
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "missing executable"
/usr/bin/time -f '%e' -o "$W/feature.seconds" timeout 7200s \
  "$J" --dump-eval-features "$W/current.jnnw" "$W/current.feat" >"$W/features.log" 2>&1
K=$(python3 -c 'import struct,sys;f=open(sys.argv[1],"rb");assert f.read(4)==b"FEAT";print(struct.unpack("<II",f.read(8))[1])' "$W/current.feat")
[ "$K" -eq "$EXPECTED_EXTRAS" ] || die "feature width drift"

stage bounded-four-arm-sizer
"$PY" jobs/tools/jfi_subset.py --data "$W/current.jnnw" --feat "$W/current.feat" \
  --target-values "$W/context30.npy" --records "$SIZER_RECORDS" --holdout-count "$SIZER_HOLDOUT" \
  --out-data "$W/sizer.jnnw" --out-feat "$W/sizer.feat" --out-target-values "$W/sizer.npy" \
  --manifest "$ART/JFI_SIZER_SUBSET.json"
fit_sizer(){
  local arm="$1"; shift
  /usr/bin/time -f '%e' -o "$W/$arm.seconds" timeout 3600s env \
    JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" PYTHONUNBUFFERED=1 \
    "$PY" pattern_jass/tools/train_stream.py --data "$W/sizer.jnnw" --feat "$W/sizer.feat" \
    --out "$W/$arm.pjtw" --target external --target-values "$W/sizer.npy" \
    --targets-report "$ART/$arm-targets.json" --loss logistic --exact-fold --tempo-stage \
    --holdout-count "$SIZER_HOLDOUT" --l2 1e-5 --max-iter "$SIZER_MAXIT" --chunk "$CHUNK" \
    --lbfgs-maxcor 20 --lbfgs-gtol 1e-4 --prune --optimizer-report "$ART/$arm-optimizer.json" \
    "$@" >"$W/$arm.log" 2>&1
}
fit_sizer A_CURRICULUM_INIT_CURRICULUM_CENTER --prior-mean "$W/curriculum.pjtw" --prior-decay 0
fit_sizer B_ZERO_INIT_CURRICULUM_CENTER --prior-mean "$W/curriculum.pjtw" --prior-decay 0 --init-mode zero
fit_sizer C_CURRICULUM_INIT_ZERO_CENTER --init-mode file --init-file "$W/curriculum.pjtw"
fit_sizer D_ZERO_INIT_ZERO_CENTER --init-mode zero

stage publish-boundary-a
"$PY" - "$ART/JFI_BOUNDARY_A_INPUT.json" "$EXPECTED_CODE_SHA" "$W" "$ART" "$RECORDS" "$TRAIN" "$HOLDOUT" <<'PY'
import hashlib,json,os,platform,sys
from pathlib import Path
out,code,w,art=sys.argv[1:5]; records,train,holdout=map(int,sys.argv[5:8]); w=Path(w); art=Path(art)
sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
arms=['A_CURRICULUM_INIT_CURRICULUM_CENTER','B_ZERO_INIT_CURRICULUM_CENTER','C_CURRICULUM_INIT_ZERO_CENTER','D_ZERO_INIT_ZERO_CENTER']
seconds={a:float((w/f'{a}.seconds').read_text()) for a in arms}
payload={'schema':'jass.jfi.boundary_a_input.v1','code_sha':code,
 'machine':{'host':platform.node(),'nproc':os.cpu_count(),'platform':platform.platform(),
            'cpu_model':os.environ['CPU_MODEL'],'isa_flags':os.environ['ISA_FLAGS'],
            'avx2':True,'bmi2':True,'native_build':True},
 'numeric_env':{k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')},
 'disk':{'code_path':str(Path.cwd()),'code_free_bytes':os.statvfs(Path.cwd()).f_bavail*os.statvfs(Path.cwd()).f_frsize,
         'scratch_path':str(w.parent),'scratch_free_bytes':os.statvfs(w).f_bavail*os.statvfs(w).f_frsize},
 'current_2m':{'records':records,'train_records':train,'holdout_records':holdout,'split_seed':577215,'sha256':sha(w/'current.jnnw')},
 'context30':{'sha256':sha(w/'context30.npy')},
 'feature_dump':{'rows':records,'seconds':float((w/'feature.seconds').read_text()),'sha256':sha(w/'current.feat')},
 'sizer':{'rows':20000,'iterations':2,'seconds':max(seconds.values()),'arm_seconds':seconds,
          'iterations_per_second':2/max(seconds.values()),
          'rows_per_iteration_second':20000/max(seconds.values()),
          'full_fit_timeout_seconds':86400},
 'markers':{'FULL_FITS':0,'FRESH_OPENINGS':0,'STRENGTH_GAMES':0,'SCIENTIFIC_DECISION':False,'SCAN_WEIGHT_READS':0,'SCAN_SCORE_READS':0}}
Path(out).write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY
"$PY" jobs/tools/jfi_boundary_a.py --input "$ART/JFI_BOUNDARY_A_INPUT.json" --out "$ART/JFI_BOUNDARY_A_FACTS.json" | tee -a "$RES"
printf '0\n' >"$ART/FULL_FITS__0"; printf '0\n' >"$ART/FRESH_OPENINGS__0"
printf '0\n' >"$ART/STRENGTH_GAMES__0"; printf 'FALSE\n' >"$ART/SCIENTIFIC_DECISION__FALSE"
printf '0\n' >"$ART/SCAN_WEIGHT_READS__0"; printf '0\n' >"$ART/SCAN_SCORE_READS__0"
printf 'GO JFI FIT\n' >"$ART/NEXT_BOUNDARY__GO_JFI_FIT"
stage complete
say "JFI_BOUNDARY_A_READY FULL_FITS=0 FRESH_OPENINGS=0 STRENGTH_GAMES=0 SCAN_WEIGHT_READS=0 SCAN_SCORE_READS=0"
