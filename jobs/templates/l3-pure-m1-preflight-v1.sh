#!/usr/bin/env bash
# L3-PURE maturity M1 HOME preflight: exact source, Q00 generation and mini-fit.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${PARENT_PREFIX:?}"; : "${EXPECTED_PARENT_JOB:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; SRC="$JASS_RESULT_DIR/source"
GEOM="$JASS_RESULT_DIR/geom8"; mkdir -p "$W" "$ART" "$SRC" "$GEOM"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; : > "$RES"; : > "$PROG"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT; set +e; cp "$RES" "$ART/RESULTS.txt"; cp "$PROG" "$ART/PROGRESS.txt"; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR

[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"
FREE_MB="$(df -Pm "$JASS_RESULT_DIR"|awk 'NR==2{print $4}')"
[ "${FREE_MB:-0}" -ge 12000 ] || die "need 12 GiB free"

echo stage=fetch-parent-and-history > "$PROG"
python3 jobs/tools/fetch_result_files.py \
  --prefix "$PARENT_PREFIX" \
  --file artefacts/g3.pjtw.gz=parent.pjtw.gz \
  --file artefacts/g1-selfplay.jnnw.gz=g1.jnnw.gz \
  --file artefacts/g1-selfplay.jsm.gz=g1.jsm.gz \
  --file artefacts/g2-selfplay.jnnw.gz=g2.jnnw.gz \
  --file artefacts/g2-selfplay.jsm.gz=g2.jsm.gz \
  --file artefacts/g3-selfplay.jnnw.gz=g3.jnnw.gz \
  --file artefacts/g3-selfplay.jsm.gz=g3.jsm.gz \
  --file artefacts/l3-pure-manifest.json=manifest.json \
  --out-dir "$SRC" --report "$ART/verified-parent-source.json" > "$W/fetch.log" 2>&1
python3 - "$SRC" "$ART/verified-parent-source.json" "$EXPECTED_PARENT_JOB" <<'PY'
import gzip,json,struct,sys
from pathlib import Path
src=Path(sys.argv[1]); verified=json.load(open(sys.argv[2])); expected=sys.argv[3]
if verified.get("job_id") != expected or verified.get("result_state") != "completed":
    raise SystemExit("parent identity/state mismatch")
manifest=json.load(open(src/"manifest.json"))
if manifest.get("arm") != "A" or manifest.get("generations") != 3:
    raise SystemExit("not the immutable C0 A-G3 lineage")
counts={}
for generation in range(1,4):
    with gzip.open(src/f"g{generation}.jnnw.gz","rb") as handle:
        head=handle.read(8)
    if head[:4] != b"JNNW": raise SystemExit("bad historical JNNW")
    counts[f"g{generation}"]=struct.unpack_from("<I",head,4)[0]
    if counts[f"g{generation}"] != 500000: raise SystemExit("historical count mismatch")
json.dump({"schema":1,"parent_job":expected,"history_records":counts,"total_history_records":sum(counts.values())},open(Path(sys.argv[2]).parent/"m1-parent-contract.json","w"),indent=2,sort_keys=True)
PY
gunzip -c "$SRC/parent.pjtw.gz" > "$W/parent.pjtw"

echo stage=isolated-scipy > "$PROG"
python3 -m venv "$W/venv"
"$W/venv/bin/python" -m pip install --disable-pip-version-check --only-binary=:all: \
  numpy==1.26.4 scipy==1.14.1 > "$W/pip.log" 2>&1
"$W/venv/bin/python" - "$ART/python-runtime.json" <<'PY'
import json,platform,sys,numpy,scipy
json.dump({"schema":1,"python":sys.version,"platform":platform.platform(),"numpy":numpy.__version__,"scipy":scipy.__version__},open(sys.argv[1],"w"),indent=2,sort_keys=True)
PY

echo stage=build-8cf > "$PROG"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen-patterns.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] || die "8cf mismatch"
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl > "$W/clone.log" 2>&1
EGDIR=""; for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }; done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR"
cmake -S . -B "$W/build" $FLAGS > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j4 --target jass > "$W/build.log" 2>&1
J="$W/build/jass"

Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"
[ "$(tr ',' '\n' <<<"$Q00"|wc -l)" -eq 63 ] || die "Q00 must have 63 keys"

