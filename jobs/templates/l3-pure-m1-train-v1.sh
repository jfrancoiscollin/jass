#!/usr/bin/env bash
# L3-PURE maturity M1: shared fresh source, F500/F2M/R2M fits, no promotion.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${PARENT_PREFIX:?}"; : "${EXPECTED_PARENT_JOB:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; SRC="$JASS_RESULT_DIR/source"
GEOM="$JASS_RESULT_DIR/geom8"; mkdir -p "$W" "$ART" "$SRC" "$GEOM"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; PHASE="$W/phase.txt"
: > "$RES"; : > "$PROG"; echo initializing > "$PHASE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
phase(){ echo "$1" > "$PHASE"; say "phase=$1"; }
ACTIVE=(); MONITOR_PID=""
monitor(){
  (
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$PHASE" 2>/dev/null || echo unknown)"
        df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{printf "free_mb=%s\n",$4}'
        awk '/MemAvailable:/{printf "mem_available_mb=%d\n",$2/1024}' /proc/meminfo
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 60
    done
  ) & MONITOR_PID="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR INT TERM; set +e
  [ "${#ACTIVE[@]}" -eq 0 ] || kill "${ACTIVE[@]}" 2>/dev/null
  [ -z "$MONITOR_PID" ] || { kill "$MONITOR_PID" 2>/dev/null; wait "$MONITOR_PID" 2>/dev/null; }
  [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$W/venv" "$W"/*.feat 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 130' INT
trap 'exit 143' TERM

COMMON_RECORDS=500000
EXTRA_RECORDS=1500000
PRODUCERS=12
LABEL_DEPTH=4
PLAY_DEPTH=8
MAXPLIES=260
BASE_SEED=314159
HOLDOUT_MOD=10
SPLIT_SEED=271828
L2=3e-5
MAXIT=200
CHUNK=20000
GEN_TIMEOUT=14400
FIT_TIMEOUT=43200

Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

say "=== $JASS_JOB_ID — L3-PURE maturity M1 F500/F2M/R2M ==="
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ "${SCIENTIFIC_GO:-0}" = 1 ] || die "SCIENTIFIC_GO=1 missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "NO_AUTOMATIC_CONTINUATION=1 missing"
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -ge 12000 ] || die "need 12 GiB free"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 key count drift"
monitor

phase fetch-immutable-parent-and-replay
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
import gzip, hashlib, json, struct, sys
from pathlib import Path
src=Path(sys.argv[1]); report=json.load(open(sys.argv[2])); expected=sys.argv[3]
if report.get("job_id") != expected or report.get("result_state") != "completed":
    raise SystemExit("parent identity/state mismatch")
manifest=json.load(open(src/"manifest.json"))
if manifest.get("arm") != "A" or manifest.get("generations") != 3:
    raise SystemExit("parent is not C0 A-G3")
sources={}
for g in range(1,4):
    with gzip.open(src/f"g{g}.jnnw.gz","rb") as h: data=h.read()
    with gzip.open(src/f"g{g}.jsm.gz","rb") as h: meta=h.read()
    if data[:4] != b"JNNW" or struct.unpack_from("<I",data,4)[0] != 500000:
        raise SystemExit(f"G{g} historical count mismatch")
    if meta[:4] != b"JSM1":
        raise SystemExit(f"G{g} historical JSM mismatch")
    sources[f"g{g}"]={"records":500000,
      "jnnw_sha256":hashlib.sha256(data).hexdigest(),
      "jsm_sha256":hashlib.sha256(meta).hexdigest()}
json.dump({"schema":1,"parent_job":expected,"parent_generation":3,
 "replay_sources":sources,"replay_records":1500000},
 open(Path(sys.argv[2]).parent/"m1-source-contract.json","w"),indent=2,sort_keys=True)
PY
gunzip -c "$SRC/parent.pjtw.gz" > "$W/parent.pjtw"
for g in 1 2 3; do gunzip -c "$SRC/g$g.jnnw.gz" > "$W/hist-g$g.jnnw"; gunzip -c "$SRC/g$g.jsm.gz" > "$W/hist-g$g.jsm"; done

phase isolated-runtime-and-build
python3 -m venv "$W/venv"
"$W/venv/bin/python" -m pip install --disable-pip-version-check --only-binary=:all: \
  numpy==1.26.4 scipy==1.14.1 > "$W/pip.log" 2>&1
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen-patterns.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] || die "8cf mismatch"
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl > "$W/clone.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || die "EGDB unavailable"; export JASS_EGDB_PATH="$EGDIR"
cmake -S . -B "$W/build" $FLAGS > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j4 --target jass > "$W/build.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "jass binary missing"

