#!/usr/bin/env bash
# template: L3-PURE C0/P1 convex meta-eval screen + independent confirmation
# description: blend immutable parent weights; no training/self-play; compare selected blend to both parents
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${C0_PREFIX:?}"; : "${P1_PREFIX:?}"
: "${EXPECTED_C0_JOB:?}"; : "${EXPECTED_P1_JOB:?}"

SCREEN_NOPEN="${SCREEN_NOPEN:-128}"
CONFIRM_NOPEN="${CONFIRM_NOPEN:-256}"
SCREEN_DEPTH="${SCREEN_DEPTH:-8}"
CONFIRM_DEPTH="${CONFIRM_DEPTH:-9}"
MOVETIME="${MOVETIME:-0.3}"
PAR_GATE="${PAR_GATE:-12}"
GAME_TIMEOUT="${GAME_TIMEOUT:-100}"
JASS_BUILD_JOBS="${JASS_BUILD_JOBS:-4}"
FULL_RUN_APPROVED="${FULL_RUN_APPROVED:-0}"
SCIENTIFIC_GO="${SCIENTIFIC_GO:-0}"
ALPHAS=(0.25 0.50 0.75 0.875)
TAGS=(c0w0250 c0w0500 c0w0750 c0w0875)
Q00_KEYS=63

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"
C0="$JASS_RESULT_DIR/c0"; P1="$JASS_RESULT_DIR/p1"
mkdir -p "$W" "$ART" "$C0" "$P1"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/STAGE.txt"
: > "$RES"; echo preflight > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
set_stage(){ echo "$1" > "$STAGE"; say "stage=$1 time_fr=$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"; }
MONITOR_PID=""
monitor(){ ( while true; do { TZ=Europe/Paris date '+time_fr=%Y-%m-%dT%H:%M:%S%z'; printf 'stage=%s\n' "$(cat "$STAGE" 2>/dev/null||echo ?)"; df -Pm "$JASS_RESULT_DIR"|awk 'NR==2{printf "free_mb=%s\n",$4}'; printf 'gate_results=%s\n' "$(find "$ART" -type f -name '*.json' 2>/dev/null|wc -l)"; } > "$PROG.tmp"; mv "$PROG.tmp" "$PROG"; sleep 300; done ) & MONITOR_PID="$!"; }
finalize(){ rc=$?; trap - EXIT TERM INT; set +e; [ -n "$MONITOR_PID" ] && { kill "$MONITOR_PID" 2>/dev/null; wait "$MONITOR_PID" 2>/dev/null; }; [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"; [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"; [ -d "$W" ] && (cd "$W" && find . -type f -name '*.log' -print0|tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null||true; rm -rf "$W/build8" "$W"/gate-* "$C0" "$P1" 2>/dev/null||true; exit "$rc"; }
trap finalize EXIT TERM INT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR

say "=== $JASS_JOB_ID — L3-PURE C0/P1 convex meta-eval ==="
[ "$FULL_RUN_APPROVED" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ "$SCIENTIFIC_GO" = 1 ] || die "SCIENTIFIC_GO=1 missing"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "$SCREEN_NOPEN" -eq 128 ] && [ "$CONFIRM_NOPEN" -eq 256 ] || die "opening-count contract mismatch"
[ "$SCREEN_DEPTH" -eq 8 ] && [ "$CONFIRM_DEPTH" -eq 9 ] && [ "$MOVETIME" = 0.3 ] || die "budget contract mismatch"
[ "$(nproc)" -ge 16 ] || die "requires cpx62 >=16 CPUs"
[ "$(df -Pm "$JASS_RESULT_DIR"|awk 'NR==2{print $4}')" -ge 8000 ] || die "<8 GiB free"
monitor
python3 -m py_compile tools/blend_pjtw.py jobs/tools/fetch_result_files.py jobs/tools/l3_pure_m0_sources.py \
  jobs/tools/l3_pure_meta_blend.py jobs/tools/run_jass_gate_bounded.py jobs/tools/validate_opening_pool.py
python3 jobs/tests/test_blend_pjtw.py > "$W/test-blend.log" 2>&1 || die "blend tests red"
python3 jobs/tests/test_l3_pure_meta_blend.py > "$W/test-meta.log" 2>&1 || die "meta aggregation tests red"
python3 jobs/tests/test_run_jass_gate.py > "$W/test-gate.log" 2>&1 || die "gate tests red"
python3 jobs/tests/test_validate_opening_pool.py > "$W/test-openings.log" 2>&1 || die "opening tests red"

set_stage fetch-verified-sources
python3 jobs/tools/fetch_result_files.py --prefix "$C0_PREFIX" \
  --file artefacts/g3.pjtw.gz=g3.pjtw.gz --file artefacts/l3-pure-manifest.json=manifest.json \
  --out-dir "$C0" --report "$ART/verified-c0-source.json" > "$W/fetch-c0.log" 2>&1 || die "C0 source unavailable"
python3 jobs/tools/fetch_result_files.py --prefix "$P1_PREFIX" \
  --file artefacts/g4.pjtw.gz=g4.pjtw.gz --file artefacts/l3-pure-p1-manifest.json=manifest.json \
  --out-dir "$P1" --report "$ART/verified-p1-source.json" > "$W/fetch-p1.log" 2>&1 || die "P1 source unavailable"
python3 jobs/tools/l3_pure_m0_sources.py \
  --c0-dir "$C0" --p1-dir "$P1" --verified-c0 "$ART/verified-c0-source.json" --verified-p1 "$ART/verified-p1-source.json" \
  --expected-c0-job "$EXPECTED_C0_JOB" --expected-p1-job "$EXPECTED_P1_JOB" \
  --out "$ART/meta-source-contract.json" > "$W/source-contract.log" 2>&1 || { cat "$W/source-contract.log"|tee -a "$RES"; die "source contract failed"; }
cat "$W/source-contract.log" | tee -a "$RES"
gunzip -c "$C0/g3.pjtw.gz" > "$W/c0-a-g3.pjtw"
gunzip -c "$P1/g4.pjtw.gz" > "$W/p1-0842-g4.pjtw"
Q00_SEARCH="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["p1_q00_search_params"])' "$ART/meta-source-contract.json")"
[ "$(awk -F, '{print NF}' <<< "$Q00_SEARCH")" -eq "$Q00_KEYS" ] || die "Q00 not fully pinned"

set_stage create-blend-family
for i in "${!ALPHAS[@]}"; do
  alpha="${ALPHAS[$i]}"; tag="${TAGS[$i]}"
  python3 tools/blend_pjtw.py --parent-a "$W/c0-a-g3.pjtw" --parent-b "$W/p1-0842-g4.pjtw" \
    --alpha-a "$alpha" --out "$W/blend-$tag.pjtw" --report "$ART/blend-$tag.json" \
    > "$W/blend-$tag.log" 2>&1 || die "blend $tag failed"
done

set_stage build-8cf
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl > "$W/clone.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || die "EGDB unavailable"; export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB=128
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
cmake --build "$W/build8" -j"$JASS_BUILD_JOBS" --target jass > "$W/build8.log" 2>&1
J8="$W/build8/jass"; [ -x "$J8" ] || die "missing jass binary"

set_stage independent-opening-pools
"$J8" --gen-opening-pool 768 "$W/previous-reinforcement.fen" 8 32 20 271828 > "$W/open-prev.log" 2>&1
"$J8" --gen-opening-pool "$SCREEN_NOPEN" "$W/open-screen.fen" 8 32 20 161803 > "$W/open-screen.log" 2>&1
python3 jobs/tools/validate_opening_pool.py --pool "$W/open-screen.fen" --expected "$SCREEN_NOPEN" \
  --exclude data/dilf_combinations.fen --exclude "$W/previous-reinforcement.fen" --generator-seed 161803 \
  --out "$ART/screen-openings-manifest.json" > "$W/validate-screen.log" 2>&1 || die "screen pool invalid"
"$J8" --gen-opening-pool "$CONFIRM_NOPEN" "$W/open-confirm.fen" 8 32 20 141421 > "$W/open-confirm.log" 2>&1
python3 jobs/tools/validate_opening_pool.py --pool "$W/open-confirm.fen" --expected "$CONFIRM_NOPEN" \
  --exclude data/dilf_combinations.fen --exclude "$W/previous-reinforcement.fen" --exclude "$W/open-screen.fen" \
  --generator-seed 141421 --out "$ART/confirm-openings-manifest.json" > "$W/validate-confirm.log" 2>&1 || die "confirm pool invalid"

run_gate(){ local label="$1" pattern_a="$2" pattern_b="$3" openings="$4" nshards="$5"; shift 5
  timeout 14400 python3 jobs/tools/run_jass_gate_bounded.py --jass "$J8" \
    --pattern-a "$pattern_a" --pattern-b "$pattern_b" --search-params-a "$Q00_SEARCH" --search-params-b "$Q00_SEARCH" \
    --openings-file "$openings" --pairs 1 --nshards "$nshards" --max-parallel "$PAR_GATE" --timeout 10800 \
    --game-timeout "$GAME_TIMEOUT" --work-dir "$W/gate-$label" --out "$ART/$label.json" "$@" \
    > "$W/$label.log" 2>&1 || { cat "$W/$label.log"|tee -a "$RES"; die "$label failed"; }
}

set_stage screen-blends-depth8
for tag in "${TAGS[@]}"; do
  run_gate "screen-$tag-vs-c0" "$W/blend-$tag.pjtw" "$W/c0-a-g3.pjtw" "$W/open-screen.fen" 8 --depth "$SCREEN_DEPTH"
  run_gate "screen-$tag-vs-p1" "$W/blend-$tag.pjtw" "$W/p1-0842-g4.pjtw" "$W/open-screen.fen" 8 --depth "$SCREEN_DEPTH"
done
python3 jobs/tools/l3_pure_meta_blend.py select --screen-dir "$ART" --alphas "${ALPHAS[@]}" \
  --out "$ART/meta-blend-selection.json" > "$W/select.log" 2>&1 || die "blend selection failed"
SELECTED_TAG="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["selected"]["tag"])' "$ART/meta-blend-selection.json")"
SELECTED_ALPHA="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["selected"]["alpha_c0"])' "$ART/meta-blend-selection.json")"
[ -f "$W/blend-$SELECTED_TAG.pjtw" ] || die "selected blend missing"
say "selected_blend=$SELECTED_TAG alpha_c0=$SELECTED_ALPHA"

set_stage confirm-selected-depth9
run_gate confirm-depth9-meta-vs-c0 "$W/blend-$SELECTED_TAG.pjtw" "$W/c0-a-g3.pjtw" "$W/open-confirm.fen" 16 --depth "$CONFIRM_DEPTH"
run_gate confirm-depth9-meta-vs-p1 "$W/blend-$SELECTED_TAG.pjtw" "$W/p1-0842-g4.pjtw" "$W/open-confirm.fen" 16 --depth "$CONFIRM_DEPTH"
set_stage confirm-selected-movetime
run_gate confirm-movetime-meta-vs-c0 "$W/blend-$SELECTED_TAG.pjtw" "$W/c0-a-g3.pjtw" "$W/open-confirm.fen" 16 --movetime "$MOVETIME"
run_gate confirm-movetime-meta-vs-p1 "$W/blend-$SELECTED_TAG.pjtw" "$W/p1-0842-g4.pjtw" "$W/open-confirm.fen" 16 --movetime "$MOVETIME"

set_stage aggregate-verdict
python3 jobs/tools/l3_pure_meta_blend.py confirm --selection "$ART/meta-blend-selection.json" \
  --depth-vs-c0 "$ART/confirm-depth9-meta-vs-c0.json" --movetime-vs-c0 "$ART/confirm-movetime-meta-vs-c0.json" \
  --depth-vs-p1 "$ART/confirm-depth9-meta-vs-p1.json" --movetime-vs-p1 "$ART/confirm-movetime-meta-vs-p1.json" \
  --out "$ART/meta-blend-verdict.json" --summary-out "$ART/JASS_CONTROL_SUMMARY.json" \
  > "$W/aggregate.log" 2>&1 || { cat "$W/aggregate.log"|tee -a "$RES"; die "aggregation failed"; }
cp "$W/blend-$SELECTED_TAG.pjtw" "$ART/meta-c0-p1-$SELECTED_TAG.pjtw"
gzip -n -c "$W/blend-$SELECTED_TAG.pjtw" > "$ART/meta-c0-p1-$SELECTED_TAG.pjtw.gz"
python3 - "$ART/meta-source-contract.json" "$ART/blend-$SELECTED_TAG.json" "$ART/meta-blend-verdict.json" "$ART/meta-model-manifest.json" <<'PY'
import json,sys
from pathlib import Path
source,blend,verdict,out=map(Path,sys.argv[1:])
p={"schema":1,"lineage":"L3-PURE-META-C0-P1","construction":"convex-weight-interpolation",
   "source_contract":json.load(source.open()),"blend":json.load(blend.open()),"evaluation":json.load(verdict.open()),
   "training_records":0,"self_play_games_for_training":0,"promotion_authorized":False,
   "training_continuation_authorized":False,"automatic_next_job":None}
out.write_text(json.dumps(p,indent=2,sort_keys=True)+"\n")
PY
python3 - "$ART/meta-blend-verdict.json" "$ART" "$RES" <<'PY'
import json,sys
from pathlib import Path
p=json.load(open(sys.argv[1])); art=Path(sys.argv[2]); res=Path(sys.argv[3]); s=p['selected']; c=p['combined_vs_c0']; q=p['combined_vs_p1']
def safe(v): return ('P' if v>=0 else 'M')+f'{abs(v):.1f}'.replace('.','_')
markers=[f"VERDICT__{p['decision']}",f"SELECTED_BLEND__{s['tag'].upper()}",
         f"META_ELO_VS_C0__{safe(c['meta_elo_vs_parent'])}",f"META_ELO_VS_P1__{safe(q['meta_elo_vs_parent'])}",
         "PROMOTION_AUTHORIZED__FALSE","TRAINING_CONTINUATION_AUTHORIZED__FALSE"]
for name in markers: (art/name).write_text(name+'\n')
with res.open('a') as f:
 f.write(f"decision={p['decision']} selected={s['tag']} alpha_c0={s['alpha_c0']} alpha_p1={s['alpha_p1']}\n")
 f.write(f"meta_vs_c0 score={c['meta_score_rate']:.6f} ci95=[{c['ci_low']:.6f},{c['ci_high']:.6f}] elo={c['meta_elo_vs_parent']:.2f} n={c['n']}\n")
 f.write(f"meta_vs_p1 score={q['meta_score_rate']:.6f} ci95=[{q['ci_low']:.6f},{q['ci_high']:.6f}] elo={q['meta_elo_vs_parent']:.2f} n={q['n']}\n")
 f.write('promotion_authorized=false training_continuation_authorized=false automatic_next_job=null\n')
PY
cat "$W/aggregate.log" | tee -a "$RES"
set_stage completed
say "=== meta blend comparison complete; human review required ==="
