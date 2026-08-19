#!/usr/bin/env bash
# Read-only decision autopsy after the established harmful 1419 CTX3 gate.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"

FIT_JOB="cpx62-1418-l3-context3-paired-patterneval-fit-v1"
FIT_ATTEMPT="20260819T074026Z-1e718553"
FIT_CODE="1e71855338b0642a28dd5d4023d9dba6bdf3dbf0"
FIT_ROOT="r2:jass-data/runs/$FIT_JOB/$FIT_ATTEMPT"
FORCE_JOB="cpx62-1419-l3-context3-two-pool-force-v1"
FORCE_ATTEMPT="20260819T112556Z-8adc506a"
FORCE_CODE="8adc506a8ec95b1f170bc706def1fe052eca0d98"
FORCE_ROOT="r2:jass-data/runs/$FORCE_JOB/$FORCE_ATTEMPT"
AUDIT_JOB="cpx62-1420-l3-context3-terminal-audit-v1"
AUDIT_ATTEMPT="20260819T134046Z-69170897"
AUDIT_CODE="691708976581afd6dd539bb74927f264c65cac62"
AUDIT_ROOT="r2:jass-data/runs/$AUDIT_JOB/$AUDIT_ATTEMPT"
CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE="18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_ROOT="r2:jass-data/runs/$CURRICULUM_JOB/$CURRICULUM_ATTEMPT"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"

PER_POOL=192
TOTAL=384
NSH=8
CHOICE_DEPTH=9
JUDGE_DEPTH=12
SYMMETRY_PER_POOL=8
SELECTION_SEED=2026081913
BOOTSTRAP=100000
BOOTSTRAP_SEED=2026081914
CACHE_MB=128
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
VENV_READY="$VENV/.jass-runtime-ready-v1"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

W="$JASS_RESULT_DIR/work"
IN="$JASS_RESULT_DIR/inputs"
ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"
SHARDS="$W/shards"
mkdir -p "$W" "$IN" "$ART" "$GEOM" "$SHARDS"
RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
STAGE="$W/.stage"
: >"$RES"; echo start >"$STAGE"
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
      printf 'shards_ready=%s/%s\n' "$(find "$SHARDS" -name 'shard-*.json' | wc -l)" "$NSH"
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
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-context3-decision-flip-autopsy-v1$ ]] || die "invalid job nomenclature"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(nproc)" -eq 16 ] || die "16-CPU CPX contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] || die "frozen-read guard missing"
[ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] || die "promotion guard missing"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
[ -f "$VENV_READY" ] || die "persistent numeric runtime absent; do not reinstall"
PY="$VENV/bin/python"
"$PY" -c 'import numpy; assert numpy.__version__'
DFA=$(df -Pm /root | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 3000 ] || die "disk below 3GB"
monitor
say "sizing=cpx62_16cpu sample=$TOTAL choice_depth=$CHOICE_DEPTH judge_depth=$JUDGE_DEPTH nshards=$NSH eta_min=15-35"

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_context3_decision_flip_autopsy.py
"$PY" -m unittest jobs.tests.test_l3_context3_decision_flip_autopsy +  jobs.tests.test_l3_context3_two_pool_force_readout +  jobs.tests.test_l3_context3_two_pool_force_template >"$W/tests.log" 2>&1

fetch(){
  local root="$1" report="$2"; shift 2
  python3 jobs/tools/fetch_result_files.py --prefix "$root" "$@" +    --out-dir "$IN" --report "$ART/$report" --expected-state completed
}