generate_fresh(){
  local label="$1" total="$2" seed_offset="$3"
  local base=$((total / PRODUCERS)) rem=$((total % PRODUCERS)) shard count data meta log failed pid
  local pairs=(); ACTIVE=()
  for shard in $(seq 0 $((PRODUCERS-1))); do
    count="$base"; [ "$shard" -lt "$rem" ] && count=$((count+1))
    data="$W/$label-s$shard.jnnw"; meta="$W/$label-s$shard.jsm"; log="$W/$label-s$shard.log"
    timeout "$GEN_TIMEOUT" "$J" --gen-data-wdl "$count" "$data" \
      "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" $((BASE_SEED+seed_offset+shard)) \
      --nnue "$W/parent.pjtw" --search-params-play "$Q00" --wdl-zero-score \
      --random-open-plies 8 --explore-eps 8 --explore-decay-plies 60 \
      --pair-openings --drop-plycap --sample-meta-out "$meta" > "$log" 2>&1 &
    ACTIVE+=("$!"); pairs+=(--pair "$data" "$meta")
  done
  failed=0; for pid in "${ACTIVE[@]}"; do wait "$pid" || failed=$((failed+1)); done; ACTIVE=()
  [ "$failed" -eq 0 ] || die "$label generation: $failed producer failures"
  for log in "$W/$label-s"*.log; do grep -q 'label_score_searches=0' "$log" || die "score-label search in $log"; done
  python3 tools/selfplay_frontier.py merge "${pairs[@]}" \
    --out-data "$W/$label.raw.jnnw" --out-meta "$W/$label.raw.jsm" \
    --manifest "$ART/$label-merge.json" > "$W/$label-merge.log" 2>&1
}

if [ -n "${RESUME_SOURCE_PREFIX:-}" ]; then
  phase recover-verified-fresh-source
  python3 jobs/tools/fetch_result_files.py --prefix "$RESUME_SOURCE_PREFIX" \
    --expected-state failed \
    --file artefacts/common-fresh-500k.jnnw.gz=common.jnnw.gz \
    --file artefacts/common-fresh-500k.jsm.gz=common.jsm.gz \
    --file artefacts/extra-fresh-1500k.jnnw.gz=extra.jnnw.gz \
    --file artefacts/extra-fresh-1500k.jsm.gz=extra.jsm.gz \
    --out-dir "$SRC" --report "$ART/verified-resume-source.json" > "$W/fetch-resume.log" 2>&1
  gunzip -c "$SRC/common.jnnw.gz" > "$W/common.raw.jnnw"
  gunzip -c "$SRC/common.jsm.gz" > "$W/common.raw.jsm"
  gunzip -c "$SRC/extra.jnnw.gz" > "$W/extra.raw.jnnw"
  gunzip -c "$SRC/extra.jsm.gz" > "$W/extra.raw.jsm"
else
  phase generate-common-fresh-500k
  generate_fresh common "$COMMON_RECORDS" 10000
  phase generate-extra-fresh-1500k
  generate_fresh extra "$EXTRA_RECORDS" 100000
fi

phase assemble-three-arms
python3 tools/selfplay_frontier.py merge \
  --pair "$W/common.raw.jnnw" "$W/common.raw.jsm" \
  --out-data "$W/f500.raw.jnnw" --out-meta "$W/f500.raw.jsm" \
  --renamespace-nested --manifest "$ART/f500-assembly.json" > "$W/f500-assembly.log" 2>&1
python3 tools/selfplay_frontier.py merge \
  --pair "$W/common.raw.jnnw" "$W/common.raw.jsm" \
  --pair "$W/extra.raw.jnnw" "$W/extra.raw.jsm" \
  --out-data "$W/f2m.raw.jnnw" --out-meta "$W/f2m.raw.jsm" \
  --renamespace-nested --manifest "$ART/f2m-assembly.json" > "$W/f2m-assembly.log" 2>&1
python3 tools/selfplay_frontier.py merge \
  --pair "$W/common.raw.jnnw" "$W/common.raw.jsm" \
  --pair "$W/hist-g1.jnnw" "$W/hist-g1.jsm" \
  --pair "$W/hist-g2.jnnw" "$W/hist-g2.jsm" \
  --pair "$W/hist-g3.jnnw" "$W/hist-g3.jsm" \
  --out-data "$W/r2m.raw.jnnw" --out-meta "$W/r2m.raw.jsm" \
  --renamespace-nested --manifest "$ART/r2m-assembly.json" > "$W/r2m-assembly.log" 2>&1
python3 - "$W" "$ART/m1-arm-contract.json" <<'PY'
import hashlib,json,struct,sys
from pathlib import Path
w=Path(sys.argv[1])
def info(name):
    data=(w/name).read_bytes()
    if data[:4] != b"JNNW": raise SystemExit(f"bad {name}")
    return {"records":struct.unpack_from("<I",data,4)[0],"sha256":hashlib.sha256(data).hexdigest()}
common=info("common.raw.jnnw"); f500=info("f500.raw.jnnw"); f2m=info("f2m.raw.jnnw"); r2m=info("r2m.raw.jnnw")
if common["records"] != 500000 or f500["records"] != 500000 or f2m["records"] != 2000000 or r2m["records"] != 2000000:
    raise SystemExit("arm record count mismatch")
