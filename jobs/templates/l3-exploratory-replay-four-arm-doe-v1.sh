#!/usr/bin/env bash
# End-to-end exploratory post-CTX4 replay/anchor DOE.
#
# D1 = immutable 1409 corpus, D2 = immutable 1448 fresh-seed corpus.
# Four WDL fits are performed, followed by OLD/NEW static readout and the three
# preregistered force contrasts B-A, B-C and C-D on two fresh disjoint pools.
# CTX4 remains failed. No frozen read, automatic continuation or promotion.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"
IN="$JASS_RESULT_DIR/inputs"
ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"
FORCE="$ART/force"
DATA="$W/data"
mkdir -p "$W" "$IN" "$ART" "$GEOM" "$FORCE" "$DATA"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

D1_JOB="cpx62-1409-l3-context2-intervention-corpus-v1"
D1_ATTEMPT="20260818T184956Z-3465ec72"
D1_CODE="3465ec720eb37c5c9368f2df048831f7381c5839"
D1_ROOT="r2:jass-data/runs/$D1_JOB/$D1_ATTEMPT"
D2_JOB="cpx62-1448-l3-context2-intervention-corpus-fresh2m-exploratory-v2"
D2_ATTEMPT="20260820T215456Z-4652cdc4"
D2_CODE="4652cdc49ec98031247cb21fac8521ffe2522f9c"
D2_ROOT="r2:jass-data/runs/$D2_JOB/$D2_ATTEMPT"
CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE="18c38a33ae78c5c9368f2df048831f7381c5839"
# The previous line is intentionally not trusted; the immutable fetch receipt
# below checks the full actual code SHA from the source run.
CURRICULUM_EXPECTED_CODE="18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_ROOT="r2:jass-data/runs/$CURRICULUM_JOB/$CURRICULUM_ATTEMPT"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
CTX4_JOB="cpx62-1446-l3-context4-uncertainty-screen-v6"
CTX4_ATTEMPT="20260820T193737Z-f206a837"
CTX4_CODE="f206a8373b1324952599bf5f5d93632e52b22e61"
CTX4_ROOT="r2:jass-data/runs/$CTX4_JOB/$CTX4_ATTEMPT"
SMOKE_JOB="cpx62-1426-l3-context3-exact-extras-fit-smoke-v1"
SMOKE_ATTEMPT="20260819T215156Z-040da98c"
SMOKE_CODE="040da98c215bac82b5bc3c97ad1a144d35f7de53"
SMOKE_ROOT="r2:jass-data/runs/$SMOKE_JOB/$SMOKE_ATTEMPT"

EXPECTED_RECORDS=2000000
SPLIT_SEED=577215
HOLDOUT_MOD=10
REPLAY_SEED=2026082106
STATIC_BOOTSTRAP_SEED=2026082109
MAXIT=2000
CHUNK=20000
FIT_TIMEOUT=43200
EXPECTED_EXTRAS=120
NOPEN=1500
CANDIDATES=20000
POOL_SEED_1=2026082116
POOL_SEED_2=2026082117
BOOTSTRAP=100000
NSH=12
PAR=12
FORCE_DEPTH=9
MOVETIME=0.1
CACHE_MB=128
ERROR_LIMIT=120
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
VENV_READY="$VENV/.jass-runtime-ready-v1"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

# Fifteen historical pools + both 1419 pools + both 1428 pools.
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
pool-succession|r2:jass-data/runs/home-0995-l3-pure-turnover-succession-preflight-v2/20260727T054246Z-f20e59d0|artefacts/turnover-succession-openings.fen
pool-context3-1419-force-pool1|r2:jass-data/runs/cpx62-1419-l3-context3-two-pool-force-v1/20260819T112556Z-8adc506a|artefacts/ctx3-force-pool1-openings.fen
pool-context3-1419-force-pool2|r2:jass-data/runs/cpx62-1419-l3-context3-two-pool-force-v1/20260819T112556Z-8adc506a|artefacts/ctx3-force-pool2-openings.fen
pool-context3-1428-force-pool1|r2:jass-data/runs/cpx62-1428-l3-context3-two-pool-force-exact-extras-v2/20260820T005123Z-17517b38|artefacts/ctx3-force-pool1-openings.fen
pool-context3-1428-force-pool2|r2:jass-data/runs/cpx62-1428-l3-context3-two-pool-force-exact-extras-v2/20260820T005123Z-17517b38|artefacts/ctx3-force-pool2-openings.fen"

MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        printf 'models_ready=%s/4\n' "$(find "$W" -maxdepth 1 -name '[ABCD].pjtw' | wc -l)"
        printf 'force_views_ready=%s/12\n' "$(find "$FORCE" -name '*.json' | wc -l)"
      } >"$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 120
    done ) & MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$GEOM" "$W/gate-"* 2>/dev/null || true
  rm -f "$DATA"/*.feat "$DATA"/*.jnnw "$DATA"/*.jsm "$DATA"/*.npy 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-exploratory-replay-four-arm-doe-v1$ ]] || die "invalid job nomenclature"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] || die "frozen-read guard missing"
[ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] || die "promotion guard missing"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
[ -f "$VENV_READY" ] || die "persistent numeric runtime absent"
PY="$VENV/bin/python"
"$PY" -c 'import numpy,scipy; assert numpy.__version__ and scipy.__version__' || die "numeric runtime invalid"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 30720 ] || die "less than 30 GiB free ($DFA MiB)"
say "experiment=EXPLORATORY_POST_CTX4 D1=1409 D2=1448 arms=A,B,C,D target=native_WDL"
say "primary=B_vs_A secondary=B_vs_C,C_vs_D force_openings_per_pool=$NOPEN"
monitor

stage repository-contract-tests
python3 -m py_compile tools/contextual_replay_mix.py \
  jobs/tools/l3_replay_doe_assemble.py \
  jobs/tools/l3_replay_doe_static_readout.py \
  jobs/tools/l3_replay_doe_force_readout.py \
  pattern_jass/tools/train_stream_exact.py
"$PY" -m unittest \
  jobs.tests.test_contextual_replay_mix \
  jobs.tests.test_l3_replay_doe_tools \
  jobs.tests.test_exact_extras_fit_contract >"$W/tests.log" 2>&1

fetch(){
  local root="$1" report="$2"; shift 2
  timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$root" "$@" \
    --out-dir "$IN" --report "$ART/$report" --expected-state completed
}

stage fetch-and-authenticate-immutable-sources
fetch "$D1_ROOT" verified-D1.json \
  --file artefacts/context2-intervention-2m.jnnw.gz=D1.jnnw.gz \
  --file artefacts/context2-intervention-2m.jsm.gz=D1.jsm.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=D1-summary.json >"$W/fetch-D1.log" 2>&1
fetch "$D2_ROOT" verified-D2.json \
  --file artefacts/context2-intervention-2m.jnnw.gz=D2.jnnw.gz \
  --file artefacts/context2-intervention-2m.jsm.gz=D2.jsm.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=D2-summary.json >"$W/fetch-D2.log" 2>&1
fetch "$CURRICULUM_ROOT" verified-curriculum.json \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=curriculum-summary.json >"$W/fetch-curriculum.log" 2>&1
fetch "$CTX4_ROOT" verified-ctx4.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=ctx4-summary.json >"$W/fetch-ctx4.log" 2>&1
fetch "$SMOKE_ROOT" verified-exact-smoke.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=exact-smoke-summary.json >"$W/fetch-smoke.log" 2>&1

"$PY" - "$ART" "$IN" <<'PY'
import json,sys
from pathlib import Path
art,src=map(Path,sys.argv[1:3])
expected={
 'verified-D1.json':('cpx62-1409-l3-context2-intervention-corpus-v1','20260818T184956Z-3465ec72','3465ec720eb37c5c9368f2df048831f7381c5839'),
 'verified-D2.json':('cpx62-1448-l3-context2-intervention-corpus-fresh2m-exploratory-v2','20260820T215456Z-4652cdc4','4652cdc49ec98031247cb21fac8521ffe2522f9c'),
 'verified-curriculum.json':('cpx62-1341-jass-megacorpus-arm-d-fit-v1','20260814T191555Z-18c38a33','18c38a33ae78c9c2e8e2df62fca266da28dacead'),
 'verified-ctx4.json':('cpx62-1446-l3-context4-uncertainty-screen-v6','20260820T193737Z-f206a837','f206a8373b1324952599bf5f5d93632e52b22e61'),
 'verified-exact-smoke.json':('cpx62-1426-l3-context3-exact-extras-fit-smoke-v1','20260819T215156Z-040da98c','040da98c215bac82b5bc3c97ad1a144d35f7de53')}
for name,want in expected.items():
 r=json.load(open(art/name)); got=(r.get('job_id'),r.get('attempt_id'),r.get('code_sha'))
 if got!=want or r.get('result_state')!='completed' or r.get('exit_code')!=0:
  raise SystemExit(f'{name}: identity/state drift {got}')
d1=json.load(open(src/'D1-summary.json')); d2=json.load(open(src/'D2-summary.json'))
cur=json.load(open(src/'curriculum-summary.json')); ctx4=json.load(open(src/'ctx4-summary.json'))
smoke=json.load(open(src/'exact-smoke-summary.json'))
if d1.get('verdict')!='JASS_CONTEXT2_INTERVENTION_CORPUS_READY' or d1.get('records')!=2_000_000: raise SystemExit('D1 contract drift')
if d2.get('verdict')!='JASS_EXPLORATORY_FRESH2M_D2_READY' or d2.get('records')!=2_000_000 or d2.get('experiment_class')!='EXPLORATORY_POST_CTX4': raise SystemExit('D2 contract drift')
if cur.get('verdict')!='JASS_MEGACORPUS_ARM_D_FIT_READY': raise SystemExit('CURRICULUM certificate drift')
if ctx4.get('verdict')!='JASS_CONTEXT4_UNCERTAINTY_DECISION_SCREEN_FAILED' or ctx4.get('next_stage_authorized') is not False: raise SystemExit('CTX4 closure drift')
if smoke.get('verdict')!='JASS_CONTEXT3_EXACT_EXTRAS_FIT_CONTRACT_VERIFIED': raise SystemExit('exact-extras prerequisite drift')
PY

gunzip -t "$IN/D1.jnnw.gz"; gunzip -t "$IN/D1.jsm.gz"
gunzip -t "$IN/D2.jnnw.gz"; gunzip -t "$IN/D2.jsm.gz"
gunzip -t "$IN/curriculum.pjtw.gz"
gunzip -c "$IN/D1.jnnw.gz" >"$W/D1.raw.jnnw"
gunzip -c "$IN/D1.jsm.gz" >"$W/D1.raw.jsm"
gunzip -c "$IN/D2.jnnw.gz" >"$W/D2.raw.jnnw"
gunzip -c "$IN/D2.jsm.gz" >"$W/D2.raw.jsm"
gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
[ "$(sha256sum "$W/curriculum.pjtw" | awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM raw hash drift"
"$PY" jobs/tools/assert_corpus_wdl.py --data "$W/D1.raw.jnnw" >"$W/D1-wdl.log" 2>&1
"$PY" jobs/tools/assert_corpus_wdl.py --data "$W/D2.raw.jnnw" >"$W/D2-wdl.log" 2>&1

stage opening-level-splits
python3 tools/selfplay_frontier.py split --data "$W/D1.raw.jnnw" --meta "$W/D1.raw.jsm" \
  --out-data "$W/D1.split.jnnw" --out-meta "$W/D1.split.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" --manifest "$ART/D1-split.json" >"$W/D1-split.log" 2>&1
python3 tools/selfplay_frontier.py split --data "$W/D2.raw.jnnw" --meta "$W/D2.raw.jsm" \
  --out-data "$W/D2.split.jnnw" --out-meta "$W/D2.split.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" --manifest "$ART/D2-split.json" >"$W/D2-split.log" 2>&1
read -r D1_TRAIN D1_HOLD D2_TRAIN D2_HOLD < <("$PY" - "$ART/D1-split.json" "$ART/D2-split.json" <<'PY'
import json,sys
a,b=(json.load(open(p)) for p in sys.argv[1:3])
for row in (a,b):
 if row.get('records')!=2_000_000 or row.get('split_unit')!='opening_id' or not row.get('tail_is_holdout'):
  raise SystemExit('split contract drift')
print(a['train_records'],a['holdout_records'],b['train_records'],b['holdout_records'])
PY
)
[ "$D1_TRAIN" -gt 0 ] && [ "$D1_HOLD" -gt 0 ] && [ "$D2_TRAIN" -gt 0 ] && [ "$D2_HOLD" -gt 0 ] || die "empty train/holdout"

stage assemble-four-arm-training-corpora
"$PY" jobs/tools/l3_replay_doe_assemble.py \
  --old-data "$W/D1.split.jnnw" --old-meta "$W/D1.split.jsm" --old-split "$ART/D1-split.json" \
  --new-data "$W/D2.split.jnnw" --new-meta "$W/D2.split.jsm" --new-split "$ART/D2-split.json" \
  --out-dir "$DATA" --manifest "$ART/assembly.json" >"$W/assembly.log" 2>&1
"$PY" tools/contextual_replay_mix.py \
  --old-data "$W/D1.split.jnnw" --old-meta "$W/D1.split.jsm" --old-train-count "$D1_TRAIN" \
  --new-data "$W/D2.split.jnnw" --new-meta "$W/D2.split.jsm" --new-train-count "$D2_TRAIN" \
  --old-share 0.25 --new-share 0.75 --seed "$REPLAY_SEED" \
  --out-data "$DATA/BC-replay25.jnnw" --out-meta "$DATA/BC-replay25.jsm" \
  --out-weights "$DATA/BC-replay25-weights.npy" --manifest "$ART/BC-replay25-manifest.json" \
  >"$W/replay-mix.log" 2>&1
"$PY" - "$ART/assembly.json" "$ART/BC-replay25-manifest.json" <<'PY'
import json,sys
a,b=(json.load(open(p)) for p in sys.argv[1:3])
if a.get('holdout_rows_read_into_training')!=0: raise SystemExit('assembly holdout leakage')
if b.get('holdout_rows_read_into_training')!=0: raise SystemExit('replay holdout leakage')
if not b.get('selection',{}).get('whole_opening_groups_only'): raise SystemExit('replay opening-unit drift')
old=b['realised_effective_loss_mass']['OLD']; new=b['realised_effective_loss_mass']['NEW']
if abs(old-.25)>2e-7 or abs(new-.75)>2e-7: raise SystemExit('replay effective mass drift')
full=a['outputs']['D_FULL_HISTORY_NO_PRIOR_train']
if abs(full['realised_effective_loss_mass']['OLD']-.5)>2e-7: raise SystemExit('full-history source mass drift')
PY
rm -f "$W/D1.raw.jnnw" "$W/D1.raw.jsm" "$W/D2.raw.jnnw" "$W/D2.raw.jsm"

stage build-common-engine-and-feature-dumper
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] || die "8cf geometry drift"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON \
  -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests >"$W/build.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB ctest --test-dir "$W/build" --output-on-failure >"$W/ctest.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "missing jass binary"
printf 'hello\nquit\n' | timeout 60 "$J" --pattern "$W/curriculum.pjtw" >"$W/load-curriculum.log" 2>&1
grep -q '^ready' "$W/load-curriculum.log" || die "CURRICULUM does not load"

feature(){
  local name="$1" data="$2"
  stage "features-$name"
  timeout 10800s "$J" --dump-eval-features "$data" "$DATA/$name.feat" >"$W/features-$name.log" 2>&1
  local width
  width=$(python3 -c 'import struct,sys;f=open(sys.argv[1],"rb");assert f.read(4)==b"FEAT";print(struct.unpack("<II",f.read(8))[1])' "$DATA/$name.feat")
  [ "$width" -eq "$EXPECTED_EXTRAS" ] || die "$name feature width=$width"
}
feature A "$DATA/A-current.jnnw"
feature BC "$DATA/BC-replay25.jnnw"
feature D "$DATA/D-full-history.jnnw"
feature OLD-HOLDOUT "$DATA/OLD-holdout.jnnw"
feature NEW-HOLDOUT "$DATA/NEW-holdout.jnnw"

certify_exact_extras(){
  local arm="$1"
  "$PY" - "$W/$arm.pjtw" "$ART/$arm-exact-extras.json" <<'PY'
import json,struct,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,'pattern_jass/tools')
from exact_extras import exact_extras_residuals
p,out=Path(sys.argv[1]),Path(sys.argv[2]); raw=p.read_bytes()
magic,ver,scale,np_,ne=struct.unpack_from('<5I',raw,0)
if magic!=0x57544A50 or (ver&255)!=3 or ne!=120: raise SystemExit('PJTW architecture drift')
base=20+2*np_*4
mg=np.frombuffer(raw,dtype='<i4',count=ne,offset=base).copy()
eg=np.frombuffer(raw,dtype='<i4',count=ne,offset=base+ne*4).copy()
a={'mg':exact_extras_residuals(mg),'eg':exact_extras_residuals(eg)}
if a['mg']['max_abs']!=0 or a['eg']['max_abs']!=0: raise SystemExit(f'exact extras residual {a}')
out.write_text(json.dumps(a,indent=2,sort_keys=True)+'\n')
PY
}

weight_bounds(){
  local manifest="$1"
  "$PY" - "$manifest" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); w=r.get('sample_weights') or r.get('outputs',{}).get('D_FULL_HISTORY_NO_PRIOR_train',{}).get('sample_weights')
if not w: raise SystemExit('missing sample weight certificate')
print(w['min'],w['max'])
PY
}

fit_arm(){
  local arm="$1" data="$2" feat="$3" weights="$4" manifest="$5" prior="$6"
  stage "fit-$arm"
  local args=(--data "$data" --feat "$feat" --out "$W/$arm.pjtw"
    --target wdl --loss logistic --exact-fold --tempo-stage
    --l2 1e-5 --max-iter "$MAXIT" --chunk "$CHUNK"
    --lbfgs-maxcor 20 --lbfgs-gtol 1e-4 --prune
    --optimizer-report "$ART/$arm-optimizer.json")
  if [ "$prior" = yes ]; then args+=(--prior-mean "$W/curriculum.pjtw" --prior-decay 0); fi
  if [ "$weights" != none ]; then
    read -r wmin wmax < <(weight_bounds "$manifest")
    args+=(--sample-weights "$weights" --weight-min "$wmin" --weight-max "$wmax" --weights-report "$ART/$arm-weights.json")
  fi
  /usr/bin/time -f '%e' -o "$W/fit-$arm.seconds" timeout "$FIT_TIMEOUT" \
    env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" PYTHONUNBUFFERED=1 \
    "$PY" pattern_jass/tools/train_stream_exact.py "${args[@]}" >"$W/fit-$arm.log" 2>&1
  [ -s "$W/$arm.pjtw" ] || die "$arm produced no model"
  "$PY" jobs/tools/verify_optimizer_convergence.py --report "$ART/$arm-optimizer.json" \
    --label "$arm" --expected-max-iterations "$MAXIT" --expected-maxcor 20 \
    --expected-gtol 1e-4 --receipt "$ART/$arm-convergence.json"
  certify_exact_extras "$arm"
  gzip -n -c "$W/$arm.pjtw" >"$ART/$arm.pjtw.gz"
}

stage sequential-four-arm-fits
fit_arm A "$DATA/A-current.jnnw" "$DATA/A.feat" none none yes
fit_arm B "$DATA/BC-replay25.jnnw" "$DATA/BC.feat" "$DATA/BC-replay25-weights.npy" "$ART/BC-replay25-manifest.json" yes
fit_arm C "$DATA/BC-replay25.jnnw" "$DATA/BC.feat" "$DATA/BC-replay25-weights.npy" "$ART/BC-replay25-manifest.json" no
fit_arm D "$DATA/D-full-history.jnnw" "$DATA/D.feat" "$DATA/D-full-history-weights.npy" "$ART/assembly.json" no

stage old-new-static-readout
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools:jobs/tools" \
  "$PY" jobs/tools/l3_replay_doe_static_readout.py \
  --old-data "$DATA/OLD-holdout.jnnw" --old-meta "$DATA/OLD-holdout.jsm" --old-feat "$DATA/OLD-HOLDOUT.feat" \
  --new-data "$DATA/NEW-holdout.jnnw" --new-meta "$DATA/NEW-holdout.jsm" --new-feat "$DATA/NEW-HOLDOUT.feat" \
  --model "A=$W/A.pjtw" --model "B=$W/B.pjtw" --model "C=$W/C.pjtw" --model "D=$W/D.pjtw" \
  --contrast B:A --contrast B:C --contrast C:D \
  --bootstrap-samples 10000 --bootstrap-seed "$STATIC_BOOTSTRAP_SEED" \
  --out "$ART/static-readout.json" >"$W/static-readout.log" 2>&1

stage publish-four-model-certificate
"$PY" - "$W" "$ART" "$EXPECTED_CODE_SHA" "$CURRICULUM_SHA" <<'PY' | tee -a "$RES"
import hashlib,json,struct,sys
from pathlib import Path
w,art=Path(sys.argv[1]),Path(sys.argv[2]); code,parent_sha=sys.argv[3:5]
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1<<20),b''): h.update(block)
 return h.hexdigest()
def structure(path):
 raw=Path(path).read_bytes(); magic,version,scale,np_,ne=struct.unpack_from('<5I',raw,0)
 if magic!=0x57544A50 or (version&255)!=3 or scale<=0 or np_!=4251528 or ne!=120 or len(raw)!=20+8*(np_+ne): raise SystemExit(f'{path}: structure drift')
 return {'version':version,'scale':scale,'n_patterns':np_,'n_extras':ne,'size_bytes':len(raw)}
models={}
for arm in 'ABCD':
 exact=json.load(open(art/f'{arm}-exact-extras.json'))
 if exact['mg']['max_abs']!=0 or exact['eg']['max_abs']!=0: raise SystemExit(f'{arm}: exact extras drift')
 models[arm]={'model_raw_sha256':sha(w/f'{arm}.pjtw'),'model_gz_sha256':sha(art/f'{arm}.pjtw.gz'),
  'structure':structure(w/f'{arm}.pjtw'),'optimizer':json.load(open(art/f'{arm}-optimizer.json')),
  'convergence':json.load(open(art/f'{arm}-convergence.json')),'exact_extras':exact,
  'fit_seconds':float((w/f'fit-{arm}.seconds').read_text()),
  'prior_mean':('CURRICULUM' if arm in 'AB' else None)}
payload={'schema':'jass.l3_exploratory_replay_four_models.v1',
 'verdict':'JASS_EXPLORATORY_REPLAY_FOUR_MODELS_READY','experiment_class':'EXPLORATORY_POST_CTX4',
 'ctx4_verdict_unchanged':'JASS_CONTEXT4_UNCERTAINTY_DECISION_SCREEN_FAILED','code_sha':code,
 'sources':{'D1':'1409','D2':'1448','parent':{'label':'CURRICULUM','raw_sha256':parent_sha}},
 'target':'native_JNNW_WDL','split':{'seed':577215,'holdout_mod':10},'replay_seed':2026082106,
 'arms':{'A':{'label':'CURRENT','data':'all_D2_train','effective_mass':{'NEW':1.0},'prior':'CURRICULUM'},
         'B':{'label':'REPLAY25','data':'all_D2_plus_D1_opening_replay','effective_mass':{'NEW':.75,'OLD':.25},'prior':'CURRICULUM'},
         'C':{'label':'REPLAY25_NO_PRIOR','data':'identical_to_B','effective_mass':{'NEW':.75,'OLD':.25},'prior':None},
         'D':{'label':'FULL_HISTORY_NO_PRIOR','data':'all_D1_and_D2_train','effective_mass':{'NEW':.5,'OLD':.5},'prior':None}},
 'models':models,'static_readout':json.load(open(art/'static-readout.json')),
 'fit_recipe':{'architecture':'8cf_exact_fold_tempo_120_extras','target':'wdl','l2':1e-5,'gtol':1e-4,'max_iterations':2000,'lbfgs_maxcor':20,'dense_extras_constraint':'projected_inside_fit'},
 'primary_force_contrast':'B_vs_A','secondary_force_contrasts':['B_vs_C','C_vs_D'],
 'strength_games_played':0,'frozen_cohorts_read':0,'promotion_authorized':False,'automatic_next_job':None}
(art/'model-certificate.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/'VERDICT__JASS_EXPLORATORY_REPLAY_FOUR_MODELS_READY').touch()
print(json.dumps(payload,sort_keys=True))
PY

for arm in A B C D; do
  printf 'hello\nquit\n' | timeout 60 "$J" --pattern "$W/$arm.pjtw" >"$W/load-$arm.log" 2>&1
  grep -q '^ready' "$W/load-$arm.log" || die "$arm model does not load"
done

stage fetch-historical-force-pools
EXCL_ARGS=(); EXCL_NAMES=()
while IFS='|' read -r label prefix remote_path; do
  [ -n "${label:-}" ] || continue
  python3 jobs/tools/fetch_result_files.py --prefix "$prefix" \
    --file "$remote_path=$label.fen" --out-dir "$IN" \
    --report "$ART/verified-exclude-$label.json" --expected-state completed \
    >"$W/fetch-$label.log" 2>&1 || die "historical pool fetch failed: $label"
  EXCL_ARGS+=(--exclude "$IN/$label.fen"); EXCL_NAMES+=("$label")
done <<<"$EXCLUDE_SPECS"
[ "${#EXCL_NAMES[@]}" -eq 19 ] || die "historical exclusion count drift"

generate_pool(){
  local index="$1" seed="$2" out="replay-doe-pool${index}-openings"
  local extra=("${EXCL_ARGS[@]}")
  if [ "$index" -eq 2 ]; then extra+=(--exclude "$ART/replay-doe-pool1-openings.fen"); fi
  for pass in a b; do
    "$J" --gen-opening-pool "$CANDIDATES" "$W/pool${index}-cand-$pass.fen" 8 32 20 "$seed" >"$W/pool${index}-gen-$pass.log" 2>&1
  done
  cmp -s "$W/pool${index}-cand-a.fen" "$W/pool${index}-cand-b.fen" || die "pool$index candidates nondeterministic"
  python3 jobs/tools/select_independent_opening_pool.py --candidates "$W/pool${index}-cand-a.fen" \
    --expected "$NOPEN" "${extra[@]}" --generator-seed "$seed" \
    --out "$ART/$out.fen" --manifest "$ART/$out.json" >"$W/pool${index}-select.log" 2>&1
  python3 jobs/tools/validate_opening_pool.py --pool "$ART/$out.fen" --expected "$NOPEN" \
    --generator-seed "$seed" "${extra[@]}" --out "$ART/$out-provenance.json" >"$W/pool${index}-validate.log" 2>&1
}

stage generate-two-fresh-force-pools
generate_pool 1 "$POOL_SEED_1"
generate_pool 2 "$POOL_SEED_2"
COMMON=$(grep -Fx -f "$ART/replay-doe-pool1-openings.fen" "$ART/replay-doe-pool2-openings.fen" | grep -c . || true)
[ "$COMMON" -eq 0 ] || die "fresh force pools overlap by $COMMON"
for index in 1 2; do
 file="$ART/replay-doe-pool${index}-openings.fen"
 [ "$(grep -c . "$file" || true)" -eq "$NOPEN" ] || die "pool$index cardinality drift"
 for label in "${EXCL_NAMES[@]}"; do
  overlap=$(grep -Fx -f "$IN/$label.fen" "$file" | grep -c . || true)
  [ "$overlap" -eq 0 ] || die "pool$index overlaps $label by $overlap"
 done
done

"$PY" - "$ART" "$NOPEN" "$POOL_SEED_1" "$POOL_SEED_2" "${EXCL_NAMES[@]}" <<'PY'
import hashlib,json,sys
from pathlib import Path
art=Path(sys.argv[1]); n=int(sys.argv[2]); seeds=list(map(int,sys.argv[3:5])); exclusions=sys.argv[5:]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p): return [x for raw in p.read_text().splitlines() if (x:=raw.split('#',1)[0].strip())]
pools=[]; sets=[]
for i,seed in enumerate(seeds,1):
 stem=art/f'replay-doe-pool{i}-openings'; fen=stem.with_suffix('.fen'); values=rows(fen)
 manifest=json.load(open(stem.with_suffix('.json'))); provenance=json.load(open(art/f'{stem.name}-provenance.json'))
 digest=sha(fen)
 if len(values)!=n or len(set(values))!=n or manifest.get('sha256')!=digest or manifest.get('generator_seed')!=seed or manifest.get('overlap_records')!=0 or provenance.get('overlap_records')!=0: raise SystemExit(f'pool{i}: certificate drift')
 sets.append(set(values)); pools.append({'pool_index':i,'openings':n,'seed':seed,'sha256':digest,'fen':fen.name})
if sets[0]&sets[1]: raise SystemExit('fresh pools overlap')
payload={'schema':'jass.l3_exploratory_replay_doe_pools.v1','verdict':'JASS_EXPLORATORY_REPLAY_DOE_TWO_POOLS_READY','pools':pools,'mutually_disjoint':True,'mutual_overlap':0,'historical_exclusions':exclusions,'historical_exclusion_count':len(exclusions),'all_historical_overlaps_zero':True,'deterministic_generation_repeated':True,'promotion_authorized':False}
(art/'pool-certificate.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY

stage publish-locked-force-protocol
cat >"$ART/force-protocol.json" <<'JSON'
{
  "schema": "jass.l3_exploratory_replay_doe_force_protocol.v1",
  "openings_per_pool": 1500,
  "bootstrap_samples": 100000,
  "primary_contrast": "B_vs_A",
  "contrasts": {
    "B_vs_A": {
      "candidate": "B", "baseline": "A",
      "gate_seeds": {"pool1": {"native": 2026082120, "q00": 2026082121}, "pool2": {"native": 2026082122, "q00": 2026082123}},
      "combined_seeds": {"native": 2026082124, "q00": 2026082125}
    },
    "B_vs_C": {
      "candidate": "B", "baseline": "C",
      "gate_seeds": {"pool1": {"native": 2026082130, "q00": 2026082131}, "pool2": {"native": 2026082132, "q00": 2026082133}},
      "combined_seeds": {"native": 2026082134, "q00": 2026082135}
    },
    "C_vs_D": {
      "candidate": "C", "baseline": "D",
      "gate_seeds": {"pool1": {"native": 2026082140, "q00": 2026082141}, "pool2": {"native": 2026082142, "q00": 2026082143}},
      "combined_seeds": {"native": 2026082144, "q00": 2026082145}
    }
  },
  "paired_colours": true,
  "native_movetime_seconds": 0.1,
  "q00_depth": 9,
  "native_is_primary": true,
  "q00_can_override_native": false,
  "promotion_authorized": false
}
JSON

run_gate(){
  local contrast="$1" candidate="$2" baseline="$3" pool="$4" view="$5" seed="$6"
  local budget=(); [ "$view" = native ] && budget=(--movetime "$MOVETIME") || budget=(--depth "$FORCE_DEPTH")
  timeout -k 120s 25200s "$PY" jobs/tools/run_jass_gate_bounded.py \
    --jass "$J" --pattern-a "$W/$candidate.pjtw" --pattern-b "$W/$baseline.pjtw" \
    --search-params-a "$Q00" --search-params-b "$Q00" \
    --openings-file "$ART/replay-doe-pool${pool}-openings.fen" "${budget[@]}" --pairs 1 \
    --max-plies 160 --nshards "$NSH" --max-parallel "$PAR" --timeout 21600 --game-timeout 180 \
    --paired-bootstrap-samples "$BOOTSTRAP" --paired-bootstrap-seed "$seed" \
    --work-dir "$W/gate-$contrast-pool$pool-$view" --out "$FORCE/$contrast-pool$pool-$view.json" \
    >"$W/force-$contrast-pool$pool-$view.log" 2>&1
}

seed_for(){
 "$PY" - "$ART/force-protocol.json" "$1" "$2" "$3" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); print(r['contrasts'][sys.argv[2]]['gate_seeds'][f'pool{sys.argv[3]}'][sys.argv[4]])
PY
}

for spec in "B_vs_A B A" "B_vs_C B C" "C_vs_D C D"; do
 read -r contrast candidate baseline <<<"$spec"
 for pool in 1 2; do
  for view in native q00; do
   seed=$(seed_for "$contrast" "$pool" "$view")
   stage "force-$contrast-pool$pool-$view"
   run_gate "$contrast" "$candidate" "$baseline" "$pool" "$view" "$seed" || die "$contrast pool$pool $view failed"
   say "$contrast pool=$pool view=$view games=$((2*NOPEN)) complete"
  done
 done
done

stage audit-and-publish-terminal-doe-readout
"$PY" jobs/tools/l3_replay_doe_force_readout.py \
  --protocol "$ART/force-protocol.json" --pool-certificate "$ART/pool-certificate.json" \
  --model-certificate "$ART/model-certificate.json" \
  --gate "B_vs_A:1:native=$FORCE/B_vs_A-pool1-native.json" --gate "B_vs_A:1:q00=$FORCE/B_vs_A-pool1-q00.json" \
  --gate "B_vs_A:2:native=$FORCE/B_vs_A-pool2-native.json" --gate "B_vs_A:2:q00=$FORCE/B_vs_A-pool2-q00.json" \
  --gate "B_vs_C:1:native=$FORCE/B_vs_C-pool1-native.json" --gate "B_vs_C:1:q00=$FORCE/B_vs_C-pool1-q00.json" \
  --gate "B_vs_C:2:native=$FORCE/B_vs_C-pool2-native.json" --gate "B_vs_C:2:q00=$FORCE/B_vs_C-pool2-q00.json" \
  --gate "C_vs_D:1:native=$FORCE/C_vs_D-pool1-native.json" --gate "C_vs_D:1:q00=$FORCE/C_vs_D-pool1-q00.json" \
  --gate "C_vs_D:2:native=$FORCE/C_vs_D-pool2-native.json" --gate "C_vs_D:2:q00=$FORCE/C_vs_D-pool2-q00.json" \
  --out "$ART/replay-doe-terminal-readout.json" >"$W/terminal-readout.log" 2>&1
cp "$ART/replay-doe-terminal-readout.json" "$ART/JASS_CONTROL_SUMMARY.json"
VERDICT=$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
: >"$ART/VERDICT__$VERDICT"
: >"$ART/EXPERIMENT_CLASS__EXPLORATORY_POST_CTX4"
: >"$ART/CTX4_VERDICT_UNCHANGED__FAILED"
: >"$ART/FITS_RUN__4"
: >"$ART/FORCE_GAMES_PLAYED__36000"
: >"$ART/FROZEN_READ__FALSE"
: >"$ART/PROMOTION_AUTHORIZED__FALSE"
: >"$ART/AUTOMATIC_NEXT_JOB__NULL"
stage completed
say "$VERDICT fits=4 force_games=36000 frozen=false promotion=false automatic_next_job=null"
