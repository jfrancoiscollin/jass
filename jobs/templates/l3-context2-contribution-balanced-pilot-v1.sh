#!/usr/bin/env bash
# Generate the preregistered 600k CTX2 contribution-balanced pilot corpus.
# Generation only: no mapper/PatternEval fit, force game, frozen read or promotion.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$IN/seeds" "$ART/cells" "$GEOM"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; cp "$STAGE" "$ART/STAGE.txt"; }

SEED_ROOT="r2:jass-data/runs/cpx62-1414b-l3-context2-contribution-seed-miner-v2/20260818T222026Z-f614cb53"
SEED_JOB="cpx62-1414b-l3-context2-contribution-seed-miner-v2"
SEED_ATTEMPT="20260818T222026Z-f614cb53"
SEED_CODE_SHA="f614cb533b1f39e131f577069018ea5a866274e6"
CURRICULUM_ROOT="r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/20260814T191555Z-18c38a33"
CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE_SHA="18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
CELL_NAMES="blocked_man center_presence king_centrality king_safe_mobility legal_capture_option neutral"
PRODUCERS=12; PREFLIGHT_RECORDS=10000; CELL_RECORDS=100000
CONTENTION=1.174; MAX_BUDGET_MIN=45; FRESH_SEED=2026081807
LABEL_DEPTH=4; PLAY_DEPTH=8; MAXPLIES=260
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        printf 'cells_done=%s\n' "$(find "$ART/cells" -name '*-merge.json' 2>/dev/null | wc -l || true)"
      } >"$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120
    done ) & MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$W/cells" "$W"/*.jnnw "$W"/*.jsm 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-1415-l3-context2-contribution-balanced-pilot-v1$ ]] || die "invalid job nomenclature"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "explicit execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "persistent numeric runtime absent; do not reinstall"
PY="$VENV/bin/python"; "$PY" -c 'import numpy; assert numpy.__version__'

stage repository-and-disk-contracts
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 10240 ] || die "less than 10 GiB free ($DFA MiB)"
python3 -m py_compile jobs/tools/l3_context2_contribution_balanced_corpus_audit.py
"$PY" -m unittest jobs.tests.test_l3_context2_contribution_balanced_corpus_audit \
  jobs.tests.test_l3_context2_contribution_balanced_pilot_template >"$W/tests.log" 2>&1
say "host=cpx62 nproc=16 producers=$PRODUCERS target_records=600000 preflight_per_cell=10000 budget_min=45"
monitor

stage fetch-and-authenticate-seeds-and-curriculum
seed_args=()
for name in $CELL_NAMES; do seed_args+=(--file "artefacts/$name.jnnw.gz=$name.jnnw.gz"); done
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$SEED_ROOT" \
  "${seed_args[@]}" \
  --file artefacts/context2-contribution-seeds.json=seed-manifest.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=seed-summary.json \
  --out-dir "$IN" --report "$ART/verified-seeds.json" --expected-state completed >"$W/fetch-seeds.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" --expected-state completed >"$W/fetch-curriculum.log" 2>&1
"$PY" - "$ART" "$IN" "$SEED_JOB" "$SEED_ATTEMPT" "$SEED_CODE_SHA" \
  "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" "$CURRICULUM_CODE_SHA" <<'PY'
import json,sys
from pathlib import Path
art,src=map(Path,sys.argv[1:3]); ids=sys.argv[3:]
for name,expected in (('verified-seeds.json',tuple(ids[:3])),('verified-curriculum.json',tuple(ids[3:6]))):
 row=json.load(open(art/name)); got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha'))
 if got!=expected or row.get('result_state')!='completed' or row.get('exit_code')!=0: raise SystemExit(f'{name}: source identity/state drift {got}')
s=json.load(open(src/'seed-summary.json')); m=json.load(open(src/'seed-manifest.json'))
if s.get('verdict')!='JASS_CONTEXT2_CONTRIBUTION_SEEDS_READY' or m.get('verdict')!='JASS_CONTEXT2_CONTRIBUTION_SEEDS_READY': raise SystemExit('seed certificate drift')
if m.get('guards',{}).get('exact_records_total')!=24576 or len(m.get('pools',{}))!=6: raise SystemExit('seed count drift')
PY
for name in $CELL_NAMES; do
  gunzip -c "$IN/$name.jnnw.gz" >"$IN/seeds/$name.jnnw"
