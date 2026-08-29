#!/usr/bin/env bash
# R0-v3: corrected production leaf/search contract. No strength games.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${JASS_OBJSTORE_REMOTE:?}"
cd "$JASS_CODE_DIR"
source jobs/templates/t3-f6-runtime-exclusions-v3.sh

MODEL_SHA="16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
MODEL_PREFIX="r2:jass-data/runs/cpx62-1637-l3-t3-rf1-joint-ab-train-freeze-v1/20260829T082456Z-bbb2bfe4"
CURRICULUM_PREFIX="r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/20260814T191555Z-18c38a33"
MODEL_JOB="cpx62-1637-l3-t3-rf1-joint-ab-train-freeze-v1"
MODEL_ATTEMPT="20260829T082456Z-bbb2bfe4"
MODEL_CODE="bbb2bfe460ece89bef0ec30e2d52ed4b0ff847ea"
CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE="18c38a33ae78c9c2e8e2df62fca266da28dacead"
PREREG_CODE="b326bb6610a7eb9b9b997540c1dbb0508f433ca0"
V1_IMPLEMENTATION_CODE="362d1a09bdb0633ef783f4e4048721d8ae6ee980"
RF1_EXTRACTOR_CODE="e5c4a0d6e88e99c06819100c4b5dbc697bbe3a53"
GEN_SEED=2026092101
SELECT_SEED=2026092102
PERMUTE_SEED=2026092103
BENCH_SEED=2026092104
ISOLATED_SEED=2026092105
TRACE_SEED=2026092106
CANDIDATES=120000
SELECTED=4096
CACHE_MB=128
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
VENV_READY="$VENV/.jass-runtime-ready-v1"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
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
      printf 'artefacts=%s\n' "$(find "$ART" -maxdepth 1 -type f | wc -l)"
    } >"$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120
  done) & MON="$!"
}
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  git worktree remove --force "$W/v1-src" 2>/dev/null || true
  git worktree remove --force "$W/rf1-src" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

emit_terminal(){
  local verdict authorized
  verdict=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
  authorized=$(python3 -c 'import json,sys;print(str(json.load(open(sys.argv[1]))["pool1_authorized"]).lower())' "$ART/JASS_CONTROL_SUMMARY.json")
  cp "$IN/t3-a-f6-only.json" "$ART/t3-a-f6-only.json"
  cp "$IN/curriculum.pjtw" "$ART/curriculum.pjtw"
  cp "$IN/r0-v1-corpus.fen" "$ART/r0-v1-corpus.fen"
  cp "$IN/r0-v2-corpus.fen" "$ART/r0-v2-corpus.fen"
  cp "$IN/negamax-autopsy.json" "$ART/negamax-autopsy.json"
  : >"$ART/VERDICT__$verdict"; : >"$ART/STRENGTH_GAMES__0"
  : >"$ART/POOL1_AUTHORIZED__${authorized^^}"
  : >"$ART/PROMOTION_AUTHORIZED__FALSE"; : >"$ART/BAKE__FALSE"
  say "$verdict strength_games=0 pool1_authorized=$authorized promotion=false"
}

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-t3-f6-runtime-r0-v3$ ]] || die "job nomenclature drift"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
git merge-base --is-ancestor "$PREREG_CODE" HEAD || die "v3 prereg is not an ancestor"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "dirty/non-detached job worktree"
[ "$(nproc)" -eq 16 ] || die "16-CPU CPX contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
[ -f "$VENV_READY" ] || die "numeric runtime absent"
PY="$VENV/bin/python"; "$PY" -c 'import numpy,scipy; assert numpy.__version__ and scipy.__version__' || die "numeric runtime invalid"
unset JASS_T3_F6_MODEL
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/t3_f6_r0_select_v3.py \
  jobs/tools/t3_f6_runtime_parity_v2.py jobs/tools/t3_f6_search_profile.py \
  jobs/tools/t3_f6_r0_readout_v3.py jobs/tools/t3_f6_strength_readout_v2.py
"$PY" -m unittest jobs.tests.test_t3_f6_runtime_protocol \
  jobs.tests.test_t3_f6_runtime_v2_protocol \
  jobs.tests.test_t3_f6_runtime_v3_protocol >"$W/python-tests.log" 2>&1

stage fetch-authenticate-frozen-evaluators
python3 jobs/tools/fetch_result_files.py --prefix "$MODEL_PREFIX" \
  --file artefacts/t3-a-f6-only.json=t3-a-f6-only.json --out-dir "$IN" \
  --report "$ART/verified-t3-a.json" >"$W/fetch-model.log" 2>&1 || die "T3-A fetch failed"
