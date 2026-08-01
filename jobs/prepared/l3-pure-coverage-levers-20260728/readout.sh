#!/usr/bin/env bash
# Prepared only: reusable after exactly one valid coverage-lever training A/B.
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?must equal the training code SHA}"
: "${EXPECTED_JOB_ID:?allocate a unique HOME readout job id}"
: "${TRAIN_PREFIX:?pin completed coverage-lever A/B result prefix}"
: "${EXPECTED_TRAIN_JOB:?pin its exact job id}"
: "${EXPECTED_COVERAGE_LEVER:?phase_sampling, topk_softmax, regret_restart, opening_pool or replay_ratio}"
: "${FULL_RUN_APPROVED:?explicit launch approval required}"
: "${SCIENTIFIC_GO:?explicit scientific approval required}"
export NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 28800s \
  bash jobs/templates/l3-pure-coverage-lever-readout-v1.sh
