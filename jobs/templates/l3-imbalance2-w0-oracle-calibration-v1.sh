#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Read-only calibration of adaptive role weights from immutable EGDB/Scan data.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${DIFFICULTY_REFERENCE_URI:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; mkdir -p "$W" "$ART"
RES="$W/RESULTS.txt"; : > "$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT; set +e; [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

say "=== $JASS_JOB_ID — L3-IMBALANCE2 W0 oracle-adaptive calibration ==="
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "${W0_CALIBRATION_GO:-0}" = 1 ] || die "W0_CALIBRATION_GO=1 missing"
python3 -m py_compile jobs/tools/fetch_result_files.py jobs/tools/imbalance2_oracle_weight_curve.py
python3 jobs/tests/test_imbalance2_oracle_weight_curve.py > "$W/tests.log" 2>&1 || die "W0 tests red"

python3 jobs/tools/fetch_result_files.py --prefix "$DIFFICULTY_REFERENCE_URI" \
  --file artefacts/imbalance2-a64-b64-difficulty-reference.json=reference.json \
  --out-dir "$W" --report "$ART/verified-reference.json" > "$W/fetch.log" 2>&1 \
  || die "immutable difficulty reference unavailable"

python3 jobs/tools/imbalance2_oracle_weight_curve.py \
  --reference "$W/reference.json" --prior-strength 32 \
  --out "$ART/w0-oracle-weight-calibration.json" | tee -a "$RES"

python3 - "$ART/w0-oracle-weight-calibration.json" "$ART/JASS_CONTROL_SUMMARY.json" "$ART" <<'PY'
import json,re,sys
from pathlib import Path
src,out,art=sys.argv[1:]
d=json.load(open(src,encoding='utf-8'))
summary={
  'protocol':d['protocol'],'decision':d['decision'],'classification':d['classification'],
  'recommendation':d['recommendation_for_human_review'],'formula':d['formula'],
  'diagnostics':d['diagnostics'],'training_authorized':False,
  'weight_policy_authorized':False,'promotion_authorized':False,'automatic_next_job':None,
}
Path(out).write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def safe(value): return re.sub(r'[^A-Z0-9._+-]+','_',str(value).upper()).strip('_')
for name,value in (
  ('VERDICT',d['decision']),('CLASSIFICATION',d['classification']),
  ('RECOMMENDATION',d['recommendation_for_human_review']),
  ('DENSITY_ONLY_PASS',d['diagnostics']['density_only_hypothesis_pass']),
  ('POOL_STABILITY_PASS',d['diagnostics']['pool_stability_pass']),
  ('TRAINING_AUTHORIZED',False),('WEIGHT_POLICY_AUTHORIZED',False),
):
  Path(art,f'{name}__{safe(value)}').touch()
PY
say "W0 complete; full curve in R2, compact summary prepared for jass-control"