python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_PREFIX" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz --out-dir "$IN" \
  --report "$ART/verified-curriculum.json" >"$W/fetch-curriculum.log" 2>&1 || die "CURRICULUM fetch failed"
gunzip -t "$IN/curriculum.pjtw.gz"; gunzip -c "$IN/curriculum.pjtw.gz" >"$IN/curriculum.pjtw"
python3 - "$IN" "$ART" "$MODEL_JOB" "$MODEL_ATTEMPT" "$MODEL_CODE" \
  "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" "$CURRICULUM_CODE" "$MODEL_SHA" "$CURRICULUM_SHA" <<'PY_AUTH'
import hashlib,json,sys
from pathlib import Path
root,art=map(Path,sys.argv[1:3]); mj,ma,mc,cj,ca,cc,msha,csha=sys.argv[3:]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name,want in [('verified-t3-a.json',(mj,ma,mc)),('verified-curriculum.json',(cj,ca,cc))]:
 r=json.loads((art/name).read_text()); got=(r.get('job_id'),r.get('attempt_id'),r.get('code_sha'))
 if got!=want or r.get('result_state')!='completed' or r.get('exit_code')!=0: raise SystemExit(f'{name}: source drift {got}')
if sha(root/'t3-a-f6-only.json')!=msha: raise SystemExit('T3-A raw SHA drift')
if sha(root/'curriculum.pjtw')!=csha: raise SystemExit('CURRICULUM raw SHA drift')
PY_AUTH

stage fetch-all-frozen-exclusions
IDENTITY_ARGS=(); FORCE_ARGS=(); IDENTITY_COUNT=0; FORCE_COUNT=0
while IFS='|' read -r label prefix remote_path; do
  [ -n "${label:-}" ] || continue
  python3 jobs/tools/fetch_result_files.py --prefix "$prefix" --file "$remote_path=$label.tsv.gz" \
    --out-dir "$IN" --report "$ART/verified-identity-$label.json" >"$W/fetch-identity-$label.log" 2>&1 || die "identity exclusion fetch failed: $label"
  IDENTITY_ARGS+=(--exclude-tsv "$IN/$label.tsv.gz"); IDENTITY_COUNT=$((IDENTITY_COUNT+1))
done <<<"$T3_F6_IDENTITY_EXCLUDE_SPECS"
while IFS='|' read -r label prefix remote_path; do
  [ -n "${label:-}" ] || continue
  python3 jobs/tools/fetch_result_files.py --prefix "$prefix" --file "$remote_path=$label.fen" \
    --out-dir "$IN" --report "$ART/verified-force-$label.json" >"$W/fetch-force-$label.log" 2>&1 || die "force exclusion fetch failed: $label"
  FORCE_ARGS+=(--exclude-fen "$IN/$label.fen"); FORCE_COUNT=$((FORCE_COUNT+1))
done <<<"$T3_F6_FORCE_EXCLUDE_SPECS"
python3 jobs/tools/fetch_result_files.py --prefix "$T3_F6_R0_V1_PREFIX" \
  --expected-state "$T3_F6_R0_V1_EXPECTED_STATE" --file "$T3_F6_R0_V1_REMOTE=r0-v1-corpus.fen" \
  --out-dir "$IN" --report "$ART/verified-r0-v1-exclusion.json" >"$W/fetch-r0-v1.log" 2>&1 || die "R0-v1 exclusion fetch failed"
python3 jobs/tools/fetch_result_files.py --prefix "$T3_F6_R0_V2_PREFIX" \
  --file "$T3_F6_R0_V2_REMOTE=r0-v2-corpus.fen" --out-dir "$IN" \
  --report "$ART/verified-r0-v2-exclusion.json" >"$W/fetch-r0-v2.log" 2>&1 || die "R0-v2 exclusion fetch failed"
python3 jobs/tools/fetch_result_files.py --prefix "$T3_F6_AUTOPSY_PREFIX" \
  --file "$T3_F6_AUTOPSY_REMOTE=negamax-autopsy.json" --out-dir "$IN" \
  --report "$ART/verified-negamax-autopsy.json" >"$W/fetch-autopsy.log" 2>&1 || die "autopsy exclusion fetch failed"
