# Manifeste de nettoyage des branches — 17 juillet 2026

Ce manifeste a été produit avant toute suppression distante, sur `develop=709fa072b292436a091329d0a38a2bcc677636b6`.

## Inventaire de référence réactualisé

- 339 PR : 330 mergées, 7 fermées sans merge, 2 ouvertes ;
- 151 branches distantes, dont `develop` ;
- 150 branches hors `develop` ;
- 123 branches dont le tip correspond exactement au `head.sha` d'au moins une PR mergée ;
- 21 autres suppressions explicitement auditées : 9 tips post-PR dépassés, 4 PR fermées remplacées, 7 branches sans PR obsolètes et la branche de la PR #339 après fermeture ;
- 7 branches distantes initiales conservées, auxquelles s'ajoute la branche de cette PR d'archivage.

L'inventaire exhaustif, avec tip SHA, PR associée, état, disposition et raison, est conservé dans [`branch_cleanup_20260717.tsv`](branch_cleanup_20260717.tsv).

## Branches conservées

- `develop` — branche par défaut ;
- `agent/archive-pre-branch-cleanup-20260717` — présente PR d'archivage ;
- `agent/t3-adj-g1-launch` — source de la PR #338, conservée jusqu'au merge de l'archive ;
- `claude/0121-pattern-jass-variant-C-kings` — source unique archivée ici ;
- `claude/docs-perf-journey` — source unique archivée ici ;
- `claude/nnue-eval-server` — source unique archivée ici ;
- `migration/clean-develop-20260717T140558Z` — rollback de réécriture ;
- `migration/clean-main-20260717T140558Z` — rollback de réécriture.

Les quatre branches sources peuvent être retirées seulement après merge de la PR d'archivage. Les deux branches `migration/clean-*` restent jusqu'à validation définitive du rollback R2.

## Garde-fous

- aucun force-push et aucun `git push --mirror` ;
- aucune écriture R2, jass-control, runner, science ou job ;
- vérification du SHA distant immédiatement avant chaque lot de suppression ;
- conservation de toute branche nouvelle ou dont le tip diverge de l'inventaire ;
- suppression de `develop` interdite.
