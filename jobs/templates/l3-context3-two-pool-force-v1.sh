#!/usr/bin/env bash
# Preregistered terminal causal gate for CTX3 ALIGNED vs SHUFFLED.
# Two fresh mutually disjoint 3000-opening pools; native 0.1 s is primary and
# Q00 depth 9 is diagnostic. Reuses the paired 1418 models without refitting.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"

FIT_JOB="cpx62-1418-l3-context3-paired-patterneval-fit-v1"
FIT_ATTEMPT="20260819T074026Z-1e718553"
FIT_CODE_SHA="1e71855338b0642a28dd5d4023d9dba6bdf3dbf0"
FIT_PREFIX="r2:jass-data/runs/$FIT_JOB/$FIT_ATTEMPT"

NOPEN=3000
CANDIDATES=30000
POOL_SEED_1=2026081907
POOL_SEED_2=2026081908
GATE_BOOTSTRAP_SEED_1=2026081909
GATE_BOOTSTRAP_SEED_2=2026081910
COMBINED_NATIVE_SEED=2026081911
COMBINED_Q00_SEED=2026081912
BOOTSTRAP=200000
GAMES_PER_VIEW=6000
NSH=12
PAR=12
FORCE_DEPTH=9
MOVETIME=0.1
CACHE_MB=128
ERROR_LIMIT=120
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
VENV_READY="$VENV/.jass-runtime-ready-v1"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

# One line per immutable historical pool: label|R2 prefix|artifact path.
EXCLUDE_SPECS="pool-context2-curriculum-alpha30-first3000|r2:jass-data/runs/cpx62-1398-l3-context2-curriculum-alpha30-fresh3000-pool1-v1/20260818T061513Z-f60336ca|artefacts/context2-curriculum-alpha30-pool1-openings.fen
pool-context2-curriculum-alpha30-second3000|r2:jass-data/runs/cpx62-1401-l3-context2-curriculum-alpha30-fresh3000-pool2-v1/20260818T073556Z-f60336ca|artefacts/context2-curriculum-alpha30-pool2-openings.fen
pool-context2-alpha100-first3000|r2:jass-data/runs/cpx62-1386-l3-context2-alpha100-fresh3000-pool1-v1/20260817T145036Z-05554755|artefacts/context2-alpha100-pool1-openings.fen
pool-context2-primary-first3000|r2:jass-data/runs/cpx62-1375-l3-context2-primary-pool1-v1/20260817T025306Z-3393763d|artefacts/context2-primary-pool1-openings.fen
pool-context2-primary-second3000|r2:jass-data/runs/cpx62-1377-l3-context2-primary-pool2-v1/20260817T030349Z-3393763d|artefacts/context2-primary-pool2-openings.fen
pool-context30-causal-first3000|r2:jass-data/runs/cpx62-1360-l3-context30-causal-pool1-v1/20260816T075225Z-196d5e1d|artefacts/context30-causal-pool1-openings.fen
pool-context30-causal-second3000|r2:jass-data/runs/cpx62-1361-l3-context30-causal-pool2-v1/20260816T080325Z-196d5e1d|artefacts/context30-causal-pool2-openings.fen
pool-d-champion-first3000|r2:jass-data/runs/cpx62-1348-jass-d-champion-fresh3000-pool-v1/20260815T065455Z-18c38a33|artefacts/d-champion-fresh3000-openings.fen
pool-d-champion-replication3000|r2:jass-data/runs/cpx62-1351-jass-d-champion-replication3000-pool-v1/20260815T083517Z-18c38a33|artefacts/d-champion-replication3000-openings.fen
pool-abcd-highn1500|r2:jass-data/runs/home-1108-l3-pure-reverse-seed-scale4m-independent-readout-v1/20260731T034759Z-3351b160|artefacts/reverse-seed-scale4m-readout-openings.fen
pool-abcd-source500|r2:jass-data/runs/home-0984bis-l3-pure-turnover-l2-preflight-v2/20260726T122615Z-5ef14ffe|artefacts/turnover-l2-eval-openings.fen
pool-big3000|r2:jass-data/runs/cpx62-1154-l3-big-opening-pool-v1/20260802T120251Z-9b57e0aa|artefacts/big3000-openings.fen
pool-big3000b|r2:jass-data/runs/cpx62-1183-l3-second-big-opening-pool/20260805T155017Z-cd9064f9|artefacts/big3000b-openings.fen
pool-vol8m|r2:jass-data/runs/home-1004-l3-pure-volume8m-preflight-v2/20260727T211936Z-90d3aad1|artefacts/vol8m-eval-openings.fen
pool-succession|r2:jass-data/runs/home-0995-l3-pure-turnover-succession-preflight-v2/20260727T054246Z-f20e59d0|artefacts/turnover-succession-openings.fen"

