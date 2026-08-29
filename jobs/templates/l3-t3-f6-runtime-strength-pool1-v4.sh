#!/usr/bin/env bash
# R1-v4 Pool1: preregistered frozen T3-A/F6 native wall-clock primary.
export T3_F6_RUNTIME_CAMPAIGN=v4
export T3_F6_POOL1_GEN_SEED=2026092601
export T3_F6_POOL1_SELECT_SEED=2026092602
export T3_F6_POOL1_BOOTSTRAP_SEED=2026092603
source jobs/templates/l3-t3-f6-runtime-strength-pool1-v2.sh
