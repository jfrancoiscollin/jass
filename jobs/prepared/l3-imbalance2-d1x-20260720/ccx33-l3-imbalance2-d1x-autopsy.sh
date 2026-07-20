#!/usr/bin/env bash
# id: ccx33-l3-imbalance2-d1x-autopsy
# description: read-only RC4 feature/weight/stratum/generalist autopsy after D1 no-go
# do not queue without explicit go and a reviewed merged EXPECTED_CODE_SHA
set -Eeuo pipefail

: "${EXPECTED_CODE_SHA:?set the reviewed merged jass SHA}"
export P1_PREFIX="r2:jass-data/runs/ccx33-0852-l3-imbalance2-role-v2-p1/20260720T073236Z-61839d1d"
export EXPECTED_P1_JOB_ID="ccx33-0852-l3-imbalance2-role-v2-p1"
export D1_PREFIX="r2:jass-data/runs/cpx62-0872-l3-imbalance2-d1-rc4/20260720T202210Z-fa68634c"
export EXPECTED_D1_JOB_ID="cpx62-0872-l3-imbalance2-d1-rc4"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 D1X_AUTOPSY_GO=1
export JASS_BUILD_JOBS=8

bash jobs/templates/l3-imbalance2-d1x-autopsy-v1.sh
python3 - "$JASS_ARTEFACT_DIR/d1x-rc4-autopsy.json" "$JASS_ARTEFACT_DIR" <<'PY'
import json,re,sys
from pathlib import Path
src=Path(sys.argv[1]); out=Path(sys.argv[2]); p=json.loads(src.read_text())
def safe(v): return re.sub(r'[^A-Za-z0-9_.-]+','_',str(v)).strip('_')
markers={
 'VERDICT': p['decision'],
 'CLASSIFICATION': p['classification'],
 'RECOMMENDATION': p['recommendation_for_human_review'],
 'SEARCH_PILOT': p['candidate_search_pilot_constraints']['working_name'],
}
for key,value in markers.items():
 path=out/f"{key}__{safe(value)}"
 path.write_text(f"{key.lower()}={value}\n")
summary={
 'decision':p['decision'],
 'classification':p['classification'],
 'recommendation':p['recommendation_for_human_review'],
 'candidate_search_pilot':p['candidate_search_pilot_constraints']['working_name'],
 'search_pilot_authorized':p['search_pilot_authorized'],
 'training_authorized':p['training_authorized'],
 'promotion_authorized':p['promotion_authorized'],
 'automatic_next_job':p['automatic_next_job'],
}
(out/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
PY
