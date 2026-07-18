#!/usr/bin/env bash
# id: ccx33-l3-pure-c0-a-v1
# description: L3-PURE C0 arm A, three generations of pure terminal-WDL self-play
# expected_duration: 14-18 h at the 0665 anchor (~230 kept positions/min/shard)
set -Eeuo pipefail
export ARM=A
export FRONTIER_FRAC=0
export NGEN=3 FRESH=500000 NSHARDS=8 PAR_GEN=8
export BASE_SEED=314159
export SHARD_TIMEOUT=21600
export JASS_BUILD_JOBS=8
exec bash jobs/templates/l3-pure-c0-runner-v3.sh