python3 - "$IN/negamax-autopsy.json" "$ART/autopsy-exclusions.fen" <<'PY_AUTOPSY_FEN'
import json,sys
from pathlib import Path
from jobs.tools.t3_f6_r0_select import fen_fingerprint
payload=json.loads(Path(sys.argv[1]).read_text()); rows={}
def visit(value):
 if isinstance(value,dict):
  for item in value.values(): visit(item)
 elif isinstance(value,list):
  for item in value: visit(item)
 elif isinstance(value,str) and ':' in value:
  try: rows.setdefault(fen_fingerprint(value)[0],value)
  except (ValueError,IndexError,KeyError): pass
visit(payload)
if not rows: raise SystemExit('autopsy FEN extraction empty')
Path(sys.argv[2]).write_text('\n'.join(rows[key] for key in sorted(rows))+'\n')
PY_AUTOPSY_FEN
FORCE_ARGS+=(--exclude-fen "$IN/r0-v1-corpus.fen" --exclude-fen "$IN/r0-v2-corpus.fen")
[ "$IDENTITY_COUNT" -eq 10 ] && [ "$FORCE_COUNT" -eq 24 ] || die "exclusion count drift"

stage locate-egdb-and-build-production
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen-current.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON \
  -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests t3_f6_runtime_probe \
  t3_f6_invariance_probe t3_f6_relative_probe t3_f6_negamax_autopsy \
  t3_f6_leaf_contract_v3 \
  >"$W/build.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB ctest --test-dir "$W/build" --output-on-failure >"$W/ctest.log" 2>&1
J="$W/build/jass"

stage generate-and-mechanically-seal-r0-v3-corpus
for pass in a b; do
  "$J" --gen-opening-pool "$CANDIDATES" "$W/r0-v3-candidates-$pass.fen" 8 160 9 "$GEN_SEED" >"$W/r0-v3-generate-$pass.log" 2>&1
done
cmp -s "$W/r0-v3-candidates-a.fen" "$W/r0-v3-candidates-b.fen" || die "R0-v3 candidate replay drift"
"$W/build/t3_f6_leaf_contract_v3" --classify "$W/r0-v3-candidates-a.fen" \
  "$ART/r0-mechanics.tsv" >"$W/r0-mechanics.log" 2>&1
python3 jobs/tools/t3_f6_r0_select_v3.py --candidates "$W/r0-v3-candidates-a.fen" \
  --mechanics "$ART/r0-mechanics.tsv" "${IDENTITY_ARGS[@]}" "${FORCE_ARGS[@]}" \
  --exclude-json-fens "$IN/negamax-autopsy.json" --selection-seed "$SELECT_SEED" \
  --permutation-seed "$PERMUTE_SEED" --benchmark-seed "$BENCH_SEED" \
  --isolated-seed "$ISOLATED_SEED" --trace-seed "$TRACE_SEED" \
  --out-fen "$ART/r0-corpus.fen" --out-jnnw "$W/r0-corpus.jnnw" \
  --out-benchmark-fen "$W/r0-benchmark.fen" --out-benchmark-jnnw "$W/r0-benchmark.jnnw" \
  --out-isolated-fen "$ART/r0-isolated-roots.fen" \
  --out-real-trace-fen "$ART/r0-real-trace-roots.fen" \
  --report "$ART/r0-selection.json" >"$W/r0-select.log" 2>&1
SELECTION_PASS=$(python3 -c 'import json,sys;print(str(json.load(open(sys.argv[1]))["passed"]).lower())' "$ART/r0-selection.json")
if [ "$SELECTION_PASS" != true ]; then
  python3 jobs/tools/t3_f6_r0_readout_v3.py --selection "$ART/r0-selection.json" \
    --model "$IN/t3-a-f6-only.json" --curriculum "$IN/curriculum.pjtw" \
    --code-sha "$EXPECTED_CODE_SHA" --out "$ART/JASS_CONTROL_SUMMARY.json" >"$W/r0-readout.log" 2>&1
  emit_terminal; exit 0
fi
[ "$(grep -c . "$ART/r0-corpus.fen")" -eq "$SELECTED" ] || die "R0-v3 corpus cardinality drift"

stage relative-position-symmetry-gates
"$W/build/t3_f6_relative_probe" "$ART/r0-corpus.fen" "$IN/curriculum.pjtw" \
  "$IN/t3-a-f6-only.json" "$ART/r0-relative-contract.json" "$PERMUTE_SEED" \
  --v3-relative-only >"$W/relative.log" 2>&1
