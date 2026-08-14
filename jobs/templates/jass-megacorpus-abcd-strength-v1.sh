#!/usr/bin/env bash
# Common paired strength readout for MegaCorpus arms A/B/C/D.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${ABC_PREFIX:?}"; : "${EXPECTED_ABC_JOB:?}"; : "${EXPECTED_ABC_ATTEMPT:?}"
: "${D_PREFIX:?}"; : "${EXPECTED_D_JOB:?}"; : "${EXPECTED_D_ATTEMPT:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"; FORCE="$ART/force"
mkdir -p "$W" "$IN" "$ART" "$GEOM" "$FORCE"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

OPENING_ROOT="r2:jass-data/runs/home-0984bis-l3-pure-turnover-l2-preflight-v2/20260726T122615Z-5ef14ffe"
OPENING_JOB="home-0984bis-l3-pure-turnover-l2-preflight-v2"
OPENING_SHA="e7b89a5e3feade8919c8a498f424084deb0a2128c1712c9ca0a9547cf22b6df2"
NOPEN=250; NSH=8; PAR=2; FORCE_DEPTH=9; MOVETIME=0.1; BOOTSTRAP=200000
CACHE_MB=128
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
VENV_READY="$VENV/.jass-runtime-ready-v1"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

MON=""
monitor(){
  ( t0=$(date +%s)
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
        printf 'completed_force_files=%s\n' "$(find "$FORCE" -type f -name '*.json' | wc -l)"
      } >"$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 120
    done ) &
  MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$GEOM" "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-([0-9]+)-jass-megacorpus-abcd-strength-v1$ ]] ||
  die "invalid job nomenclature"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "explicit execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX contract mismatch"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
[ -f "$VENV_READY" ] || die "persistent numeric runtime absent; do not reinstall in this job"
PY="$VENV/bin/python"
"$PY" -c 'import numpy; assert numpy.__version__' || die "persistent numeric runtime invalid"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/jass_megacorpus_abcd_verdict.py \
  jobs/tools/run_jass_gate_bounded.py jobs/tools/jass_vs_jass_arch.py
"$PY" -m unittest jobs.tests.test_jass_megacorpus_abcd \
  jobs.tests.test_jass_megacorpus_abcd_templates >"$W/tests.log" 2>&1

stage fetch-authenticated-models-and-openings
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$ABC_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=abc-summary.json \
  --file artefacts/current_2m.pjtw.gz=A.pjtw.gz \
  --file artefacts/mega_eq_2m.pjtw.gz=B.pjtw.gz \
  --file artefacts/mega_full_4m.pjtw.gz=C.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-abc.json" >"$W/fetch-abc.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$D_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=d-summary.json \
  --file artefacts/D-c-prior-then-current.pjtw.gz=D.pjtw.gz \
  --file artefacts/abcd-static-readout.json=abcd-static-readout.json \
  --out-dir "$IN" --report "$ART/verified-d.json" >"$W/fetch-d.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$OPENING_ROOT" \
  --file artefacts/turnover-l2-eval-openings.fen=all-openings.fen \
  --file artefacts/turnover-l2-eval-openings.json=source-openings.json \
  --out-dir "$IN" --report "$ART/verified-openings.json" >"$W/fetch-openings.log" 2>&1
python3 - "$IN" "$ART" "$EXPECTED_ABC_JOB" "$EXPECTED_ABC_ATTEMPT" \
  "$EXPECTED_D_JOB" "$EXPECTED_D_ATTEMPT" "$OPENING_JOB" <<'PY'
import json,sys
from pathlib import Path
src,art=map(Path,sys.argv[1:3])
abc=json.load(open(art/'verified-abc.json')); d=json.load(open(art/'verified-d.json'))
op=json.load(open(art/'verified-openings.json'))
if (abc.get('job_id'),abc.get('attempt_id'),abc.get('result_state')) != (sys.argv[3],sys.argv[4],'completed'):
 raise SystemExit('ABC identity/state drift')
if (d.get('job_id'),d.get('attempt_id'),d.get('result_state')) != (sys.argv[5],sys.argv[6],'completed'):
 raise SystemExit('D identity/state drift')
if op.get('job_id')!=sys.argv[7] or op.get('result_state')!='completed': raise SystemExit('opening source drift')
if json.load(open(src/'abc-summary.json')).get('verdict')!='JASS_MEGACORPUS_ABC_FITS_READY':
 raise SystemExit('ABC verdict drift')
if json.load(open(src/'d-summary.json')).get('verdict')!='JASS_MEGACORPUS_ARM_D_FIT_READY':
 raise SystemExit('D verdict drift')
PY
[ "$(sha256sum "$IN/all-openings.fen" | awk '{print $1}')" = "$OPENING_SHA" ] ||
  die "opening pool hash drift"