stage fetch-and-authenticate-immutable-sources
fetch "$FIT_ROOT" verified-fit.json +  --file artefacts/JASS_CONTROL_SUMMARY.json=fit-summary.json +  --file artefacts/aligned.pjtw.gz=aligned.pjtw.gz +  --file artefacts/shuffled.pjtw.gz=shuffled.pjtw.gz >"$W/fetch-fit.log" 2>&1
fetch "$FORCE_ROOT" verified-force.json +  --file artefacts/JASS_CONTROL_SUMMARY.json=force-summary.json +  --file artefacts/model-certificate.json=model-certificate.json +  --file artefacts/pool-certificate.json=pool-certificate.json +  --file artefacts/ctx3-force-pool1-openings.fen=pool1.fen +  --file artefacts/ctx3-force-pool2-openings.fen=pool2.fen >"$W/fetch-force.log" 2>&1
fetch "$AUDIT_ROOT" verified-terminal-audit.json +  --file artefacts/JASS_CONTROL_SUMMARY.json=terminal-audit.json >"$W/fetch-audit.log" 2>&1
fetch "$CURRICULUM_ROOT" verified-curriculum.json +  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz >"$W/fetch-curriculum.log" 2>&1
for arm in aligned shuffled curriculum; do
  gunzip -t "$IN/$arm.pjtw.gz"
  gunzip -c "$IN/$arm.pjtw.gz" >"$W/$arm.pjtw"
done

