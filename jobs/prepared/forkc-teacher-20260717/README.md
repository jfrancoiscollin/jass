# Jobs préparés — fork C + teacher causal

Ces scripts sont volontairement hors de `jobs/queue/` et du control-plane
`queue/pending/` : aucun runner ne peut les réclamer. Ils sont prêts à être
copiés dans `jass-control/queue/pending/` après revue.

Ordre et conditions :

1. `cpx62-0774-forkc-c0-v1.sh` — diagnostic court : policy strong/weak,
   refit du même corpus T1 depuis weak, gate absolu et conversion p3/p4.
2. ~~`cpx62-0775-forkc-t1-v1.sh`~~ — **ANNULÉ (2026-07-17).** Le C0 `cpx62-0774`
   a rendu `scientific_status=stop_regression` (refit-faible vs fort elo −32.5,
   ci_high 0.493 < 0.5 ; hard-conv delta −0.011). Fork (c) au départ 0.3× est
   clos → le tour T1-C ne sera pas lancé. Script retiré du jeu préparé.
   Détail : `docs/forkc_c0_verdict_20260717.md`.
3. `ccx33-0776-teacher-mine-t3-v1.sh` — indépendant du fork C : reconstruit les
   trajectoires T3 historiques par transitions légales, certifie les siblings
   et produit les corpus B1/B2/B3 appariés.
4. `ccx33-0777-teacher-smoke-v1.sh` — seulement si 0776 a au moins 50 parents
   teacher. Renseigner `TEACHER_CORPUS_RUN_PREFIX` avec l'URI du résultat 0776,
   puis lancer le smoke A/B1/B2/B3.

Les seuils sont pré-engagés dans les runners : divergence politique `>=5 %`,
gain conversion dure p3/p4 `>=+0,02`, non-régression absolue ; smoke teacher
`>=+0,02` sur p3/p4 avec tolérance de simplicité `0,005`.
