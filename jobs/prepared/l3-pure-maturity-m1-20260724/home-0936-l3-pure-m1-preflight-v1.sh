#!/usr/bin/env bash
# id: home-0936-l3-pure-m1-preflight-v1
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged SHA}"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export PARENT_PREFIX="r2:jass-data/runs/ccx33-0790-l3-pure-c0-a-v1/20260718T104245Z-8fc4eacb"
export EXPECTED_PARENT_JOB="ccx33-0790-l3-pure-c0-a-v1"
exec timeout -k 60s 7200s bash jobs/templates/l3-pure-m1-preflight-v1.sh