echo stage=exact-generation-calibration > "$PROG"
START="$(date +%s)"; pids=(); merge=()
for shard in 0 1; do
  data="$W/cal-s${shard}.jnnw"; meta="$W/cal-s${shard}.jsm"; log="$W/cal-s${shard}.log"
  timeout 3600 "$J" --gen-data-wdl 10000 "$data" 4 8 260 $((424242+shard)) \
    --nnue "$W/parent.pjtw" --search-params-play "$Q00" --wdl-zero-score \
    --random-open-plies 8 --explore-eps 8 --explore-decay-plies 60 \
    --pair-openings --drop-plycap --sample-meta-out "$meta" > "$log" 2>&1 &
  pids+=("$!"); merge+=(--pair "$data" "$meta")
done
for pid in "${pids[@]}"; do wait "$pid" || die "calibration shard failed"; done
ELAPSED=$(( $(date +%s)-START )); [ "$ELAPSED" -gt 0 ] || ELAPSED=1
for log in "$W"/cal-s*.log; do grep -q 'label_score_searches=0' "$log" || die "score label search detected"; done
python3 tools/selfplay_frontier.py merge "${merge[@]}" --out-data "$W/cal.raw.jnnw" --out-meta "$W/cal.raw.jsm" --manifest "$ART/calibration-merge.json" > "$W/merge.log" 2>&1
python3 tools/selfplay_frontier.py split --data "$W/cal.raw.jnnw" --meta "$W/cal.raw.jsm" --out-data "$W/cal.fit.jnnw" --out-meta "$W/cal.fit.jsm" --holdout-mod 10 --seed 271828 --manifest "$ART/calibration-split.json" > "$W/split.log" 2>&1
HOLDOUT="$("$W/venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["holdout_records"])' "$ART/calibration-split.json")"
"$J" --dump-eval-features "$W/cal.fit.jnnw" "$W/cal.feat" > "$W/features.log" 2>&1

echo stage=mini-fit > "$PROG"
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
  /usr/bin/time -v "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
  --data "$W/cal.fit.jnnw" --feat "$W/cal.feat" --out "$W/cal.pjtw" \
  --target wdl --loss logistic --color-fold --tempo-stage --warm-start "$W/parent.pjtw" \
  --holdout-count "$HOLDOUT" --l2 3e-5 --max-iter 2 --chunk 20000 \
  > "$W/mini-fit.log" 2> "$W/mini-fit-time.log"
[ -s "$W/cal.pjtw" ] || die "mini-fit missing"
grep -q 'HOLDOUT_LOGLOSS' "$W/mini-fit.log" || die "mini-fit holdout missing"

"$W/venv/bin/python" - "$ART" "$ELAPSED" <<'PY'
import json,pathlib,re,sys
art=pathlib.Path(sys.argv[1]); elapsed=int(sys.argv[2]); records=20000
rate=records/elapsed
fit=(art.parent/"work/mini-fit.log").read_text()
timing=(art.parent/"work/mini-fit-time.log").read_text()
rss=re.search(r"Maximum resident set size \\(kbytes\\):\\s*(\\d+)",timing)
payload={"schema":1,"verdict":"M1_PREFLIGHT_READY","parent":"C0_A_G3","calibration_records":records,"elapsed_seconds":elapsed,"records_per_second_two_workers":rate,"estimated_fresh_2m_seconds_at_12_workers_85pct_efficiency":round(2000000/(rate*6*0.85)),"mini_fit_max_iterations":2,"mini_fit_completed":True,"mini_fit_max_rss_kib":int(rss.group(1)) if rss else None,"training_screen_authorized":True,"promotion_authorized":False,"automatic_next_job":None}
(art/"m1-preflight.json").write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
(art/"JASS_CONTROL_SUMMARY.json").write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
(art/"VERDICT__M1_PREFLIGHT_READY").write_text("M1_PREFLIGHT_READY\n")
(art/"PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
PY
echo stage=complete > "$PROG"
say "M1_PREFLIGHT_READY"
