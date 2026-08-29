#!/usr/bin/env bash
# R1-v2 Pool1: frozen T3-A/F6 vs CURRICULUM, CPX62 native 0.1 s/move primary only.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${JASS_OBJSTORE_REMOTE:?}"; : "${R0_RESULT_PREFIX:?}"
cd "$JASS_CODE_DIR"
CAMPAIGN="${T3_F6_RUNTIME_CAMPAIGN:-v2}"
case "$CAMPAIGN" in
  v2) source jobs/templates/t3-f6-runtime-exclusions-v2.sh ;;
  v3) source jobs/templates/t3-f6-runtime-exclusions-v3.sh ;;
  v4) source jobs/templates/t3-f6-runtime-exclusions-v4.sh ;;
  *) echo "unsupported runtime campaign: $CAMPAIGN" >&2; exit 2 ;;
esac

MODEL_SHA="16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
GEN_SEED="${T3_F6_POOL1_GEN_SEED:-2026091801}"
SELECT_SEED="${T3_F6_POOL1_SELECT_SEED:-2026091802}"
NATIVE_BOOTSTRAP_SEED="${T3_F6_POOL1_BOOTSTRAP_SEED:-2026091803}"
CANDIDATES=30000
OPENINGS=3000
GAMES=6000
BOOTSTRAP=200000
NSH=12
PAR=12
CACHE_MB=128
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
VENV_READY="$VENV/.jass-runtime-ready-v1"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"; FORCE="$ART/force"
mkdir -p "$W" "$IN" "$ART" "$FORCE"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }
MON=""
monitor(){ (t0=$(date +%s); while true; do
  { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"; printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"; printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"; } >"$PROG.tmp"
  mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120; done) & MON="$!"; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
if [ "$CAMPAIGN" = v2 ]; then
  [[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-t3-f6-runtime-strength-pool1-v2$ ]] || die "job nomenclature drift"
elif [ "$CAMPAIGN" = v3 ]; then
  [[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-t3-f6-runtime-strength-pool1-v3$ ]] || die "v3 job nomenclature drift"
else
  [[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-t3-f6-runtime-strength-pool1-v4$ ]] || die "v4 job nomenclature drift"
fi
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "dirty/non-detached job worktree"
[ "$(nproc)" -eq 16 ] || die "16-CPU CPX contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
[ -f "$VENV_READY" ] || die "numeric runtime absent"
PY="$VENV/bin/python"; "$PY" -c 'import numpy; assert numpy.__version__' || die "numeric runtime invalid"
unset JASS_T3_F6_MODEL; monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/t3_f6_force_pool_select.py jobs/tools/t3_f6_strength_readout_v2.py \
  jobs/tools/run_jass_gate_bounded.py jobs/tools/jass_vs_jass_arch.py
"$PY" -m unittest jobs.tests.test_t3_f6_runtime_protocol \
  jobs.tests.test_t3_f6_runtime_v2_protocol >"$W/python-tests.log" 2>&1
[ "$CAMPAIGN" = v2 ] || "$PY" -m unittest jobs.tests.test_t3_f6_runtime_v3_protocol >>"$W/python-tests.log" 2>&1
[ "$CAMPAIGN" != v4 ] || "$PY" -m unittest jobs.tests.test_t3_f6_runtime_v4_protocol >>"$W/python-tests.log" 2>&1

stage fetch-authenticate-r0-exact-bytes
EXTRA_R0_FILES=()
[ "$CAMPAIGN" = v2 ] || EXTRA_R0_FILES+=(
  --file artefacts/r0-v2-corpus.fen=r0-v2-corpus.fen
  --file artefacts/autopsy-exclusions.fen=autopsy-exclusions.fen)
[ "$CAMPAIGN" != v4 ] || EXTRA_R0_FILES+=(
  --file artefacts/r0-v3-mechanics.tsv=r0-v3-mechanics.tsv
  --file artefacts/scan-parents.tsv=scan-parents.tsv
  --file artefacts/scan-siblings.tsv=scan-siblings.tsv)
python3 jobs/tools/fetch_result_files.py --prefix "$R0_RESULT_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=r0-summary.json \
  --file artefacts/jass-t3-f6-force.gz=jass-t3-f6-force.gz \
  --file artefacts/t3-a-f6-only.json=t3-a-f6-only.json \
  --file artefacts/curriculum.pjtw=curriculum.pjtw \
  --file artefacts/r0-corpus.fen=r0-corpus.fen \
  --file artefacts/r0-v1-corpus.fen=r0-v1-corpus.fen \
  "${EXTRA_R0_FILES[@]}" \
  --out-dir "$IN" --report "$ART/verified-r0.json" >"$W/fetch-r0.log" 2>&1 || die "R0 fetch failed"
gunzip -t "$IN/jass-t3-f6-force.gz"; gunzip -c "$IN/jass-t3-f6-force.gz" >"$W/jass"; chmod 755 "$W/jass"; J="$W/jass"
python3 - "$IN" "$ART" "$EXPECTED_CODE_SHA" "$MODEL_SHA" "$CURRICULUM_SHA" "$CAMPAIGN" <<'PY_R0'
import hashlib,json,sys
from pathlib import Path
root,art=map(Path,sys.argv[1:3]); code,model,curr,campaign=sys.argv[3:]; sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
s=json.loads((root/'r0-summary.json').read_text()); receipt=json.loads((art/'verified-r0.json').read_text())
if receipt.get('result_state')!='completed' or receipt.get('exit_code')!=0: raise SystemExit('R0 result state drift')
want={'v2':'R0_RELATIVE_PRODUCTION_LEAF_CONTRACT_ESTABLISHED','v3':'R0_V3_PRODUCTION_LEAF_CONTRACT_ESTABLISHED','v4':'R0_V4_PRODUCTION_LEAF_CONTRACT_ESTABLISHED'}[campaign]
if s.get('verdict')!=want or s.get('passed') is not True or s.get('pool1_authorized') is not True: raise SystemExit('R0 authorization drift')
if s.get('code_sha')!=code or receipt.get('code_sha')!=code: raise SystemExit('R0/Pool1 code drift')
if sha(root/'t3-a-f6-only.json')!=model or s.get('artifact_sha256')!=model: raise SystemExit('T3-A byte drift')
if sha(root/'curriculum.pjtw')!=curr or s.get('curriculum_sha256')!=curr: raise SystemExit('CURRICULUM byte drift')
PY_R0
[ "$(sha256sum "$J" | awk '{print $1}')" = "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["executable_sha256"])' "$IN/r0-summary.json")" ] || die "R0 executable drift"

stage loader-smoke-egdb-and-exclusions
printf 'hello\nquit\n' | env -u JASS_T3_F6_MODEL "$J" --pattern "$IN/curriculum.pjtw" >"$W/load-off.log" 2>&1
printf 'hello\nquit\n' | env JASS_T3_F6_MODEL="$IN/t3-a-f6-only.json" "$J" --pattern "$IN/curriculum.pjtw" >"$W/load-on.log" 2>&1
grep -q '^ready' "$W/load-off.log" && grep -q '^ready' "$W/load-on.log" || die "exact binary loader smoke failed"
EGDIR=""; for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }; done
[ -n "$EGDIR" ] || die "EGDB unavailable"
[ "$EGDIR" = "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["runtime_contract"]["egdb_path"])' "$IN/r0-summary.json")" ] || die "R0/Pool1 EGDB path drift"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
IDENTITY_ARGS=(); FORCE_ARGS=(--exclude-fen "$IN/r0-corpus.fen" --exclude-fen "$IN/r0-v1-corpus.fen"); IDENTITY_COUNT=0; FORCE_COUNT=0
[ "$CAMPAIGN" = v2 ] || FORCE_ARGS+=(--exclude-fen "$IN/r0-v2-corpus.fen" --exclude-fen "$IN/autopsy-exclusions.fen")
[ "$CAMPAIGN" != v4 ] || IDENTITY_ARGS+=(--exclude-tsv "$IN/r0-v3-mechanics.tsv" --exclude-tsv "$IN/scan-parents.tsv" --exclude-tsv "$IN/scan-siblings.tsv")
while IFS='|' read -r label prefix remote_path; do [ -n "${label:-}" ] || continue
  python3 jobs/tools/fetch_result_files.py --prefix "$prefix" --file "$remote_path=$label.tsv.gz" --out-dir "$IN" --report "$ART/verified-identity-$label.json" >"$W/fetch-identity-$label.log" 2>&1 || die "identity exclusion fetch failed: $label"
  IDENTITY_ARGS+=(--exclude-tsv "$IN/$label.tsv.gz"); IDENTITY_COUNT=$((IDENTITY_COUNT+1)); done <<<"$T3_F6_IDENTITY_EXCLUDE_SPECS"
while IFS='|' read -r label prefix remote_path; do [ -n "${label:-}" ] || continue
  python3 jobs/tools/fetch_result_files.py --prefix "$prefix" --file "$remote_path=$label.fen" --out-dir "$IN" --report "$ART/verified-force-$label.json" >"$W/fetch-force-$label.log" 2>&1 || die "force exclusion fetch failed: $label"
  FORCE_ARGS+=(--exclude-fen "$IN/$label.fen"); FORCE_COUNT=$((FORCE_COUNT+1)); done <<<"$T3_F6_FORCE_EXCLUDE_SPECS"
[ "$IDENTITY_COUNT" -eq 10 ] && [ "$FORCE_COUNT" -eq 24 ] || die "exclusion count drift"

stage generate-certify-fresh-pool1
for pass in a b; do "$J" --gen-opening-pool "$CANDIDATES" "$W/pool1-candidates-$pass.fen" 8 32 20 "$GEN_SEED" >"$W/pool1-generate-$pass.log" 2>&1; done
cmp -s "$W/pool1-candidates-a.fen" "$W/pool1-candidates-b.fen" || die "Pool1 generator replay drift"
python3 jobs/tools/t3_f6_force_pool_select.py --candidates "$W/pool1-candidates-a.fen" \
  "${IDENTITY_ARGS[@]}" "${FORCE_ARGS[@]}" --selection-seed "$SELECT_SEED" --generator-seed "$GEN_SEED" \
  --out "$ART/pool1-openings.fen" --report "$ART/pool1-provenance.json" >"$W/pool1-select.log" 2>&1
[ "$(grep -c . "$ART/pool1-openings.fen")" -eq "$OPENINGS" ] || die "Pool1 cardinality drift"

stage force-pool1-native-primary
timeout -k 120s 43200s "$PY" jobs/tools/run_jass_gate_bounded.py \
  --jass "$J" --pattern-a "$IN/curriculum.pjtw" --pattern-b "$IN/curriculum.pjtw" \
  --t3-f6-model-a "$IN/t3-a-f6-only.json" --fail-on-game-error --enforce-no-book \
  --search-params-a "$Q00" --search-params-b "$Q00" --openings-file "$ART/pool1-openings.fen" \
  --movetime 0.1 --pairs 1 --max-plies 160 --nshards "$NSH" --max-parallel "$PAR" --timeout 40000 \
  --paired-bootstrap-samples "$BOOTSTRAP" --paired-bootstrap-seed "$NATIVE_BOOTSTRAP_SEED" \
  --work-dir "$W/gate-pool1-native" --out "$FORCE/pool1-native.json" >"$W/force-pool1-native.log" 2>&1 || die "Pool1 native gate failed"
python3 - "$W/gate-pool1-native" "$ART/pool1-native-games.jsonl.gz" "$GAMES" <<'PY_GAMES'
import gzip,json,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2]); expected=int(sys.argv[3]); rows=[]
for p in root.glob('games.*.jsonl'): rows.extend(json.loads(x) for x in p.read_text().splitlines() if x.strip())
rows.sort(key=lambda x:int(x['game_index']))
if len(rows)!=expected or [int(x['game_index']) for x in rows]!=list(range(expected)): raise SystemExit('raw game rows drift')
with out.open('wb') as raw:
 with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as gz:
  for row in rows: gz.write((json.dumps(row,sort_keys=True,separators=(',',':'))+'\n').encode())
