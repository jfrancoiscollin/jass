#!/usr/bin/env bash
# R1-v4 Pool2: exactly one unchanged replication after positive Pool1.
export T3_F6_RUNTIME_CAMPAIGN=v4
export T3_F6_POOL2_GEN_SEED=2026092701
export T3_F6_POOL2_SELECT_SEED=2026092702
export T3_F6_POOL2_BOOTSTRAP_SEED=2026092703
export T3_F6_CHAINED_BOOTSTRAP_SEED=2026092801
source jobs/templates/l3-t3-f6-runtime-strength-pool2-v2.sh
