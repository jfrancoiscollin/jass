#!/usr/bin/env bash
# id: cpx62-l3-pure-c0-p1-meta-blend-v1
# description: convex C0/P1 blend family screen and independent confirmation against both parents
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set merged jass SHA in jass-control}"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1
export SCREEN_NOPEN=128 CONFIRM_NOPEN=256 SCREEN_DEPTH=8 CONFIRM_DEPTH=9 MOVETIME=0.3
export PAR_GATE=12 GAME_TIMEOUT=100 JASS_BUILD_JOBS=4
exec bash jobs/templates/l3-pure-c0-p1-meta-blend-v1.sh