RELATIVE_PASS=$(python3 -c 'import json,sys;print(str(json.load(open(sys.argv[1]))["passed"]).lower())' "$ART/r0-relative-contract.json")
if [ "$RELATIVE_PASS" != true ]; then
  python3 jobs/tools/t3_f6_r0_readout_v3.py --selection "$ART/r0-selection.json" \
    --relative "$ART/r0-relative-contract.json" --model "$IN/t3-a-f6-only.json" \
    --curriculum "$IN/curriculum.pjtw" --code-sha "$EXPECTED_CODE_SHA" \
    --out "$ART/JASS_CONTROL_SUMMARY.json" >"$W/r0-readout.log" 2>&1
  emit_terminal; exit 0
fi

stage corrected-isolated-and-real-search-contract
"$W/build/t3_f6_leaf_contract_v3" --contract "$ART/r0-isolated-roots.fen" \
  "$ART/r0-real-trace-roots.fen" "$IN/curriculum.pjtw" "$IN/t3-a-f6-only.json" \
  "$Q00" "$EXPECTED_CODE_SHA" "$ART/r0-leaf-search-contract.json" >"$W/leaf-contract.log" 2>&1
LEAF_PASS=$(python3 -c 'import json,sys;print(str(json.load(open(sys.argv[1]))["passed"]).lower())' "$ART/r0-leaf-search-contract.json")
if [ "$LEAF_PASS" != true ]; then
  python3 jobs/tools/t3_f6_r0_readout_v3.py --selection "$ART/r0-selection.json" \
    --relative "$ART/r0-relative-contract.json" --leaf-contract "$ART/r0-leaf-search-contract.json" \
    --model "$IN/t3-a-f6-only.json" --curriculum "$IN/curriculum.pjtw" \
    --code-sha "$EXPECTED_CODE_SHA" --out "$ART/JASS_CONTROL_SUMMARY.json" >"$W/r0-readout.log" 2>&1
  emit_terminal; exit 0
fi

stage build-frozen-references
git worktree add --detach "$W/v1-src" "$V1_IMPLEMENTATION_CODE" >"$W/v1-worktree.log" 2>&1
(cd "$W/v1-src" && python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf) >"$W/gen-v1.log" 2>&1
cmake -S "$W/v1-src" -B "$W/v1-build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON \
  -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/v1-cmake.log" 2>&1
cmake --build "$W/v1-build" -j8 --target jass >"$W/v1-build.log" 2>&1
V1_J="$W/v1-build/jass"
git worktree add --detach "$W/rf1-src" "$RF1_EXTRACTOR_CODE" >"$W/rf1-worktree.log" 2>&1
(cd "$W/rf1-src" && python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf) >"$W/gen-rf1.log" 2>&1
cmake -S "$W/rf1-src" -B "$W/rf1-build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=OFF \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON \
  -DJASS_TEMPO_STAGE=ON >"$W/rf1-cmake.log" 2>&1
cmake --build "$W/rf1-build" -j8 --target jass_lib >"$W/rf1-build.log" 2>&1
c++ -std=c++20 -O3 -DNDEBUG -DJASS_ENDGAME_FEATURES=1 -DJASS_KING_MOBILITY=1 \
  -DJASS_SCAN_PARITY=1 -DJASS_TEMPO_STAGE=1 -I"$W/rf1-src/src" \
  -I"$W/rf1-src/pattern_jass/src" "$W/rf1-src/jobs/tools/residual_feature_dump.cpp" \
  "$W/rf1-src/src/residual_features.cpp" "$W/rf1-build/libjass_lib.a" -pthread \
  -o "$W/residual_feature_dump_rf1" >"$W/rf1-link.log" 2>&1
"$W/residual_feature_dump_rf1" "$W/r0-benchmark.jnnw" "$W/r0-reference.rffd" >"$W/rf1-dump.log" 2>&1

stage python-native-parity-and-runtime-profile
"$W/build/t3_f6_runtime_probe" "$W/r0-benchmark.fen" "$IN/curriculum.pjtw" \
  "$IN/t3-a-f6-only.json" "$W/r0-native.tsv" "$ART/r0-runtime-profile.json" 32 \
  "$BENCH_SEED" >"$W/runtime-probe.log" 2>&1
"$PY" jobs/tools/t3_f6_runtime_parity_v2.py --native-tsv "$W/r0-native.tsv" \
  --reference-rffd "$W/r0-reference.rffd" --model "$IN/t3-a-f6-only.json" \
  --curriculum "$IN/curriculum.pjtw" --out "$ART/r0-python-native-parity.json" >"$W/parity.log" 2>&1