"$PY" - "$IN" "$ART" "$FIT_JOB" "$FIT_ATTEMPT" "$FIT_CODE" +  "$FORCE_JOB" "$FORCE_ATTEMPT" "$FORCE_CODE" "$AUDIT_JOB" "$AUDIT_ATTEMPT" "$AUDIT_CODE" +  "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" "$CURRICULUM_CODE" "$CURRICULUM_SHA" <<'PY'
import hashlib,json,sys
from pathlib import Path
src,art=map(Path,sys.argv[1:3])
values=sys.argv[3:]
triples=[tuple(values[i:i+3]) for i in range(0,12,3)]
curr_sha=values[12]
def load(path): return json.loads(path.read_text(encoding='utf-8'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def require(ok,msg):
 if not ok: raise SystemExit(msg)
for receipt_name,expected in zip(
 ('verified-fit.json','verified-force.json','verified-terminal-audit.json','verified-curriculum.json'),
 triples):
 receipt=load(art/receipt_name)
 got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'))
 require(got==expected,f'{receipt_name}: identity drift {got}')
 require(receipt.get('result_state')=='completed' and receipt.get('exit_code')==0,f'{receipt_name}: state drift')
fit=load(src/'fit-summary.json'); force=load(src/'force-summary.json'); audit=load(src/'terminal-audit.json')
require(fit.get('verdict')=='JASS_CONTEXT3_PAIRED_PATTERNEVAL_MODELS_READY','1418 verdict drift')
require(force.get('verdict')=='JASS_CONTEXT3_ALIGNED_VS_SHUFFLED_NOT_ESTABLISHED','1419 verdict drift')
require(audit.get('verdict')=='JASS_CONTEXT3_TERMINAL_AUDIT_READY','1420 verdict drift')
require(audit.get('classification')=='BOTH_NATIVE_POINT_ESTIMATES_NONPOSITIVE','1420 classification drift')
require(force.get('frozen_cohorts_read')==0 and force.get('promotion_authorized') is False,'1419 scope drift')
require(force.get('model_certificate')==load(src/'model-certificate.json'),'model certificate drift')
require(force.get('pool_certificate')==load(src/'pool-certificate.json'),'pool certificate drift')
require(force['pool_certificate'].get('mutually_disjoint') is True,'pool disjointness drift')
require(sha(Path(sys.argv[1]).parent/'work'/'aligned.pjtw')==fit['arms']['ALIGNED']['model_raw_sha256'],'aligned model drift')
require(sha(Path(sys.argv[1]).parent/'work'/'shuffled.pjtw')==fit['arms']['SHUFFLED']['model_raw_sha256'],'shuffled model drift')
require(sha(Path(sys.argv[1]).parent/'work'/'curriculum.pjtw')==curr_sha,'CURRICULUM model drift')
PY

stage build-authentic-8cf-engine
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
grep -q "g_emasks" src/scan_eval.cpp || die "arch guard scan_eval"
grep -q "has_any_capture" src/search.cpp || die "arch guard search"
grep -q "has_any_capture" src/movegen.cpp || die "arch guard movegen"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON +  -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON +  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests >"$W/build.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB ctest --test-dir "$W/build" +  --output-on-failure >"$W/ctest.log" 2>&1
J="$W/build/jass"
for arm in aligned shuffled curriculum; do
  printf 'hello\nquit\n' | timeout 60 "$J" --pattern "$W/$arm.pjtw" >"$W/load-$arm.log" 2>&1
  grep -q '^ready' "$W/load-$arm.log" || die "$arm model does not load"
done

stage deterministic-balanced-selection
"$PY" jobs/tools/l3_context3_decision_flip_autopsy.py prepare +  --pool "POOL1=$IN/pool1.fen" --pool "POOL2=$IN/pool2.fen" +  --per-pool "$PER_POOL" --seed "$SELECTION_SEED" --out "$ART/selection.json" +  >"$W/selection.log" 2>&1
"$PY" - "$ART/selection.json" "$TOTAL" "$PER_POOL" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); total=int(sys.argv[2]); per=int(sys.argv[3])
assert r['total']==total and r['per_pool']==per and len(r['rows'])==total
assert sum(x['pool_index']==1 for x in r['rows'])==per
assert sum(x['pool_index']==2 for x in r['rows'])==per
PY

stage parallel-decision-flip-autopsy
pids=()
for shard in $(seq 0 $((NSH-1))); do
  timeout -k 30s 2400s "$PY" jobs/tools/l3_context3_decision_flip_autopsy.py worker +    --selection "$ART/selection.json" --jass "$J" +    --aligned "$W/aligned.pjtw" --shuffled "$W/shuffled.pjtw" +    --curriculum "$W/curriculum.pjtw" --search-params "$Q00" +    --choice-depth "$CHOICE_DEPTH" --judge-depth "$JUDGE_DEPTH" +    --symmetry-per-pool "$SYMMETRY_PER_POOL" --shard "$shard" --nshards "$NSH" +    --out "$SHARDS/shard-$shard.json" >"$W/shard-$shard.log" 2>&1 &
  pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid" || die "autopsy shard failed pid=$pid"; done
[ "$(find "$SHARDS" -name 'shard-*.json' | wc -l)" -eq "$NSH" ] || die "shard cardinality drift"

stage aggregate-and-classify
args=()
for shard in $(seq 0 $((NSH-1))); do args+=(--shard "$SHARDS/shard-$shard.json"); done
"$PY" jobs/tools/l3_context3_decision_flip_autopsy.py aggregate +  --selection "$ART/selection.json" "${args[@]}" +  --bootstrap-samples "$BOOTSTRAP" --bootstrap-seed "$BOOTSTRAP_SEED" +  --out "$ART/context3-decision-flip-autopsy.json" >"$W/aggregate.log" 2>&1
"$PY" - "$ART/context3-decision-flip-autopsy.json" "$TOTAL" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); r=json.load(open(p)); total=int(sys.argv[2])
assert r['schema']=='jass.l3_context3_decision_flip_autopsy.v1'
assert r['sample']['openings']==total and len(r['rows'])==total
assert r['frozen_read'] is False and r['self_play_games']==0
assert r['patterneval_fits']==0 and r['strength_games']==0
assert r['promotion_authorized'] is False
summary={k:v for k,v in r.items() if k!='rows'}
Path(p.parent/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
Path(p.parent/f"VERDICT__{r['verdict']}").touch()
Path(p.parent/'FROZEN_READ__FALSE').touch()
Path(p.parent/'SELFPLAY__0').touch()
Path(p.parent/'PATTERNEVAL_FITS__0').touch()
Path(p.parent/'STRENGTH_GAMES__0').touch()
Path(p.parent/'PROMOTION_AUTHORIZED__FALSE').touch()
PY
VERDICT=$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
FLIPS=$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["sample"]["flips"])' "$ART/JASS_CONTROL_SUMMARY.json")
say "$VERDICT openings=$TOTAL flips=$FLIPS choice_depth=$CHOICE_DEPTH judge_depth=$JUDGE_DEPTH selfplay=0 fits=0 force_games=0 frozen=false promotion=false"
