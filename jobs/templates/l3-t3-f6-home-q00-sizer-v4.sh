#!/usr/bin/env bash
# HOME-only technical Q00 depth-9 sizer for the frozen T3-A/F6 v4 runtime.
# Reuses already-consumed R0-v4 positions; publishes telemetry only, no strength.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_HOST:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${R0_RESULT_PREFIX:?}"
: "${FULL_RUN_APPROVED:?}"; : "${TECHNICAL_GO:?}"

R0_JOB="cpx62-1685-l3-t3-f6-runtime-r0-v4"
R0_ATTEMPT="20260830T083226Z-0ead13cb"
R0_CODE_SHA="0ead13cb3579ce83c1278fe21c6634096d5e8eec"
R0_PREFIX="r2:jass-data/runs/${R0_JOB}/${R0_ATTEMPT}"
MODEL_SHA="16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
IN="$JASS_RESULT_DIR/inputs"
ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
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
      printf 'technical_only=true\n'
      printf 'strength_games=0\n'
    } >"$PROG.tmp"
    mv "$PROG.tmp" "$PROG"
    cp "$PROG" "$ART/PROGRESS.txt"
    sleep 60
  done) & MON="$!"
}
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^home-[0-9]+-l3-t3-f6-v4-q00-sizer$ ]] || die "HOME job nomenclature drift"
[ "$(hostname)" = "$EXPECTED_HOST" ] || die "HOME host mismatch"
[ "$EXPECTED_HOST" = "User" ] || die "expected HOME hostname drift"
[ "$(nproc)" -eq 16 ] || die "HOME 16-CPU contract mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "dirty/non-detached worktree"
[ "$FULL_RUN_APPROVED" = 1 ] && [ "$TECHNICAL_GO" = 1 ] || die "explicit technical execution GO missing"
[ "$R0_RESULT_PREFIX" = "$R0_PREFIX" ] || die "R0-v4 source prefix drift"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 63-parameter contract drift"
for command in python3 rclone sha256sum gunzip timeout df; do
  command -v "$command" >/dev/null || die "$command missing"
done
DFA=$(df -Pm /root | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 3000 ] || die "HOME disk free below 3 GiB"
say "host=$(hostname) nproc=$(nproc) disk_free_mb=$DFA"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/t3_f6_home_q00_sizer_v4.py jobs/tools/t3_f6_search_profile.py
python3 -m unittest jobs.tests.test_t3_f6_home_q00_sizer_v4 -v >"$W/unit-tests.log" 2>&1

stage fetch-authenticate-consumed-r0-v4
python3 jobs/tools/fetch_result_files.py --prefix "$R0_RESULT_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=r0-summary.json \
  --file artefacts/jass-t3-f6-force.gz=jass-t3-f6-force.gz \
  --file artefacts/t3-a-f6-only.json=t3-a-f6-only.json \
  --file artefacts/curriculum.pjtw=curriculum.pjtw \
  --file artefacts/r0-corpus.fen=r0-corpus.fen \
  --out-dir "$IN" --report "$ART/verified-r0.json" >"$W/fetch-r0.log" 2>&1 \
  || die "R0-v4 fetch failed"
gunzip -t "$IN/jass-t3-f6-force.gz"
gunzip -c "$IN/jass-t3-f6-force.gz" >"$W/jass"
chmod 0555 "$W/jass"
J="$W/jass"
python3 - "$IN" "$ART" "$R0_JOB" "$R0_ATTEMPT" "$R0_CODE_SHA" "$MODEL_SHA" "$CURRICULUM_SHA" "$Q00" <<'PY_AUTH'
import hashlib,json,sys
from pathlib import Path
root,art=map(Path,sys.argv[1:3]); job,attempt,code,model,curr,q00=sys.argv[3:]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
r=json.loads((art/'verified-r0.json').read_text())
s=json.loads((root/'r0-summary.json').read_text())
if (r.get('job_id'),r.get('attempt_id'),r.get('code_sha')) != (job,attempt,code):
    raise SystemExit('R0 source identity drift')
if r.get('result_state')!='completed' or r.get('exit_code')!=0:
    raise SystemExit('R0 source is not completed/healthy')
if s.get('verdict')!='R0_V4_PRODUCTION_LEAF_CONTRACT_ESTABLISHED':
    raise SystemExit('R0-v4 terminal verdict drift')
if s.get('passed') is not True or s.get('pool1_authorized') is not True:
    raise SystemExit('R0-v4 Pool1 authorization missing')
if s.get('code_sha')!=code:
    raise SystemExit('R0-v4 code identity drift')
if sha(root/'t3-a-f6-only.json')!=model or s.get('artifact_sha256')!=model:
    raise SystemExit('T3-A frozen bytes drift')
if sha(root/'curriculum.pjtw')!=curr or s.get('curriculum_sha256')!=curr:
    raise SystemExit('CURRICULUM frozen bytes drift')