stage loader-fail-closed-contract
printf 'hello\nquit\n' | env -u JASS_T3_F6_MODEL "$J" --pattern "$IN/curriculum.pjtw" >"$W/load-off.log" 2>&1
grep -q '^ready' "$W/load-off.log" || die "OFF exact load failed"
printf 'hello\nquit\n' | env JASS_T3_F6_MODEL="$IN/t3-a-f6-only.json" "$J" --pattern "$IN/curriculum.pjtw" >"$W/load-on.log" 2>&1
grep -q '^ready' "$W/load-on.log" || die "ON exact load failed"
set +e
printf 'hello\nquit\n' | env JASS_T3_F6_MODEL= "$J" --pattern "$IN/curriculum.pjtw" >"$W/load-empty.log" 2>&1; EMPTY_RC=$?
printf 'hello\nquit\n' | env JASS_T3_F6_MODEL="$ART/r0-selection.json" "$J" --pattern "$IN/curriculum.pjtw" >"$W/load-wrong.log" 2>&1; WRONG_RC=$?
set -e
[ "$EMPTY_RC" -ne 0 ] && [ "$WRONG_RC" -ne 0 ] || die "loader did not fail closed"
python3 - "$ART/loader-auth.json" "$EMPTY_RC" "$WRONG_RC" <<'PY_LOADER'
import json,sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({'schema':'jass.t3_f6_loader_auth.v3','passed':True,
 'off_absent_exact':True,'on_exact_load':True,'empty_env_rejected':int(sys.argv[2])!=0,
 'wrong_artifact_rejected':int(sys.argv[3])!=0},indent=2,sort_keys=True)+'\n')
PY_LOADER

stage off-regression-and-search-cost
python3 jobs/tools/t3_f6_search_profile.py --exe "$J" --prereg-exe "$V1_J" \
  --curriculum "$IN/curriculum.pjtw" --model "$IN/t3-a-f6-only.json" \
  --corpus "$ART/r0-corpus.fen" --search-params "$Q00" --order-seed "$BENCH_SEED" \
  --out "$ART/r0-search-profile.json" >"$W/search-profile.log" 2>&1

stage runtime-contract-and-r0-v3-verdict
python3 - "$ART/runtime-contract.json" "$J" "$MODEL_SHA" "$CURRICULUM_SHA" "$Q00" "$EGDIR" <<'PY_RUNTIME'
import hashlib,json,sys
from pathlib import Path
out,exe=map(Path,sys.argv[1:3]); model,curr,q00,egdir=sys.argv[3:]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
payload={'schema':'jass.t3_f6_runtime_contract.v3','passed':True,'executable_sha256':sha(exe),
 'model_sha256':model,'curriculum_sha256':curr,'same_executable_both_arms':True,
 'candidate_env':'JASS_T3_F6_MODEL','control_env':'ABSENT','leaf_only':True,
 'trace_default_null':True,'search_params':q00,'threads':1,'tt_mb':16,'egdb':'ON',
 'egdb_path':egdir,'egdb_cache_mb':128,'book':'OFF','maxplies':160,
 'build_flags':['JASS_EGDB=ON','JASS_ENDGAME_FEATURES=ON','JASS_KING_MOBILITY=ON','JASS_SCAN_PARITY=ON','JASS_TEMPO_STAGE=ON']}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_RUNTIME
python3 jobs/tools/t3_f6_r0_readout_v3.py --selection "$ART/r0-selection.json" \
  --relative "$ART/r0-relative-contract.json" --leaf-contract "$ART/r0-leaf-search-contract.json" \
  --parity "$ART/r0-python-native-parity.json" --runtime-profile "$ART/r0-runtime-profile.json" \
  --search-profile "$ART/r0-search-profile.json" --loader-auth "$ART/loader-auth.json" \
  --runtime-contract "$ART/runtime-contract.json" --model "$IN/t3-a-f6-only.json" \
  --curriculum "$IN/curriculum.pjtw" --executable "$J" \
  --reference-rffd "$W/r0-reference.rffd" --code-sha "$EXPECTED_CODE_SHA" \
  --out "$ART/JASS_CONTROL_SUMMARY.json" >"$W/r0-readout.log" 2>&1

emit_terminal
gzip -n -c "$J" >"$ART/jass-t3-f6-force.gz"
gzip -n -c "$W/r0-native.tsv" >"$ART/r0-native.tsv.gz"
gzip -n -c "$W/r0-reference.rffd" >"$ART/r0-reference.rffd.gz"