for arm in A B C D; do gunzip -c "$IN/$arm.pjtw.gz" >"$W/$arm.pjtw"; done
"$PY" - "$IN/abc-summary.json" "$IN/d-summary.json" "$W" <<'PY'
import hashlib,json,sys
from pathlib import Path
abc=json.load(open(sys.argv[1])); d=json.load(open(sys.argv[2])); root=Path(sys.argv[3])
expected={
 'A':abc['arms']['CURRENT_2M']['model_raw_sha256'],
 'B':abc['arms']['MEGA_EQ_2M']['model_raw_sha256'],
 'C':abc['arms']['MEGA_FULL_4M']['model_raw_sha256'],
 'D':d['arm']['model_raw_sha256'],
}
for arm,digest in expected.items():
 actual=hashlib.sha256((root/f'{arm}.pjtw').read_bytes()).hexdigest()
 if actual != digest: raise SystemExit(f'{arm}: model hash differs from source certificate')
PY

stage select-preregistered-independent-opening-prefix
python3 - "$IN/all-openings.fen" "$W/openings-250.fen" "$ART/independent-openings-manifest.json" \
  "$OPENING_SHA" "$NOPEN" <<'PY'
import hashlib,json,sys
src,out,report,source_sha,n=sys.argv[1:]; n=int(n)
lines=[]
for raw in open(src):
 line=raw.split('#',1)[0].strip()
 if line: lines.append(line)
if len(lines)!=500: raise SystemExit(f'expected 500 source openings, got {len(lines)}')
payload=''.join(line+'\n' for line in lines[:n])
open(out,'w').write(payload)
json.dump({'schema':'jass.megacorpus.strength_openings.v1','source_sha256':source_sha,
 'source_openings':len(lines),'selection':'first_250_noncomment_lines_preregistered',
 'selected_openings':n,'selected_sha256':hashlib.sha256(payload.encode()).hexdigest(),
 'paired_colour_games_per_contrast':2*n},open(report,'w'),indent=2,sort_keys=True)
open(report,'a').write('\n')
PY

stage build-common-8cf-engine
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
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests >"$W/build.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB \
  ctest --test-dir "$W/build" --output-on-failure >"$W/ctest.log" 2>&1
J="$W/build/jass"

run_gate(){
  local view="$1" contrast="$2" candidate="$3" baseline="$4"; local budget=()
  [ "$view" = q00 ] && budget=(--depth "$FORCE_DEPTH") || budget=(--movetime "$MOVETIME")
  timeout 28800s "$PY" jobs/tools/run_jass_gate_bounded.py \
    --jass "$J" --pattern-a "$W/$candidate.pjtw" --pattern-b "$W/$baseline.pjtw" \
    --search-params-a "$Q00" --search-params-b "$Q00" \
    --openings-file "$W/openings-250.fen" "${budget[@]}" --pairs 1 \
    --max-plies 160 --nshards "$NSH" --max-parallel "$PAR" \
    --timeout 21600 --game-timeout 180 \
    --paired-bootstrap-samples "$BOOTSTRAP" --paired-bootstrap-seed 20260814 \
    --work-dir "$W/gate-$view-$contrast" --out "$FORCE/force-$view-$contrast.json" \
    >"$W/force-$view-$contrast.log" 2>&1
}
wait_wave(){
  local label="$1"; shift; local fail=0 pid
  for pid in "$@"; do wait "$pid" || fail=$((fail+1)); done
  [ "$fail" -eq 0 ] || die "$label: $fail gates failed"
}

CONTRASTS=(B_vs_A C_vs_B D_vs_A D_vs_C C_vs_A D_vs_B)
CANDIDATES=(B C D D C D)
BASELINES=(A B A C A B)
for view in q00 native; do
  for start in 0 2 4; do
    stage "force-$view-wave-$((start/2+1))"
    pids=()
    for offset in 0 1; do
      index=$((start+offset))
      run_gate "$view" "${CONTRASTS[$index]}" "${CANDIDATES[$index]}" "${BASELINES[$index]}" &
      pids+=("$!")
    done
    wait_wave "$view wave $((start/2+1))" "${pids[@]}"
  done
done

stage aggregate-preregistered-abcd-verdict
"$PY" jobs/tools/jass_megacorpus_abcd_verdict.py \
  --force-dir "$FORCE" --static-readout "$IN/abcd-static-readout.json" \
  --abc-summary "$IN/abc-summary.json" --d-summary "$IN/d-summary.json" \
  --opening-manifest "$ART/independent-openings-manifest.json" \
  --out "$ART/abcd-strength-readout.json" --summary-out "$ART/JASS_CONTROL_SUMMARY.json" \
  >"$W/verdict.log" 2>&1
touch "$ART/VERDICT__JASS_MEGACORPUS_ABCD_COMPARISONS_READY"
touch "$ART/PROMOTION_AUTHORIZED__FALSE" "$ART/AUTOMATIC_NEXT_JOB__NULL"
say "JASS_MEGACORPUS_ABCD_COMPARISONS_READY contrasts=6 views=2 paired_openings=250 promotion=false"