selection=s.get('selection',{})
if sha(root/'r0-corpus.fen')!=selection.get('fen_sha256'):
    raise SystemExit('consumed R0-v4 corpus SHA drift')
contract=s.get('runtime_contract',{})
if contract.get('search_params')!=q00:
    raise SystemExit('authenticated R0-v4 Q00 vector drift')
if contract.get('threads')!=1 or contract.get('tt_mb')!=16 or contract.get('book')!='OFF':
    raise SystemExit('authenticated R0-v4 search runtime contract drift')
exe=root.parent/'work'/'jass'
if sha(exe)!=s.get('executable_sha256'):
    raise SystemExit('R0-v4 executable bytes drift')
PY_AUTH

stage loader-and-home-egdb-smoke
printf 'hello\nquit\n' | env -u JASS_T3_F6_MODEL "$J" --pattern "$IN/curriculum.pjtw" >"$W/load-off.log" 2>&1
printf 'hello\nquit\n' | env JASS_T3_F6_MODEL="$IN/t3-a-f6-only.json" "$J" --pattern "$IN/curriculum.pjtw" >"$W/load-on.log" 2>&1
grep -q '^ready' "$W/load-off.log" && grep -q '^ready' "$W/load-on.log" || die "exact R0-v4 binary loader smoke failed"
EGDIR=""
for directory in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$directory"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$directory"; break; }
done
[ -n "$EGDIR" ] || die "real HOME EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB=128
say "egdb_path=$EGDIR egdb_cache_mb=128"

stage q00-depth9-telemetry-only-sizer
unset JASS_T3_F6_MODEL
TIME0=$(date +%s)
timeout -k 120s 1800s python3 jobs/tools/t3_f6_home_q00_sizer_v4.py \
  --exe "$J" --curriculum "$IN/curriculum.pjtw" --model "$IN/t3-a-f6-only.json" \
  --corpus "$IN/r0-corpus.fen" --search-params "$Q00" --out "$ART/q00-technical-sizer.json" \
  >"$W/q00-sizer.log" 2>&1 || die "HOME Q00 technical sizer failed"
TIME1=$(date +%s)
WALL=$((TIME1-TIME0))

stage validate-no-strength-output
python3 - "$ART/q00-technical-sizer.json" <<'PY_VALIDATE'
import json,sys
p=json.load(open(sys.argv[1]))
def require(condition,message):
    if not condition:
        raise SystemExit(message)
require(p.get('schema')=='jass.t3_f6_home_q00_technical_sizer.v4','sizer schema drift')
require(p.get('passed') is True and p.get('verdict')=='HOME_Q00_V4_TECHNICAL_SIZER_PASS','sizer verdict drift')
require(p.get('technical_only') is True and p.get('source')=='consumed_r0_v4_corpus','technical source drift')
require(p.get('source_pool1_excluded') is True,'Pool1 exclusion receipt missing')
require(p.get('q00_depth')==9 and p.get('order_seed')==2026092505,'Q00 depth/order drift')
require(p.get('roots')==16 and p.get('roots_by_phase')=={'P0':8,'P1':8},'technical root contract drift')
require(p.get('score_values_published') is False and p.get('best_moves_published') is False,'score/move suppression drift')
require(p.get('wdl_published') is False and p.get('strength_games')==0,'strength output drift')
require(p.get('pool_decision_authorized') is False,'technical sizer cannot authorize Pool1')
require(p.get('training') is False and p.get('tuning') is False,'training/tuning drift')
require(p.get('bake') is False and p.get('promotion') is False,'bake/promotion drift')
for arm in ('curriculum_off','t3_f6_on'):
    q=p.get('search_profile',{}).get(arm,{})
    require(q.get('searches')==16 and q.get('nodes',0)>0 and q.get('eval_calls',0)>0 and q.get('wall_seconds',0)>0,
            f'{arm} telemetry incomplete')
require(p.get('wall_ratio_t3_over_curriculum',0)>0 and p.get('nps_ratio_t3_over_curriculum',0)>0,
        'technical ratio receipt invalid')
PY_VALIDATE

for marker in \
  TECHNICAL_ONLY__TRUE STRENGTH_GAMES__0 SCORES_PUBLISHED__FALSE BESTMOVES_PUBLISHED__FALSE \
  WDL_PUBLISHED__FALSE POOL_DECISION_AUTHORIZED__FALSE TRAINING__FALSE TUNING__FALSE \
  BAKE__FALSE PROMOTION__FALSE VERDICT__HOME_Q00_V4_TECHNICAL_SIZER_PASS; do
  : >"$ART/$marker"
done
say "HOME_Q00_V4_TECHNICAL_SIZER_PASS wall_seconds=$WALL roots=16 depth=9 strength_games=0"
stage done