done
gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
[ "$(sha256sum "$W/curriculum.pjtw" | awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM hash drift"
"$PY" - "$IN" <<'PY'
import hashlib,json,struct,sys
from pathlib import Path
root=Path(sys.argv[1]); manifest=json.load(open(root/'seed-manifest.json'))
for name,row in manifest['pools'].items():
 path=root/'seeds'/f'{name}.jnnw'; raw=path.read_bytes(); magic,count=struct.unpack_from('<4sI',raw)
 if magic!=b'JNNW' or count!=4096 or len(raw)!=8+count*38: raise SystemExit(f'{name}: JNNW shape drift')
 if hashlib.sha256(raw).hexdigest()!=row['sha256']: raise SystemExit(f'{name}: seed hash drift')
 if any(raw[8+i*38+33:8+(i+1)*38]!=b'\0\0\0\0\0' for i in range(count)): raise SystemExit(f'{name}: target leakage')
PY

stage build-production-engine-and-roundtrip-seeds
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
timeout 1800s cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
timeout 3600s cmake --build "$W/build" -j16 --target jass jass_tests >"$W/build.log" 2>&1
J="$W/build/jass"; "$W/build/jass_tests" >"$W/cpp-tests.log" 2>&1
printf 'hello\nquit\n' | timeout 60s "$J" --pattern "$W/curriculum.pjtw" >"$W/load.log" 2>&1
grep -q '^ready' "$W/load.log" || die "CURRICULUM cannot be loaded"
for name in $CELL_NAMES; do
  timeout 300s "$J" --dump-conditional-context-v2 "$IN/seeds/$name.jnnw" "$W/seed-$name.feat" >"$W/seed-$name.log" 2>&1
done

gen_one(){ # out count seed seed_file log timeout
  local out="$1" count="$2" seed="$3" seed_file="$4" log="$5" limit="$6"
  timeout -k 30s "${limit}s" "$J" --gen-data-wdl "$count" "$out" \
    "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" "$seed" \
    --nnue "$W/curriculum.pjtw" --search-params-play "$Q00" --wdl-zero-score \
    --seed-file "$seed_file" --seed-frac 100 \
    --random-open-plies 8 --explore-eps 8 --explore-decay-plies 60 \
    --explore-topk 3 --explore-margin 30 --split-selfplay-rngs \
    --pair-openings --drop-plycap --sample-meta-out "${out%.jnnw}.jsm" --sample-meta-format jsm2 \
    >"$log" 2>&1 < /dev/null
}
check_log(){
  local log="$1"
  grep -q 'label_score_searches=0' "$log" && grep -q 'split_selfplay_rngs=1' "$log" \
    && grep -q 'seed_frac=100' "$log" && grep -q 'explore_topk=3' "$log" \
    && grep -q 'explore_margin=30' "$log" || die "$log: generator contract drift"
}

stage exact-10k-per-cell-preflight
mkdir -p "$W/preflight"; : >"$W/preflight-rates.tsv"; index=0
pf_args=()
for name in $CELL_NAMES; do
  t0=$(date +%s)
  gen_one "$W/preflight/$name.jnnw" "$PREFLIGHT_RECORDS" $((FRESH_SEED-1000+index)) \
    "$IN/seeds/$name.jnnw" "$W/preflight/$name.log" 1800 || die "$name preflight failed"
  elapsed=$(( $(date +%s)-t0 )); check_log "$W/preflight/$name.log"
  "$PY" jobs/tools/assert_corpus_wdl.py --data "$W/preflight/$name.jnnw" --max-side-skew 0.02 >"$W/preflight/$name-wdl.log" 2>&1
  timeout 600s "$J" --dump-conditional-context-v2 "$W/preflight/$name.jnnw" "$W/preflight/$name.feat" >"$W/preflight/$name-parser.log" 2>&1
  printf '%s\t%s\n' "$name" "$elapsed" >>"$W/preflight-rates.tsv"
  pf_args+=(--cell "$name=$W/preflight/$name.jnnw"); index=$((index+1))
done
"$PY" jobs/tools/l3_context2_contribution_balanced_corpus_audit.py "${pf_args[@]}" \
  --expected-per-cell "$PREFLIGHT_RECORDS" --code-sha "$EXPECTED_CODE_SHA" \
  --fresh-seed "$FRESH_SEED" --seed-source "$SEED_JOB/$SEED_ATTEMPT" \
  --out "$ART/preflight-distribution.json" >"$W/preflight-audit.log"
"$PY" - "$W/preflight-rates.tsv" "$PREFLIGHT_RECORDS" "$CELL_RECORDS" "$PRODUCERS" \
  "$CONTENTION" "$MAX_BUDGET_MIN" "$ART/preflight-budget.json" "$W/runtime-limits.tsv" <<'PY' | tee -a "$RES"
import json,math,sys
rates,per,target,producers,contention,budget,out,limits=sys.argv[1:]
per,target,producers=int(per),int(target),int(producers); contention,budget=float(contention),float(budget)
rows=[]; total=0.0
for raw in open(rates):
 name,seconds=raw.split(); seconds=max(1,int(seconds)); solo=per/(seconds/60); parallel=solo/contention*producers
 minutes=target/parallel; timeout_s=min(2700,max(300,int(math.ceil(minutes*60*1.40+120))))
 rows.append({'cell':name,'preflight_records':per,'preflight_seconds':seconds,'projected_minutes':minutes,'shard_timeout_seconds':timeout_s}); total+=minutes
with open(limits,'w') as f:
 for row in rows: f.write(f"{row['cell']}\t{row['shard_timeout_seconds']}\n")
payload={'schema':'jass.l3_context2_contribution_balanced_preflight.v1','exact_preflight_per_cell':per,'producers':producers,'contention':contention,'projected_generation_minutes':total,'budget_minutes':budget,'within_budget':total<=budget,'cells':rows}
json.dump(payload,open(out,'w'),indent=2,sort_keys=True); print(json.dumps(payload,sort_keys=True))
if total>budget: raise SystemExit(f'preflight budget exceeded: {total:.2f}>{budget:.2f} min')
PY

stage generate-six-exact-100k-cells
mkdir -p "$W/cells"; index=0
for name in $CELL_NAMES; do
  echo "cell-$name" >"$STAGE"; cell="$W/cells/$name"; mkdir -p "$cell"
  limit=$(awk -v n="$name" '$1==n{print $2}' "$W/runtime-limits.tsv"); [ -n "$limit" ] || die "$name timeout missing"
  base=$((CELL_RECORDS/PRODUCERS)); rem=$((CELL_RECORDS%PRODUCERS)); pids=(); pairs=()
  for shard in $(seq 0 $((PRODUCERS-1))); do
    count=$base; [ "$shard" -lt "$rem" ] && count=$((count+1))
    data="$cell/s$shard.jnnw"; meta="$cell/s$shard.jsm"
    gen_one "$data" "$count" $((FRESH_SEED+index*100+shard)) "$IN/seeds/$name.jnnw" "$cell/s$shard.log" "$limit" &
    pids+=("$!"); pairs+=(--pair "$data" "$meta")
  done
  bad=0; for pid in "${pids[@]}"; do wait "$pid" || bad=$((bad+1)); done
  [ "$bad" -eq 0 ] || die "$name: $bad producer failures"
  for shard in $(seq 0 $((PRODUCERS-1))); do check_log "$cell/s$shard.log"; done
  "$PY" tools/selfplay_frontier.py merge "${pairs[@]}" --renamespace-nested --no-wdl-check \
    --out-data "$cell/cell.jnnw" --out-meta "$cell/cell.jsm" --manifest "$ART/cells/$name-merge.json" >"$cell/merge.log" 2>&1
  "$PY" jobs/tools/assert_corpus_wdl.py --data "$cell/cell.jnnw" --max-side-skew 0.02 >"$cell/wdl.log" 2>&1
  timeout 1200s "$J" --dump-conditional-context-v2 "$cell/cell.jnnw" "$cell/cell.feat" >"$cell/parser.log" 2>&1
  gzip -n -c "$cell/cell.jnnw" >"$ART/cells/$name.jnnw.gz"; gzip -n -c "$cell/cell.jsm" >"$ART/cells/$name.jsm.gz"
  say "cell=$name records=$CELL_RECORDS ready"; index=$((index+1))
done

stage merge-and-audit-600k-corpus
all_pairs=(); audit_args=()
for name in $CELL_NAMES; do all_pairs+=(--pair "$W/cells/$name/cell.jnnw" "$W/cells/$name/cell.jsm"); audit_args+=(--cell "$name=$W/cells/$name/cell.jnnw"); done
"$PY" tools/selfplay_frontier.py merge "${all_pairs[@]}" --renamespace-nested --no-wdl-check \
  --out-data "$W/context2-contribution-balanced-600k.jnnw" --out-meta "$W/context2-contribution-balanced-600k.jsm" \
  --manifest "$ART/context2-contribution-balanced-600k-merge.json" >"$W/unified-merge.log" 2>&1
"$PY" jobs/tools/l3_context2_contribution_balanced_corpus_audit.py "${audit_args[@]}" \
  --expected-per-cell "$CELL_RECORDS" --unified "$W/context2-contribution-balanced-600k.jnnw" \
  --code-sha "$EXPECTED_CODE_SHA" --fresh-seed "$FRESH_SEED" --seed-source "$SEED_JOB/$SEED_ATTEMPT" \
  --out "$ART/JASS_CONTROL_SUMMARY.json" | tee -a "$RES"
gzip -n -c "$W/context2-contribution-balanced-600k.jnnw" >"$ART/context2-contribution-balanced-600k.jnnw.gz"
gzip -n -c "$W/context2-contribution-balanced-600k.jsm" >"$ART/context2-contribution-balanced-600k.jsm.gz"
touch "$ART/VERDICT__JASS_CONTEXT2_CONTRIBUTION_BALANCED_CORPUS_READY"
touch "$ART/SELFPLAY_GENERATED__TRUE" "$ART/FITS_RUN__0" "$ART/FORCE_GAMES_PLAYED__0"
touch "$ART/FROZEN_READ__FALSE" "$ART/PROMOTION_AUTHORIZED__FALSE" "$ART/AUTOMATIC_NEXT_JOB__NULL"
say "JASS_CONTEXT2_CONTRIBUTION_BALANCED_CORPUS_READY cells=6 records=600000 preflight=60000 fits=0 force=0"
