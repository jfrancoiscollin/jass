#!/usr/bin/env bash
# template: L3-PURE maturity M0 coverage audit v1
# description: read-only bucket visits for C0 A G1-G3 and P1-0842 G1-G4
# expected_duration: 5-15 min on cpx62; no training or automatic continuation
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${C0_PREFIX:?}"; : "${P1_PREFIX:?}"
: "${EXPECTED_C0_JOB:?}"; : "${EXPECTED_P1_JOB:?}"
FULL_RUN_APPROVED="${FULL_RUN_APPROVED:-0}"; SCIENTIFIC_GO="${SCIENTIFIC_GO:-0}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; C0="$JASS_RESULT_DIR/c0"; P1="$JASS_RESULT_DIR/p1"; GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART" "$C0" "$P1" "$GEOM"
exec 9>"$JASS_RESULT_DIR/job.lock"; flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; : > "$RES"; : > "$PROG"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT; set +e; [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"; [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"; [ -d "$W" ] && (cd "$W" && find . -type f -name '*.log' -print0|tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null||true; rm -rf "$W" "$C0" "$P1" "$GEOM" 2>/dev/null||true; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR

say "=== $JASS_JOB_ID — L3-PURE M0 coverage audit ==="
[ "$FULL_RUN_APPROVED" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ "$SCIENTIFIC_GO" = 1 ] || die "SCIENTIFIC_GO=1 missing"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
NPROC="$(nproc)"; [ "$NPROC" -ge 8 ] || die "need >=8 CPUs"
FREE_MB="$(df -Pm "$JASS_RESULT_DIR"|awk 'NR==2{print $4}')"; [ "${FREE_MB:-0}" -ge 5000 ] || die "<5 GiB free"
say "preflight: nproc=$NPROC free_mb=$FREE_MB source_corpora=7"
python3 -m py_compile jobs/tools/fetch_result_files.py jobs/tools/l3_bucket_visits.py jobs/tools/l3_pure_m0_coverage.py
python3 jobs/tests/test_l3_pure_m0.py > "$W/test-m0.log" 2>&1 || die "M0 tests red"

echo 'stage=fetch_sources' > "$PROG"
C0_ARGS=(); for g in 1 2 3; do C0_ARGS+=(--file "artefacts/g${g}-selfplay.jnnw.gz=g${g}.jnnw.gz"); done
P1_ARGS=(); for g in 1 2 3 4; do P1_ARGS+=(--file "artefacts/g${g}-selfplay.jnnw.gz=g${g}.jnnw.gz"); done
python3 jobs/tools/fetch_result_files.py --prefix "$C0_PREFIX" "${C0_ARGS[@]}" --file artefacts/l3-pure-manifest.json=manifest.json --out-dir "$C0" --report "$ART/verified-c0-source.json" > "$W/fetch-c0.log" 2>&1 || die "C0 source unavailable"
python3 jobs/tools/fetch_result_files.py --prefix "$P1_PREFIX" "${P1_ARGS[@]}" --file artefacts/l3-pure-p1-manifest.json=manifest.json --out-dir "$P1" --report "$ART/verified-p1-source.json" > "$W/fetch-p1.log" 2>&1 || die "P1 source unavailable"
python3 - "$C0" "$P1" "$ART" "$EXPECTED_C0_JOB" "$EXPECTED_P1_JOB" <<'PY'
import hashlib,json,sys
from pathlib import Path
c0,p1,art=map(Path,sys.argv[1:4]); c0job,p1job=sys.argv[4:6]
c0m=json.loads((c0/'manifest.json').read_text()); p1m=json.loads((p1/'manifest.json').read_text())
c0v=json.loads((art/'verified-c0-source.json').read_text()); p1v=json.loads((art/'verified-p1-source.json').read_text())
if c0v.get('job_id')!=c0job or p1v.get('job_id')!=p1job: raise SystemExit('source job mismatch')
if c0m.get('arm')!='A' or c0m.get('generations')!=3 or c0m.get('scientific_status')!='complete_generation_chain': raise SystemExit('invalid C0 manifest')
if p1m.get('experiment')!='L3-PURE-P1' or p1m.get('scientific_status')!='complete_p1_training' or p1m.get('recipe',{}).get('generations')!=4: raise SystemExit('invalid P1 manifest')
# The training corpora are verified by result inventory/checksums. Record their hashes again for the audit contract.
files={}
for label,root,n in (('c0',c0,3),('p1',p1,4)):
    files[label]={}
    for g in range(1,n+1):
        path=root/f'g{g}.jnnw.gz'; files[label][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
(art/'m0-coverage-source-contract.json').write_text(json.dumps({'schema':1,'c0_job':c0job,'p1_job':p1job,'objects':files},indent=2,sort_keys=True)+'\n')
PY
for g in 1 2 3; do gunzip -c "$C0/g${g}.jnnw.gz" > "$W/c0-g${g}.jnnw"; done
for g in 1 2 3 4; do gunzip -c "$P1/g${g}.jnnw.gz" > "$W/p1-g${g}.jnnw"; done

printf 'stage=generate_8cf_geometry\n' > "$PROG"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen-patterns.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
NPAT="$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')"; [ "$NPAT" -eq 4251528 ] || die "8cf geometry mismatch"

printf 'stage=measure_per_generation\n' > "$PROG"
for g in 1 2 3; do env PYTHONPATH="$GEOM:pattern_jass/tools" python3 jobs/tools/l3_bucket_visits.py --data "$W/c0-g${g}.jnnw" --out "$ART/c0-g${g}-coverage.json" > "$W/c0-g${g}.log" 2>&1; done
for g in 1 2 3 4; do env PYTHONPATH="$GEOM:pattern_jass/tools" python3 jobs/tools/l3_bucket_visits.py --data "$W/p1-g${g}.jnnw" --out "$ART/p1-g${g}-coverage.json" > "$W/p1-g${g}.log" 2>&1; done
printf 'stage=measure_cumulative\n' > "$PROG"
env PYTHONPATH="$GEOM:pattern_jass/tools" python3 jobs/tools/l3_bucket_visits.py --data "$W/c0-g1.jnnw" "$W/c0-g2.jnnw" "$W/c0-g3.jnnw" --out "$ART/c0-g1-g3-cumulative-coverage.json" > "$W/c0-cumulative.log" 2>&1
env PYTHONPATH="$GEOM:pattern_jass/tools" python3 jobs/tools/l3_bucket_visits.py --data "$W/p1-g1.jnnw" "$W/p1-g2.jnnw" "$W/p1-g3.jnnw" "$W/p1-g4.jnnw" --out "$ART/p1-g1-g4-cumulative-coverage.json" > "$W/p1-cumulative.log" 2>&1

printf 'stage=aggregate\n' > "$PROG"
python3 jobs/tools/l3_pure_m0_coverage.py \
  --c0-generation "$ART/c0-g1-coverage.json" --c0-generation "$ART/c0-g2-coverage.json" --c0-generation "$ART/c0-g3-coverage.json" \
  --p1-generation "$ART/p1-g1-coverage.json" --p1-generation "$ART/p1-g2-coverage.json" --p1-generation "$ART/p1-g3-coverage.json" --p1-generation "$ART/p1-g4-coverage.json" \
  --c0-cumulative "$ART/c0-g1-g3-cumulative-coverage.json" --p1-cumulative "$ART/p1-g1-g4-cumulative-coverage.json" \
  --out "$ART/m0-coverage-audit.json" --summary-out "$ART/JASS_CONTROL_SUMMARY.json" | tee -a "$RES"
python3 - "$ART/m0-coverage-audit.json" "$ART" <<'PY'
import json,sys
from pathlib import Path
p=json.load(open(sys.argv[1])); art=Path(sys.argv[2]); c=p['c0_a']['cumulative']; q=p['p1_0842']['cumulative']
bp=lambda x:int(round(float(x)*10000))
markers=['VERDICT__M0_COVERAGE_AUDIT_READY',f"C0_A_CUMULATIVE_COVERAGE_BP__{bp(c['coverage_fraction']):04d}",f"P1_0842_CUMULATIVE_COVERAGE_BP__{bp(q['coverage_fraction']):04d}",f"COVERAGE_LEADER_DIAGNOSTIC_ONLY__{p['coverage_leader_diagnostic_only']}",'M1_AUTHORIZED__FALSE']
for name in markers: (art/name).write_text(name+'\n')
PY
printf 'stage=complete\n' > "$PROG"
say "=== M0 coverage audit complete; coverage is diagnostic only ==="
