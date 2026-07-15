#!/usr/bin/env bash
# id: cpx62-0728-t1bis-adj-g1-v2
# Instanciation T1-bis v2 (PR #330, spec codex_review_v3_2) — valeurs pré-engagées JFC 2026-07-15 :
#   GYM_MIN_POS=150 (garde-plancher ; gymnase ~0.04% cf 0715/D1-iii, non-levier cf 0726)
#   MIN_PROTECTED_TIP_RATE=0.0 + pas de sidecar (aucun certificat TB/CERT aligné par-record n'existe encore)
#   ALLOW_MTC_SKIP=1 (MTC pas câblé dans le pipeline courant ; egdb=JASS_EGDB_PATH utilisé)
# parent = référence fixe = T0/bootstrap (B4 build-matched, header = gen2). Le runner v2 fail-closed s'arrête
# plutôt que d'inventer un PASS (source-gen blob-vérifié, tags≠certs, gates stricts, promotion n=0→stop_technical).
export JOB_ID=cpx62-0728-t1bis-adj-g1-v2
export TOUR=T1-bis
export PARENT_PJTW_GZ=jobs/results/cpx62-0707-b4-bootstrap-gate/artefacts/bootstrap-build-matched.pjtw.gz
export FIXED_PJTW_GZ=jobs/results/cpx62-0707-b4-bootstrap-gate/artefacts/bootstrap-build-matched.pjtw.gz
export GYM_MIN_POS=150
export MIN_PROTECTED_TIP_RATE=0.0
export ALLOW_MTC_SKIP=1
exec bash jobs/templates/t1bis-adj-g1-v2-launch.sh
