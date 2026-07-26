#!/usr/bin/env bash
# id: home-0982-l3-pure-replay25-train-v1
# Draft until the exact completed home-0981 and home-0980 prefixes are pinned.
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged SHA}"
: "${PREFLIGHT_PREFIX:?set completed home-0981 result prefix}"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="home-0982-l3-pure-replay25-train-v1"
export EXPECTED_PREFLIGHT_JOB="home-0981-l3-pure-replay25-preflight-v1"
export TURNOVER_CONFIRM_PREFIX="r2:jass-data/runs/home-0980-l3-pure-turnover-confirmation-v2/20260726T085020Z-aef92679"
export EXPECTED_TURNOVER_CONFIRM_JOB="home-0980-l3-pure-turnover-confirmation-v2"
export M1_PREFIX="r2:jass-data/runs/home-0944-l3-pure-m1-train-resume-v3/20260724T052619Z-faddc80a"
export EXPECTED_M1_JOB="home-0944-l3-pure-m1-train-resume-v3"
export CHAMPION_PREFIX="r2:jass-data/runs/home-0965-l3-pure-f2m-gen2-repaired-benchmark-v1/20260725T154956Z-0c1e04a9"
export EXPECTED_CHAMPION_JOB="home-0965-l3-pure-f2m-gen2-repaired-benchmark-v1"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 14400s \
  bash jobs/templates/l3-pure-replay25-train-v1.sh
