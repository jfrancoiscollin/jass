#!/usr/bin/env bash
# Prepared only: not queued. The treatment replaces half of the random-8
# openings by a stochastic pool derived from the authenticated historical
# master corpus. Master labels and played moves are never training targets.
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?pin reviewed merged SHA}"
: "${EXPECTED_JOB_ID:?allocate a unique HOME job id}"
: "${PREREQUISITE_PREFIX:?pin completed home-1017 result prefix}"
: "${TOPK_READOUT_PREFIX:?pin completed 1017 independent readout prefix}"
: "${EXPECTED_TOPK_READOUT_JOB:?pin its exact job id}"
: "${REPLAY_SOURCE_DATA_GZ_SHA:?pin home-1017 uniform.jnnw.gz SHA256}"
: "${REPLAY_SOURCE_META_GZ_SHA:?pin home-1017 uniform.jsm.gz SHA256}"
: "${FULL_RUN_APPROVED:?explicit launch approval required}"
: "${SCIENTIFIC_GO:?explicit scientific approval required}"
export COVERAGE_LEVER=opening_pool
export EXPECTED_PREREQUISITE_JOB=home-1017-l3-pure-topk-causal-ab-v2
export PARENT_TRAIN_PREFIX="r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984"
export EXPECTED_PARENT_TRAIN_JOB=home-0977-l3-pure-turnover1to1-train-v1
export PARENT_ARTEFACT=turnover1to1.pjtw.gz
export PARENT_MODEL_SHA=b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16
export PARENT_NAME=TURNOVER
export NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 28800s \
  bash jobs/templates/l3-pure-coverage-lever-ab-v1.sh