W="$JASS_RESULT_DIR/work"
IN="$JASS_RESULT_DIR/inputs"
ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"
FORCE="$ART/force"
mkdir -p "$W" "$IN" "$ART" "$GEOM" "$FORCE"
RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
STAGE="$W/.stage"
: >"$RES"
echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

MON=""
monitor(){
  (t0=$(date +%s); while true; do
    {
      printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
      printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
      printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
      printf 'pools_ready=%s\n' "$(find "$ART" -maxdepth 1 -name 'ctx3-force-pool*-openings.fen' | wc -l)"
      printf 'force_views_ready=%s\n' "$(find "$FORCE" -name 'pool*-*.json' | wc -l)"
    } >"$PROG.tmp"
    mv "$PROG.tmp" "$PROG"
    cp "$PROG" "$ART/PROGRESS.txt"
    sleep 120
  done) & MON="$!"
}
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$GEOM" "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-context3-two-pool-force-v1$ ]] || die "invalid job nomenclature"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(nproc)" -eq 16 ] || die "16-CPU CPX contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
[ -f "$VENV_READY" ] || die "persistent numeric runtime absent; do not reinstall"
PY="$VENV/bin/python"
"$PY" -c 'import numpy; assert numpy.__version__' || die "numeric runtime invalid"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_context3_two_pool_force_readout.py jobs/tools/run_jass_gate_bounded.py
"$PY" -m unittest jobs.tests.test_l3_context3_two_pool_force_readout \
  jobs.tests.test_l3_context3_two_pool_force_template >"$W/tests.log" 2>&1

stage fetch-and-authenticate-1418-models
python3 jobs/tools/fetch_result_files.py --prefix "$FIT_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=fit-summary.json \
  --file artefacts/aligned.pjtw.gz=aligned.pjtw.gz \
  --file artefacts/shuffled.pjtw.gz=shuffled.pjtw.gz \
  --file artefacts/aligned-convergence.json=aligned-convergence.json \
  --file artefacts/shuffled-convergence.json=shuffled-convergence.json \
  --file artefacts/aligned-target-consumption.json=aligned-target-consumption.json \
  --file artefacts/shuffled-target-consumption.json=shuffled-target-consumption.json \
  --file artefacts/context3-paired-targets.json=context3-paired-targets.json \
  --out-dir "$IN" --report "$ART/verified-fit.json" >"$W/fetch-fit.log" 2>&1 || die "1418 fetch failed"
