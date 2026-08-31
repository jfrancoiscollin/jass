#!/usr/bin/env bash
# SB1 frozen fit pair. This script is intentionally unreachable without a distinct
# post-Boundary-A GO_SB1_FIT=1. It creates no fresh openings and runs no games.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"; : "${BOUNDARY_A_PREFIX:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"; GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$IN" "$ART" "$GEOM"
RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*"|tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }

ABC_ROOT="r2:jass-data/runs/cpx62-1340-jass-megacorpus-comparative-fit-v1/20260814T123246Z-2ce07222"
TURNOVER_ROOT="r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984"
SCAN_ROOT="r2:jass-data/runs/home-0957-l3-pure-m1-scan-gap-causal-v1/20260725T104131Z-ebf919fe"
TURNOVER_CORPUS_SHA="9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
TURNOVER_META_SHA="acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
HOLDOUT_MOD=10; SPLIT_SEED=577215; CHUNK=20000
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"; VENV_READY="$VENV/.jass-runtime-ready-v1"
FIT_TIMEOUT="${SB1_FIT_TIMEOUT_SECONDS:-21600}"

finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  (cd "$W" && find . -maxdepth 1 -name '*.log' -type f -print0|tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat "$W"/*.npy "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-([0-9]+)-l3-sb1-scan-basin-fit-v1$ ]] || die "invalid SB1 fit job nomenclature"
[ "${GO_SB1_FIT:-0}" = 1 ] || die "distinct post-facts GO SB1 FIT missing"
[ "${NO_FRESH_FORCE:-0}" = 1 ] || die "NO_FRESH_FORCE guard missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX62 contract mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree must be detached and clean"
[ -f "$VENV_READY" ] || die "persistent numeric runtime absent"; PY="$VENV/bin/python"

# Boundary-A facts are a mandatory authorization prerequisite, not a source of new science.
timeout 900s python3 jobs/tools/fetch_result_files.py --prefix "$BOUNDARY_A_PREFIX" \
  --file artefacts/SB1_BOUNDARY_A_FACTS.json=boundary-a.json \
  --file artefacts/input-auth.json=boundary-a-auth.json \
  --out-dir "$IN" --report "$ART/verified-boundary-a.json" >"$W/fetch-boundary-a.log" 2>&1
"$PY" - "$IN/boundary-a.json" "$EXPECTED_CODE_SHA" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
if d.get('verdict')!='SB1_BOUNDARY_A_READY' or d.get('code_sha')!=sys.argv[2]: raise SystemExit('Boundary-A facts/code mismatch')
if d.get('markers')!={'FRESH_FORCE':0,'FULL_FITS':0,'SCIENTIFIC_DECISION':False,'STRENGTH_GAMES':0}: raise SystemExit('Boundary-A markers drift')
if d.get('next_boundary')!='GO SB1 FIT': raise SystemExit('Boundary-A did not stop at GO SB1 FIT')
PY

# Re-fetch immutable scientific inputs. No fresh PL8 or force cohort is referenced.
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$ABC_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=abc-summary.json \
  --file artefacts/mega_full_4m.pjtw.gz=C.pjtw.gz \
  --file artefacts/current_2m-context30.npy.gz=current-context30.npy.gz \
  --file artefacts/current_2m-manifest.json=current-manifest.json \
  --out-dir "$IN" --report "$ART/verified-abc.json" >"$W/fetch-abc.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_ROOT" \
  --file artefacts/turnover1to1.jnnw.gz=turnover.jnnw.gz \
  --file artefacts/turnover1to1.jsm.gz=turnover.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-turnover.json" >"$W/fetch-turnover.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$SCAN_ROOT" \
  --file artefacts/scan-exact-8cf.pjtw.gz=SCAN_EXACT.pjtw.gz \
  --file artefacts/scan-exact-port-manifest.json=scan-port.json \
  --file artefacts/scan-static-parity.json=scan-parity.json \
  --out-dir "$IN" --report "$ART/verified-scan.json" >"$W/fetch-scan.log" 2>&1
for spec in C SCAN_EXACT; do gunzip -c "$IN/$spec.pjtw.gz" >"$W/$spec.pjtw"; done
gunzip -c "$IN/current-context30.npy.gz" >"$W/current-context30.npy"
gunzip -c "$IN/turnover.jnnw.gz" >"$W/turnover.raw.jnnw"; gunzip -c "$IN/turnover.jsm.gz" >"$W/turnover.raw.jsm"
[ "$(sha256sum "$W/turnover.raw.jnnw"|awk '{print $1}')" = "$TURNOVER_CORPUS_SHA" ] || die "TURNOVER corpus drift"
[ "$(sha256sum "$W/turnover.raw.jsm"|awk '{print $1}')" = "$TURNOVER_META_SHA" ] || die "TURNOVER meta drift"
"$PY" - "$IN/boundary-a-auth.json" "$W/C.pjtw" "$W/SCAN_EXACT.pjtw" "$IN/scan-parity.json" <<'PY'
import hashlib,json,sys
sha=lambda p:hashlib.sha256(open(p,'rb').read()).hexdigest()
a=json.load(open(sys.argv[1])); parity=json.load(open(sys.argv[4]))
if sha(sys.argv[2])!=a['C_raw_sha256'] or sha(sys.argv[3])!=a['SCAN_EXACT_raw_sha256']: raise SystemExit('prior identities differ from Boundary A')
if parity.get('verdict')!='SCAN_STATIC_PORT_EXACT' or parity.get('comparison',{}).get('max_abs_delta')!=0: raise SystemExit('Scan exact parity drift')
PY
python3 tools/selfplay_frontier.py split --data "$W/turnover.raw.jnnw" --meta "$W/turnover.raw.jsm" \
  --out-data "$W/current.jnnw" --out-meta "$W/current.jsm" --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$W/current-manifest-reproduced.json" >"$W/split.log" 2>&1
cmp "$W/current-manifest-reproduced.json" "$IN/current-manifest.json" || die "CURRENT split drift"
read -r RECORDS TRAIN HOLDOUT < <("$PY" - "$IN/current-manifest.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); print(d['records'],d['train_records'],d['holdout_records'])
PY
)
[ "$RECORDS" -eq 2000000 ] || die "not CURRENT_2M"

# Build production static feature path and dump exactly once; both arms consume this byte-identical file.
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
J="$W/build/jass"
timeout 7200s "$J" --dump-eval-features "$W/current.jnnw" "$W/current.shared.feat" >"$W/features.log" 2>&1

# Exactly two frozen fits, identical except --prior-mean selected by the registered arm.
for arm in SELF_BASIN SCAN_BASIN; do
  timeout "$FIT_TIMEOUT" env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" PYTHONUNBUFFERED=1 \
    "$PY" jobs/tools/sb1_fit_contract.py --arm "$arm" --python "$PY" \
      --data "$W/current.jnnw" --feat "$W/current.shared.feat" --target-values "$W/current-context30.npy" \
      --prior-c "$W/C.pjtw" --prior-scan "$W/SCAN_EXACT.pjtw" --out "$W/$arm.pjtw" \
      --targets-report "$ART/$arm-target-consumption.json" --optimizer-report "$ART/$arm-optimizer.json" \
      --holdout-count "$HOLDOUT" --receipt "$ART/$arm-fit-contract.json" >"$W/$arm-fit.log" 2>&1
  "$PY" jobs/tools/verify_optimizer_convergence.py --report "$ART/$arm-optimizer.json" --label "$arm" \
    --expected-max-iterations 2000 --expected-maxcor 20 --expected-gtol 1e-4 --receipt "$ART/$arm-convergence.json"
  gzip -n -c "$W/$arm.pjtw" >"$ART/$arm.pjtw.gz"
done

env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" "$PY" jobs/tools/sb1_postfit_readout.py \
  --data "$W/current.jnnw" --feat "$W/current.shared.feat" --target-values "$W/current-context30.npy" --train-count "$TRAIN" \
  --self-basin "$W/SELF_BASIN.pjtw" --scan-basin "$W/SCAN_BASIN.pjtw" --out "$ART/SB1_POSTFIT_READOUT.json" >"$W/readout.log" 2>&1
"$PY" - "$ART/SELF_BASIN-fit-contract.json" "$ART/SCAN_BASIN-fit-contract.json" "$ART/SB1_FIT_PAIR.json" "$EXPECTED_CODE_SHA" <<'PY'
import json,sys
a,b=(json.load(open(p)) for p in sys.argv[1:3])
if a['normalized_science_command']!=b['normalized_science_command']: raise SystemExit('A/B command contract differs beyond prior/output paths')
expected={'chunk':20000,'fold':'exact','l2':1e-05,'lbfgs_gtol':0.0001,'lbfgs_maxcor':20,'loss':'logistic','max_iter':2000,'phase':'tempo-stage','prior_decay':0.0,'prune':True,'target':'external'}
if a['recipe']!=expected or b['recipe']!=expected: raise SystemExit('frozen recipe drift')
payload={'schema':'jass.sb1.fit_pair.v1','code_sha':sys.argv[4],'arms':['SELF_BASIN','SCAN_BASIN'],'full_fits':2,'shared_feature_dump':True,'only_treatment_difference':'prior_basin','markers':{'FULL_FITS':2,'FRESH_FORCE':0,'STRENGTH_GAMES':0,'SCIENTIFIC_DECISION':False},'strength_verdict':None,'next_boundary':'runtime strength preflight, then GO SB1 FORCE'}
open(sys.argv[3],'w').write(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY
printf '2\n' >"$ART/FULL_FITS__2"; printf '0\n' >"$ART/FRESH_FORCE__0"; printf '0\n' >"$ART/STRENGTH_GAMES__0"; printf 'FALSE\n' >"$ART/SCIENTIFIC_DECISION__FALSE"
printf 'SB1_FITS_HEALTHY_AWAIT_STRENGTH_PREFLIGHT\n' >"$ART/VERDICT__SB1_FITS_HEALTHY_AWAIT_STRENGTH_PREFLIGHT"
printf 'FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"; printf 'NULL\n' >"$ART/AUTOMATIC_NEXT_JOB__NULL"
say "SB1_FITS_HEALTHY_AWAIT_STRENGTH_PREFLIGHT FULL_FITS=2 FRESH_FORCE=0 STRENGTH_GAMES=0 SCIENTIFIC_DECISION=FALSE"
