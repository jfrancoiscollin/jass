#!/usr/bin/env bash
# Immutable identity-only exclusions for runtime v2. The v1 corpus is terminal
# scientific history and is fetched from its failed (scientific-gate) attempt.

source jobs/templates/t3-f6-runtime-exclusions-v1.sh

T3_F6_R0_V1_PREFIX="r2:jass-data/runs/cpx62-1644-l3-t3-f6-runtime-r0-v1/20260829T112915Z-362d1a09"
T3_F6_R0_V1_REMOTE="artefacts/r0-corpus.fen"
T3_F6_R0_V1_EXPECTED_STATE="failed"
