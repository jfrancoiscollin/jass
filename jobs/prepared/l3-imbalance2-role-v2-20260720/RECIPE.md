# Prepared jobs — L3-IMBALANCE2 role-aware V2 — ccx33

Cible d’exécution scientifique de cette variante : **ccx33, 8 vCPU, 16 GiB RAM**.

La recette scientifique V1 est inchangée ; seul le rééchantillonnage devient dépendant du rôle et du domaine courant :

- domaine exact : `|Δ hommes| = 2` et nombre de dames égal ;
- camp au trait à `+2` : victoire/nulle/défaite = `1/2/4` ;
- camp au trait à `-2` : victoire/nulle/défaite = `4/2/1` ;
- hors domaine : poids `1` ;
- holdout final intact ;
- aucun relabel profond de criticité.

## Contrat ccx33

- `PAR_GEN=8` ;
- `JASS_BUILD_JOBS=8` ;
- garde runner : au moins 14 GiB RAM et 20 GiB libres ;
- suivi de `min_mem_available_mb` dans les artefacts.

Le runner spécialiste ne place pas actuellement chaque processus sous une commande `timeout`; les wrappers ne déclarent donc pas une protection inexistante.

## Ordre obligatoire

1. Exécuter `ccx33-l3-imbalance2-role-v2-probe.sh` : une génération P1 réduite à 54 000 records, strictement non promotable.
2. Vérifier la mémoire minimale disponible, le débit, l’absence d’OOM ou de processus bloqué, la voie EGDB et les rapports V2.
3. Lancer P1 complet uniquement après go explicite.
4. P2, P3 et P4 exigent l’URI et le SHA-256 immuables du parent précédent.
5. Le gate final reste interdit avant plateau interne approuvé.

La L3 initiale équilibrée utilise un runner et des wrappers séparés dans `jobs/prepared/l3-pure-role-v2-20260720/`. Les deux lignées partagent seulement l’outil de calcul des poids, jamais leurs manifests ni leurs décisions de promotion.

Aucun wrapper ne chaîne automatiquement le suivant et aucun job scientifique n’est lancé par la PR.
