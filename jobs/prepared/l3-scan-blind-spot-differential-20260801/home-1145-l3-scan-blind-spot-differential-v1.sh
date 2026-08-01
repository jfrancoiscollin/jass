#!/usr/bin/env bash
# id: home-1145-l3-scan-blind-spot-differential-v1
# Readout only. Fill the two immutable result prefixes after 1143/1144 finish.
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set the reviewed develop SHA}"
: "${EXACT_ATLAS_PREFIX:?set completed home-1143 result prefix}"
: "${GEN2_ATLAS_PREFIX:?set completed home-1144 result prefix}"
export EXPECTED_JOB_ID="home-1145-l3-scan-blind-spot-differential-v1"
export EXPECTED_EXACT_ATLAS_JOB="home-1143-l3-scan-blind-spot-atlas-exact-v1"
export EXPECTED_GEN2_ATLAS_JOB="home-1144-l3-scan-blind-spot-atlas-gen2-v1"
export READOUT_APPROVED=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 30s 600s \
  bash jobs/templates/l3-scan-blind-spot-differential-v1.sh