gunzip -t "$IN/aligned.pjtw.gz"
gunzip -t "$IN/shuffled.pjtw.gz"
gunzip -c "$IN/aligned.pjtw.gz" >"$W/aligned.pjtw"
gunzip -c "$IN/shuffled.pjtw.gz" >"$W/shuffled.pjtw"
"$PY" - "$IN" "$ART" "$W" "$FIT_JOB" "$FIT_ATTEMPT" "$FIT_CODE_SHA" <<'PY'
import hashlib,json,sys
from pathlib import Path
src,art,work=map(Path,sys.argv[1:4]); job,attempt,code=sys.argv[4:7]
def load(path): return json.loads(path.read_text(encoding='utf-8'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def require(ok,msg):
 if not ok: raise SystemExit(msg)
receipt=load(art/'verified-fit.json')
got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'),receipt.get('result_state'),receipt.get('exit_code'))
require(got==(job,attempt,code,'completed',0),f'1418 identity/state drift: {got}')
summary=load(src/'fit-summary.json')
require(summary.get('verdict')=='JASS_CONTEXT3_PAIRED_PATTERNEVAL_MODELS_READY','1418 verdict drift')
require(summary.get('primary_contrast')=='ALIGNED_vs_SHUFFLED_on_two_fresh_disjoint_opening_pools','1418 contrast drift')
require(summary.get('strength_games_played')==0 and summary.get('frozen_cohorts_read')==0,'1418 scope drift')
require(summary.get('promotion_authorized') is False and summary.get('automatic_next_job') is None,'1418 promotion drift')
models={}
for label,name in [('ALIGNED','aligned'),('SHUFFLED','shuffled')]:
 arm=summary['arms'][label]; conv=load(src/f'{name}-convergence.json')
 require(conv.get('success') is True and float(conv.get('gradient_inf_norm',1.0))<=1e-4,f'{label}: convergence drift')
 raw=work/f'{name}.pjtw'; digest=sha(raw)
 require(digest==arm['model_raw_sha256'],f'{label}: raw model hash drift')
 consume=load(src/f'{name}-target-consumption.json')
 require(consume['source']['sha256']==arm['target_sha256'],f'{label}: consumed target drift')
 require(arm['target_sha256']==summary['target_certificate']['outputs'][f'{name}_sha256'],f'{label}: target certificate drift')
 models[label]={'model_raw_sha256':digest,'model_gz_sha256':sha(src/f'{name}.pjtw.gz'),
                'target_sha256':arm['target_sha256'],'convergence':conv}
require(models['ALIGNED']['model_raw_sha256']!=models['SHUFFLED']['model_raw_sha256'],'models unexpectedly identical')
payload={'schema':'jass.context3.force_models.v1','verdict':'JASS_CONTEXT3_FORCE_MODELS_AUTHENTICATED',
 'fit_source':receipt,'fit_job':job,'fit_attempt':attempt,'fit_code_sha':code,
 'models':models,'distinct':True,'reused_without_refit':True,'promotion_authorized':False}
(art/'model-certificate.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY

stage fetch-historical-opening-pools
EXCL_ARGS=()
EXCL_NAMES=()
while IFS='|' read -r label prefix remote_path; do
  [ -n "${label:-}" ] || continue
  python3 jobs/tools/fetch_result_files.py --prefix "$prefix" \
    --file "$remote_path=$label.fen" --out-dir "$IN" \
    --report "$ART/verified-exclude-$label.json" --expected-state completed \
    >"$W/fetch-$label.log" 2>&1 || die "historical pool fetch failed: $label"
  EXCL_ARGS+=(--exclude "$IN/$label.fen")
  EXCL_NAMES+=("$label")
done <<<"$EXCLUDE_SPECS"
[ "${#EXCL_NAMES[@]}" -eq 15 ] || die "historical exclusion count drift"

stage build-common-certified-8cf-engine
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON \
  -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests >"$W/build.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB ctest --test-dir "$W/build" --output-on-failure >"$W/ctest.log" 2>&1
J="$W/build/jass"
for arm in aligned shuffled; do
  printf 'hello\nquit\n' | timeout 60 "$J" --pattern "$W/$arm.pjtw" >"$W/load-$arm.log" 2>&1
  grep -q '^ready' "$W/load-$arm.log" || die "$arm model does not load"
done

generate_pool(){
  local index="$1" seed="$2"
  local out="ctx3-force-pool${index}-openings"
  local extra=("${EXCL_ARGS[@]}")
  if [ "$index" -eq 2 ]; then extra+=(--exclude "$ART/ctx3-force-pool1-openings.fen"); fi
  for pass in a b; do
    "$J" --gen-opening-pool "$CANDIDATES" "$W/pool${index}-cand-$pass.fen" 8 32 20 "$seed" \
      >"$W/pool${index}-gen-$pass.log" 2>&1
  done
  cmp -s "$W/pool${index}-cand-a.fen" "$W/pool${index}-cand-b.fen" || die "pool$index candidates nondeterministic"
  python3 jobs/tools/select_independent_opening_pool.py \
    --candidates "$W/pool${index}-cand-a.fen" --expected "$NOPEN" "${extra[@]}" \
    --generator-seed "$seed" --out "$ART/$out.fen" --manifest "$ART/$out.json" \
    >"$W/pool${index}-select.log" 2>&1 || die "pool$index selection failed"
  python3 jobs/tools/validate_opening_pool.py --pool "$ART/$out.fen" \
    --expected "$NOPEN" --generator-seed "$seed" "${extra[@]}" \
    --out "$ART/$out-provenance.json" >"$W/pool${index}-validate.log" 2>&1 || die "pool$index validation failed"
}

stage generate-certify-fresh-pool1
generate_pool 1 "$POOL_SEED_1"
stage generate-certify-fresh-pool2
generate_pool 2 "$POOL_SEED_2"
COMMON=$(grep -Fx -f "$ART/ctx3-force-pool1-openings.fen" "$ART/ctx3-force-pool2-openings.fen" | grep -c . || true)
[ "$COMMON" -eq 0 ] || die "fresh pools overlap by $COMMON openings"
for index in 1 2; do
  file="$ART/ctx3-force-pool${index}-openings.fen"
  [ "$(grep -c . "$file" || true)" -eq "$NOPEN" ] || die "pool$index cardinality drift"
  for label in "${EXCL_NAMES[@]}"; do
    overlap=$(grep -Fx -f "$IN/$label.fen" "$file" | grep -c . || true)
    [ "$overlap" -eq 0 ] || die "pool$index overlaps historical $label by $overlap"
  done
done

"$PY" - "$ART" "$POOL_SEED_1" "$POOL_SEED_2" "${EXCL_NAMES[@]}" <<'PY'
import hashlib,json,sys
from pathlib import Path
art=Path(sys.argv[1]); seeds=list(map(int,sys.argv[2:4])); exclusions=sys.argv[4:]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def rows(path): return [x for raw in path.read_text().splitlines() if (x:=raw.split('#',1)[0].strip())]
pools=[]; sets=[]
for index,seed in enumerate(seeds,1):
 stem=art/f'ctx3-force-pool{index}-openings'; fen=stem.with_suffix('.fen')
 values=rows(fen); manifest=json.load(open(stem.with_suffix('.json'))); provenance=json.load(open(art/f'{stem.name}-provenance.json'))
 if len(values)!=3000 or len(set(values))!=3000: raise SystemExit(f'pool{index}: cardinality/uniqueness drift')
 digest=sha(fen)
 if manifest.get('sha256')!=digest or manifest.get('generator_seed')!=seed or manifest.get('overlap_records')!=0: raise SystemExit(f'pool{index}: selector certificate drift')
 if provenance.get('generator_seed')!=seed or provenance.get('overlap_records')!=0: raise SystemExit(f'pool{index}: provenance drift')
 sets.append(set(values)); pools.append({'pool_index':index,'openings':3000,'seed':seed,'sha256':digest,
  'fen':fen.name,'selector_manifest_sha256':sha(stem.with_suffix('.json')),
  'provenance_sha256':sha(art/f'{stem.name}-provenance.json')})
if sets[0]&sets[1]: raise SystemExit('fresh pools are not mutually disjoint')
payload={'schema':'jass.context3.two_fresh_pools.v1','verdict':'JASS_CONTEXT3_TWO_FRESH_POOLS_READY',
 'pools':pools,'mutually_disjoint':True,'mutual_overlap':0,
 'historical_exclusions':exclusions,'historical_exclusion_count':len(exclusions),
 'all_historical_overlaps_zero':True,'deterministic_generation_repeated':True,
 'promotion_authorized':False}
(art/'pool-certificate.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY

run_gate(){
  local pool_index="$1" view="$2" seed="$3"
  local budget=()
  [ "$view" = native ] && budget=(--movetime "$MOVETIME") || budget=(--depth "$FORCE_DEPTH")
  timeout -k 120s 25200s "$PY" jobs/tools/run_jass_gate_bounded.py \
    --jass "$J" --pattern-a "$W/aligned.pjtw" --pattern-b "$W/shuffled.pjtw" \
    --search-params-a "$Q00" --search-params-b "$Q00" \
    --openings-file "$ART/ctx3-force-pool${pool_index}-openings.fen" "${budget[@]}" --pairs 1 \
    --max-plies 160 --nshards "$NSH" --max-parallel "$PAR" \
    --timeout 21600 --game-timeout 180 \
    --paired-bootstrap-samples "$BOOTSTRAP" --paired-bootstrap-seed "$seed" \
    --work-dir "$W/gate-pool${pool_index}-$view" --out "$FORCE/pool${pool_index}-$view.json" \
    >"$W/force-pool${pool_index}-$view.log" 2>&1
}

for view in native q00; do
  for pool_index in 1 2; do
    eval "seed=\$GATE_BOOTSTRAP_SEED_$pool_index"
    stage "force-pool${pool_index}-${view}-${GAMES_PER_VIEW}-games"
    run_gate "$pool_index" "$view" "$seed" || die "pool$pool_index/$view gate failed"
    say "pool$pool_index/$view complete n=$GAMES_PER_VIEW"
  done
done

stage audit-combine-and-decide
"$PY" jobs/tools/l3_context3_two_pool_force_readout.py \
  --pool1-native "$FORCE/pool1-native.json" --pool1-q00 "$FORCE/pool1-q00.json" \
  --pool2-native "$FORCE/pool2-native.json" --pool2-q00 "$FORCE/pool2-q00.json" \
  --pool-certificate "$ART/pool-certificate.json" --model-certificate "$ART/model-certificate.json" \
  --gate-bootstrap-seed-pool1 "$GATE_BOOTSTRAP_SEED_1" \
  --gate-bootstrap-seed-pool2 "$GATE_BOOTSTRAP_SEED_2" \
  --combined-native-seed "$COMBINED_NATIVE_SEED" --combined-q00-seed "$COMBINED_Q00_SEED" \
  --bootstrap-samples "$BOOTSTRAP" --out "$ART/context3-two-pool-force-readout.json" \
  >"$W/readout.log" 2>&1 || die "terminal readout failed"
cp "$ART/context3-two-pool-force-readout.json" "$ART/JASS_CONTROL_SUMMARY.json"
VERDICT=$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
: >"$ART/VERDICT__$VERDICT"
: >"$ART/GAMES_TOTAL__24000"
: >"$ART/MODELS_REUSED__TRUE"
: >"$ART/REFITS__0"
: >"$ART/NEW_SELFPLAY__0"
: >"$ART/FROZEN_COHORTS_READ__0"
: >"$ART/PROMOTION_AUTHORIZED__FALSE"
: >"$ART/AUTOMATIC_NEXT_JOB__NULL"
say "$VERDICT games=24000 refits=0 frozen=0 promotion=false automatic_next_job=null"
