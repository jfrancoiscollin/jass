#!/usr/bin/env bash
# id: ccx33-l3-pure-q00-role-v2
# description: ccx33 treatment paired with Q00 control; exact ±2 role-aware resampling
# expected_duration: use control calibration; explicit go required
set -Eeuo pipefail
export ARM=A FRONTIER_FRAC=0 L3_VARIANT=Q00_CAPTURE
export L3_SEARCH_OVERRIDES="qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,qs_forcing_depth=0,qs_promo_depth=0"
export NGEN=2 FRESH=150000 NSHARDS=8 PAR_GEN=8
export BASE_SEED=271828 SHARD_TIMEOUT=21600 JASS_BUILD_JOBS=8
export L3_ROLE_V2_BOX=ccx33 L3_ROLE_V2_RUN_KIND=primary
exec bash jobs/templates/l3-pure-role-v2-runner-v1.sh
