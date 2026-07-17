#!/usr/bin/env bash
# id: cpx62-0775-forkc-t1-v1
# description: T1 fork-c weak bootstrap, guarded by parent/fixed + absolute strong T0
# expected_duration: 2-4 h; enqueue only after 0774 scientific_status=proceed_t1
set -Eeuo pipefail
: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
: "${JASS_ARTEFACT_DIR:?runner v3 must provide JASS_ARTEFACT_DIR}"
: "${FORKC_C0_RUN_PREFIX:?exact completed 0774 prefix required}"
: "${MTC_AUDIT_RUN_PREFIX:?exact completed cpx62 MTC audit prefix required}"
export TMPDIR="$JASS_RESULT_DIR/tmp"; mkdir -p "$TMPDIR"
PRE="$JASS_RESULT_DIR/prechecks"; mkdir -p "$PRE"
python3 jobs/tools/fetch_result_files.py --prefix "$FORKC_C0_RUN_PREFIX" \
  --file artefacts/c0-decision.json=c0-decision.json --out-dir "$PRE" \
  --report "$JASS_ARTEFACT_DIR/verified-c0-result.json"
python3 jobs/tools/fetch_result_files.py --prefix "$MTC_AUDIT_RUN_PREFIX" \
  --file artefacts/mtc-audit.json=mtc-audit.json --out-dir "$PRE" \
  --report "$JASS_ARTEFACT_DIR/verified-mtc-audit.json"
export JASS_EGDB_PATH=/root/egdb_extracted/app
export JASS_EGDB_MTC_PATH=/root/egdb_mtc/app
python3 jobs/tools/mtc_audit.py --verify-manifest "$PRE/mtc-audit.json" \
  --expected-path "$JASS_EGDB_MTC_PATH" \
  --out "$JASS_ARTEFACT_DIR/mtc-verification.json"
cp "$PRE/c0-decision.json" "$JASS_ARTEFACT_DIR/scientific-summary.json"
set +e
python3 - "$PRE/c0-decision.json" "$PRE/mtc-audit.json" <<'PY'
import json,socket,sys
c0=json.load(open(sys.argv[1])); mtc=json.load(open(sys.argv[2]))
if c0.get('scientific_status')=='stop_technical':
    print('fork C T1: C0 is technically incomplete', file=sys.stderr)
    raise SystemExit(2)
if c0.get('scientific_status')!='proceed_t1' or c0.get('decision')!='proceed':
    print('fork C T1: clean stop; C0 did not authorize proceed_t1')
    raise SystemExit(3)
if not mtc.get('audit_ok') or mtc.get('audit_level')!='complete' or mtc.get('concurrent_smoke_ok') is not True:
    raise SystemExit('complete MTC audit required')
if mtc.get('host') != socket.gethostname():
    raise SystemExit(f'MTC audit host mismatch: {mtc.get("host")} != {socket.gethostname()}')
PY
PRECHECK_RC=$?
set -e
case "$PRECHECK_RC" in
  0) ;;
  3) exit 0 ;;
  *) exit "$PRECHECK_RC" ;;
esac
export TOUR=T1-bis
export T1BIS_INPUTS_PREFIX="${JASS_OBJSTORE_REMOTE%/}/inputs/t1bis-adj-g1/forkc-weak-v1"
export ABSOLUTE_INPUTS_PREFIX="${JASS_OBJSTORE_REMOTE%/}/inputs/t1bis-adj-g1/v1"
export REQUIRE_ABSOLUTE_REFERENCE=1
export GYM_MIN_POS=150 MIN_PROTECTED_TIP_RATE=0.0 ALLOW_MTC_SKIP=0
export NSH_GEN_TOTAL=8 NSH_RELABEL_TOTAL=8 NSH_CONV_TOTAL=4 NSH_GATE_TOTAL=4
export PAR_GEN=8 PAR_RELABEL=8 PAR_CONV=4 PAR_GATE=4 JASS_BUILD_JOBS=8
export CACHE_MB_RELABEL=384 CACHE_MB_CONV=192
exec bash jobs/templates/t1bis-adj-g1-runner-v3-native.sh