if (w/"common.raw.jnnw").read_bytes()[8:] != (w/"f500.raw.jnnw").read_bytes()[8:]:
    raise SystemExit("F500 is not the exact common source")
common_payload=(w/"common.raw.jnnw").read_bytes()[8:]
for arm in ("f2m.raw.jnnw","r2m.raw.jnnw"):
    with open(w/arm,"rb") as h:
        h.read(8)
        if h.read(len(common_payload)) != common_payload:
            raise SystemExit(f"{arm} does not begin with exact common source")
payload={"schema":1,"common_fresh":common,"arms":{"F500":f500,"F2M":f2m,"R2M":r2m},
 "same_parent":True,"same_common_500k":True,"r2m_exact_history":"C0_G1_G2_G3",
 "starts":"standard","top3":False,"role_reweight_v2":False,"geometry":"8cf","search":"Q00"}
Path(sys.argv[2]).write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
PY
gzip -n -c "$W/common.raw.jnnw" > "$ART/common-fresh-500k.jnnw.gz"
gzip -n -c "$W/common.raw.jsm" > "$ART/common-fresh-500k.jsm.gz"
gzip -n -c "$W/extra.raw.jnnw" > "$ART/extra-fresh-1500k.jnnw.gz"
gzip -n -c "$W/extra.raw.jsm" > "$ART/extra-fresh-1500k.jsm.gz"

fit_arm(){
  local arm="$1" lower="$2" holdout iters
  phase "split-and-fit-$arm"
  python3 tools/selfplay_frontier.py split \
    --data "$W/$lower.raw.jnnw" --meta "$W/$lower.raw.jsm" \
    --out-data "$W/$lower.fit.jnnw" --out-meta "$W/$lower.fit.jsm" \
    --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
    --manifest "$ART/$lower-split.json" > "$W/$lower-split.log" 2>&1
  holdout="$("$W/venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["holdout_records"])' "$ART/$lower-split.json")"
  [ "$holdout" -gt 0 ] || die "$arm holdout missing"
  "$J" --dump-eval-features "$W/$lower.fit.jnnw" "$W/$lower.feat" > "$W/$lower-features.log" 2>&1
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
    /usr/bin/time -v timeout "$FIT_TIMEOUT" "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
      --data "$W/$lower.fit.jnnw" --feat "$W/$lower.feat" --out "$W/$lower.pjtw" \
      --target wdl --loss logistic --color-fold --tempo-stage --warm-start "$W/parent.pjtw" \
      --holdout-count "$holdout" --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
      --optimizer-report "$ART/$lower-optimizer.json" \
      > "$W/$lower-fit.log" 2> "$W/$lower-fit-time.log"
  [ -s "$W/$lower.pjtw" ] || die "$arm model missing"
  grep -q 'HOLDOUT_LOGLOSS' "$W/$lower-fit.log" || die "$arm holdout result missing"
  iters="$(sed -n 's/.*iters=\([0-9][0-9]*\).*/\1/p' "$W/$lower-fit.log" | tail -1)"
  "$W/venv/bin/python" - "$ART/$lower-optimizer.json" <<'PY' || die "$arm optimiser did not converge"
import json,sys
p=json.load(open(sys.argv[1]))
if not p.get("success"): raise SystemExit(1)
PY
  gzip -n -c "$W/$lower.pjtw" > "$ART/$lower.pjtw.gz"
  rm -f "$W/$lower.feat"
}
fit_arm F500 f500
fit_arm F2M f2m
fit_arm R2M r2m

phase publish-training-screen
"$W/venv/bin/python" - "$W" "$ART" "$EXPECTED_CODE_SHA" <<'PY'
import hashlib,json,pathlib,re,sys
w,art=map(pathlib.Path,sys.argv[1:3]); code=sys.argv[3]
arms={}
for name in ("f500","f2m","r2m"):
    log=(w/f"{name}-fit.log").read_text()
    timing=(w/f"{name}-fit-time.log").read_text()
    arms[name.upper()]={"model_sha256":hashlib.sha256((w/f"{name}.pjtw").read_bytes()).hexdigest(),
      "iterations":int(re.search(r"iters=(\d+)",log).group(1)),
      "holdout_logloss":float(re.search(r"HOLDOUT_LOGLOSS\s+([0-9.]+)",log).group(1)),
      "max_rss_kib":int(re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)",timing).group(1))}
payload={"schema":1,"verdict":"M1_TRAINING_SCREEN_READY","code_sha":code,
 "parent":"C0_A_G3","arms":arms,"promotion_authorized":False,
 "evaluation_authorized":True,"automatic_next_job":None}
(art/"m1-training-summary.json").write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
(art/"JASS_CONTROL_SUMMARY.json").write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
(art/"VERDICT__M1_TRAINING_SCREEN_READY").write_text("M1_TRAINING_SCREEN_READY\n")
(art/"PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
(art/"AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")
PY
phase complete
say "M1_TRAINING_SCREEN_READY promotion=false automatic_next_job=null"
