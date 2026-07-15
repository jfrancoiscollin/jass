#!/usr/bin/env bash
# Compatibility entry point for the T1-bis ADJ+G1 template.
#
# The original Phase-0 skeleton was used to instantiate 0727, but it did not
# contain the production integration required by codex_review_v3_2. Keep this
# stable path while routing every new instantiation to the fail-closed v2
# launcher. Historical queued jobs remain untouched.
set -euo pipefail
cd /root/jass
exec bash jobs/templates/t1bis-adj-g1-v2-launch.sh "$@"
