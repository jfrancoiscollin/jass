#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# D1-X: read-only post-mortem of the failed D1-RC4 representation screen.
# No training, no self-play, no promotion and no automatic search-pilot chaining.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"
: "${JASS_RESULT_DIR:?}"
: "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"
: "${EXPECTED_CODE_SHA:?pin reviewed merged SHA}"
: "${P1_PREFIX:?immutable completed 0852 P1 prefix}"
: "${EXPECTED_P1_JOB_ID:?}"
: "${D1_PREFIX:?immutable completed 0872 D1 prefix}"
: "${EXPECTED_D1_JOB_ID:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
INPUTS="$JASS_RESULT_DIR/inputs"
SRC="$W/rc4-src"
BUILD="$W/build-rc4"
mkdir -p "$W" "$ART" "$INPUTS/p1" "$INPUTS/d1" "$SRC"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }

JASS_BUILD_JOBS="${JASS_BUILD_JOBS:-8}"
RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
: > "$RES"; : > "$PROG"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){
  rc=$?; trap - EXIT; set +e
  [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  [ -d "$W" ] && (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$SRC" "$BUILD" "$INPUTS" "$W"/*.feat "$W"/*.jnnw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

say "=== $JASS_JOB_ID — L3-IMBALANCE2 D1-X RC4 autopsy ==="
[ -z "$(git branch --show-current)" ] || die "runner worktree must be detached"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ "${SCIENTIFIC_GO:-0}" = 1 ] || die "SCIENTIFIC_GO=1 missing"
[ "${D1X_AUTOPSY_GO:-0}" = 1 ] || die "D1X_AUTOPSY_GO=1 missing"
[ "$(nproc)" -ge 4 ] || die "requires at least four CPUs"
[ "$(awk '/MemTotal:/ {printf "%d", $2/1024}' /proc/meminfo)" -ge 10000 ] || die "requires >=10 GiB RAM"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2 {print $4}')" -ge 8000 ] || die "less than 8 GiB free"

python3 -m py_compile \
  jobs/tools/fetch_result_files.py \
  jobs/tools/apply_imbalance2_rc4_patch.py \
  jobs/tools/imbalance2_d1x_autopsy.py
python3 jobs/tests/test_imbalance2_d1x.py > "$W/test-d1x.log" 2>&1 || die "D1-X tests failed"

echo "stage=fetch_immutable_sources" > "$PROG"
python3 jobs/tools/fetch_result_files.py --prefix "$P1_PREFIX" \
  --file artefacts/g4-source.jnnw.gz=g4-source.jnnw.gz \
  --file artefacts/l3-imbalance2-p1-manifest.json=p1-manifest.json \
  --expected-state completed --out-dir "$INPUTS/p1" --report "$ART/verified-p1-source.json" \
  > "$W/fetch-p1.log" 2>&1 || die "P1 source fetch failed"
python3 jobs/tools/fetch_result_files.py --prefix "$D1_PREFIX" \
  --file artefacts/d1-rc4-decision.json=d1-rc4-decision.json \
  --file artefacts/d1-rc4-generalist.json=d1-rc4-generalist.json \
  --file artefacts/d1-c64-d64-raw-reports.tar.gz=d1-raw-reports.tar.gz \
  --file artefacts/d1-sentinel-replays.tar.gz=d1-sentinel-replays.tar.gz \
  --file artefacts/control-refit.pjtw.gz=control-refit.pjtw.gz \
  --file artefacts/rc4.pjtw.gz=rc4.pjtw.gz \
  --file artefacts/plateau-c.jnnw.gz=plateau-c.jnnw.gz \
  --file artefacts/plateau-d.jnnw.gz=plateau-d.jnnw.gz \
  --file artefacts/d1-fit-contract.json=d1-fit-contract.json \
  --file artefacts/rc4-source-transform.json=rc4-source-transform.json \
  --expected-state completed --out-dir "$INPUTS/d1" --report "$ART/verified-d1-source.json" \
  > "$W/fetch-d1.log" 2>&1 || die "D1 source fetch failed"

python3 - "$INPUTS" "$ART" "$EXPECTED_P1_JOB_ID" "$EXPECTED_D1_JOB_ID" <<'PY'
import gzip,hashlib,json,math,struct,sys
from pathlib import Path
root=Path(sys.argv[1]); art=Path(sys.argv[2]); p1id=sys.argv[3]; d1id=sys.argv[4]
for label,path,expected in (
 ('p1',art/'verified-p1-source.json',p1id),('d1',art/'verified-d1-source.json',d1id)):
 p=json.loads(path.read_text())
 if p.get('job_id') != expected or p.get('result_state') != 'completed' or p.get('exit_code') != 0:
  raise SystemExit(f'{label}: source identity/state mismatch')
p1=json.loads((root/'p1/p1-manifest.json').read_text())
if p1.get('lineage') != 'L3-IMBALANCE2-ROLE-V2' or p1.get('phase') != 'P1':
 raise SystemExit('P1 lineage mismatch')
raw=gzip.decompress((root/'p1/g4-source.jnnw.gz').read_bytes())
if raw[:4] != b'JNNW' or struct.unpack_from('<I',raw,4)[0] != 500000:
 raise SystemExit('immutable G4 source mismatch')
(root/'g4-source.jnnw').write_bytes(raw)
for pool in ('c','d'):
 data=gzip.decompress((root/f'd1/plateau-{pool}.jnnw.gz').read_bytes())
 if data[:4] != b'JNNW' or struct.unpack_from('<I',data,4)[0] != 1152:
  raise SystemExit(f'{pool.upper()}64 pool mismatch')
 (root/f'plateau-{pool}.jnnw').write_bytes(data)
d=json.loads((root/'d1/d1-rc4-decision.json').read_text())
g=json.loads((root/'d1/d1-rc4-generalist.json').read_text())
macro=d['paired']['macro_equal_stratum']
checks=[
 (d.get('decision') == 'D1_RC4_NO_GO','D1 verdict'),
 (abs(float(macro['rc4_minus_control_failure_cost'])-0.003038) < 1e-5,'macro delta'),
 (int(macro['nonworse_strata']) == 9,'nonworse strata'),
 (int(d['sentinel_gate']['corrected_representation_cases']) == 0,'sentinel corrections'),
 (abs(float(d['sentinel_gate']['throughput']['rc4_over_control'])-0.935302) < 1e-4,'throughput'),
 (abs(float(g['rc4_score_rate'])-0.4140625) < 1e-8 and g.get('pass') is False,'generalist'),
]
for ok,label in checks:
 if not ok: raise SystemExit(f'reviewed D1 metric mismatch: {label}')
fit=json.loads((root/'d1/d1-fit-contract.json').read_text())
if fit.get('control',{}).get('n_ext') != 120 or fit.get('rc4',{}).get('n_ext') != 124:
 raise SystemExit('D1 fit geometry mismatch')
proof={'schema':1,'protocol':'d1x-immutable-source-contract','p1_job_id':p1id,'d1_job_id':d1id,
 'g4_source_records':500000,'c64_records':1152,'d64_records':1152,
 'reviewed_d1_decision':'D1_RC4_NO_GO','training_records_created':0,'selfplay_games':0,
 'scan_used':False,'promotion_authorized':False,'automatic_next_job':None}
(art/'source-contract.json').write_text(json.dumps(proof,indent=2,sort_keys=True)+'\n')
PY

# Rebuild only the reviewed experimental feature extractor.  No fit is run.
echo "stage=build_rc4_feature_extractor" > "$PROG"
git archive "$EXPECTED_CODE_SHA" | tar -x -C "$SRC"
python3 jobs/tools/apply_imbalance2_rc4_patch.py --source-root "$SRC" --report "$ART/rc4-source-transform-replayed.json" \
  > "$W/rc4-patch.log" 2>&1
python3 "$SRC/pattern_jass/tools/gen_patterns.py" --emit --variant 8cf > "$W/gen-patterns.log" 2>&1
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
cmake -S "$SRC" -B "$BUILD" $FLAGS -DCMAKE_CXX_FLAGS=-DJASS_ROLE_CONVERSION=1 > "$W/cmake.log" 2>&1
cmake --build "$BUILD" -j"$JASS_BUILD_JOBS" --target jass > "$W/build.log" 2>&1
JRC4="$BUILD/jass"
[ -x "$JRC4" ] || die "RC4 feature extractor build missing"

echo "stage=dump_feature_activity" > "$PROG"
"$JRC4" --dump-eval-features "$INPUTS/g4-source.jnnw" "$W/train.feat" > "$W/train-features.log" 2>&1
"$JRC4" --dump-eval-features "$INPUTS/plateau-c.jnnw" "$W/c64.feat" > "$W/c64-features.log" 2>&1
"$JRC4" --dump-eval-features "$INPUTS/plateau-d.jnnw" "$W/d64.feat" > "$W/d64-features.log" 2>&1

echo "stage=aggregate_autopsy" > "$PROG"
python3 jobs/tools/imbalance2_d1x_autopsy.py \
  --decision "$INPUTS/d1/d1-rc4-decision.json" \
  --generalist "$INPUTS/d1/d1-rc4-generalist.json" \
  --control-model "$INPUTS/d1/control-refit.pjtw.gz" \
  --rc4-model "$INPUTS/d1/rc4.pjtw.gz" \
  --raw-reports "$INPUTS/d1/d1-raw-reports.tar.gz" \
  --sentinel-replays "$INPUTS/d1/d1-sentinel-replays.tar.gz" \
  --train-feat "$W/train.feat" --train-data "$INPUTS/g4-source.jnnw" \
  --pool-c-feat "$W/c64.feat" --pool-c-data "$INPUTS/plateau-c.jnnw" \
  --pool-d-feat "$W/d64.feat" --pool-d-data "$INPUTS/plateau-d.jnnw" \
  --openings data/dilf_combinations.fen \
  --out "$ART/d1x-rc4-autopsy.json" > "$W/autopsy.log" 2>&1

python3 - "$ART/d1x-rc4-autopsy.json" "$RES" <<'PY'
import json,sys
p=json.load(open(sys.argv[1])); a=p['feature_activity']['training_source']; m=p['model_analysis']
with open(sys.argv[2],'a') as f:
 f.write(f"decision={p['decision']}\n")
 f.write(f"classification={p['classification']}\n")
 f.write(f"training_role_domain_rate={a['role_domain_rate']:.6f} any_feature_rate={a['any_rc4_nonzero_rate']:.6f}\n")
 f.write(f"max_abs_rc4_weight_raw={m['max_abs_rc4_weight_raw']}\n")
 f.write("search_pilot_authorized=false training_authorized=false promotion_authorized=false automatic_next_job=null\n")
PY

echo "stage=completed" > "$PROG"
say "=== D1-X complete; search-only pilot remains human-gated ==="
