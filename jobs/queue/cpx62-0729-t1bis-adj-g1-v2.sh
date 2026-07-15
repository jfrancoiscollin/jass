#!/usr/bin/env bash
# id: cpx62-0729-t1bis-adj-g1-v2
# Relance strictement technique de 0728 après correction du pipeline openings
# (pas de SIGPIPE sous pipefail) et ajout d'un trap ERR ligne/commande.
# Paramètres scientifiques INCHANGÉS :
#   GYM_MIN_POS=150 ; no-sidecar ; MIN_PROTECTED_TIP_RATE=0.0 ; MTC-skip ; T0=bootstrap B4.
# Le runner reste fail-closed : aucun shard incomplet, gate n=0 ou métrique absente ne peut promouvoir.
export JOB_ID=cpx62-0729-t1bis-adj-g1-v2
export TOUR=T1-bis
export PARENT_PJTW_GZ=jobs/results/cpx62-0707-b4-bootstrap-gate/artefacts/bootstrap-build-matched.pjtw.gz
export FIXED_PJTW_GZ=jobs/results/cpx62-0707-b4-bootstrap-gate/artefacts/bootstrap-build-matched.pjtw.gz
export GYM_MIN_POS=150
export MIN_PROTECTED_TIP_RATE=0.0
export ALLOW_MTC_SKIP=1
exec bash jobs/templates/t1bis-adj-g1-v2-launch.sh