PY_GAMES

stage pool1-readout-and-decision
"$PY" jobs/tools/t3_f6_strength_readout_v2.py --pool1-native "$FORCE/pool1-native.json" \
  --model "$IN/t3-a-f6-only.json" --curriculum "$IN/curriculum.pjtw" --executable "$J" \
  --pool1-openings "$ART/pool1-openings.fen" --pool1-provenance "$ART/pool1-provenance.json" \
  --r0-summary "$IN/r0-summary.json" --code-sha "$EXPECTED_CODE_SHA" --search-params "$Q00" \
  --campaign "$CAMPAIGN" \
  --out "$ART/JASS_CONTROL_SUMMARY.json" >"$W/pool1-readout.log" 2>&1
VERDICT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
AUTHORIZED=$(python3 -c 'import json,sys;print(str(json.load(open(sys.argv[1]))["pool2_authorized"]).lower())' "$ART/JASS_CONTROL_SUMMARY.json")
cp "$IN/jass-t3-f6-force.gz" "$ART/jass-t3-f6-force.gz"; cp "$IN/t3-a-f6-only.json" "$ART/t3-a-f6-only.json"
cp "$IN/curriculum.pjtw" "$ART/curriculum.pjtw"; cp "$IN/r0-summary.json" "$ART/r0-summary.json"
cp "$IN/r0-corpus.fen" "$ART/r0-corpus.fen"; cp "$IN/r0-v1-corpus.fen" "$ART/r0-v1-corpus.fen"
[ "$CAMPAIGN" = v2 ] || { cp "$IN/r0-v2-corpus.fen" "$ART/r0-v2-corpus.fen"; cp "$IN/autopsy-exclusions.fen" "$ART/autopsy-exclusions.fen"; }
[ "$CAMPAIGN" != v4 ] || { cp "$IN/r0-v3-mechanics.tsv" "$ART/r0-v3-mechanics.tsv"; cp "$IN/scan-parents.tsv" "$ART/scan-parents.tsv"; cp "$IN/scan-siblings.tsv" "$ART/scan-siblings.tsv"; }
: >"$ART/VERDICT__$VERDICT"; : >"$ART/GAMES_TOTAL__6000"; : >"$ART/Q00_GAMES__0"
: >"$ART/POOL2_AUTHORIZED__${AUTHORIZED^^}"; : >"$ART/PROMOTION_AUTHORIZED__FALSE"; : >"$ART/BAKE__FALSE"
say "$VERDICT native_games=6000 q00_games=0 pool2_authorized=$AUTHORIZED promotion=false"
