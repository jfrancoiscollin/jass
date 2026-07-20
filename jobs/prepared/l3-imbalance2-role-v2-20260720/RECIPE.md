# Prepared jobs — L3-IMBALANCE2 role-aware V2 — ccx33 + cpx62 analysis

Cible d’entraînement scientifique de cette variante : **ccx33, 8 vCPU, 16 GiB RAM**. La comparaison P1 V1/V2 et la référence de difficulté sont préparées pour **cpx62**.

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
- suivi de `min_mem_available_mb` dans les artefacts ;
- pools plateau indépendants `A64/B64` ;
- `PLATEAU_PER_STRATUM=64` ;
- seed entraînement `271828`, seed plateau séparée `161803` ;
- 1 152 positions et un SHA-256 publié pour chaque pool.

Le runner spécialiste ne place pas actuellement chaque processus sous une commande `timeout`; les wrappers d’entraînement ne déclarent donc pas une protection inexistante.

## Campagne P1 préenregistrée

La campagne combine sans les confondre :

1. le re-assess V1 des modèles historiques G1–G4 de `ccx33-0847` ;
2. une nouvelle P1 role-aware V2 G1–G4 sur ccx33 ;
3. un verdict apparié sur les mêmes pools A64/B64 ;
4. une référence de difficulté W/D/L propre à chacune des dix-huit strates.

Le job cpx62 de comparaison joue les huit modèles à d10, Q00, cap 400 plies :

```text
8 × 2 × 1 152 = 18 432 parties candidate-only
```

Le verdict causal ne consulte ni Gen2-MMTO ni Scan. Il produit deux rapports de plateau, un rapport V1−V2 apparié par strate, les rapports bruts et une recommandation de revue. La mesure principale est la macro-moyenne par strate avec bootstrap stratifié ; le global brut reste secondaire.

## Référence de difficulté par quantité de matériel

Le wrapper :

```text
cpx62-l3-imbalance2-a64-b64-difficulty-reference.sh
```

utilise exactement les mêmes pools A64/B64 et publie :

- W/D/L **exact EGDB** pour `1v3` et `2v4`, soit 4 et 6 pièces au total ;
- W/D/L **Scan d10 empirique** pour `3v5` à `18v20`, soit 8 à 38 pièces ;
- résultats par strate et par pool ;
- coût `2L+D` de référence ;
- preuves de résolution EGDB à 100 % ;
- `scan_reference_is_exact=false`.

Scan n’est jamais une donnée de train ou de pondération. Cette référence sert seulement à interpréter la difficulté intrinsèque : un `6v8` ne reçoit pas la même courbe attendue qu’un `18v20`. Le protocole détaillé se trouve dans `docs/L3_IMBALANCE2_DIFFICULTY_REFERENCE.md`.

## Ordre obligatoire

1. Exécuter `ccx33-l3-imbalance2-role-v2-probe.sh` : une génération P1 réduite à 54 000 records, strictement non promotable.
2. Vérifier la mémoire minimale disponible, le débit, l’absence d’OOM ou de processus bloqué, la voie EGDB, les rapports V2 et les SHA A64/B64.
3. Lancer `ccx33-l3-imbalance2-role-v2-p1.sh` uniquement après go explicite.
4. Attendre la publication immuable de la nouvelle P1 V2.
5. Lancer `cpx62-l3-imbalance2-a64-b64-difficulty-reference.sh` pour figer les références exactes/Scan par strate.
6. Renseigner les préfixes et identifiants exacts de `0847` et de la V2, puis lancer `cpx62-l3-imbalance2-p1-v1-v2-a64-compare.sh`.
7. Joindre le profil de référence au comparateur pour la lecture absolue ; sa règle de lead reste candidate-only.
8. Revoir `campaign-decision.json`; P2 reste interdit tant qu’une décision humaine n’est pas enregistrée.
9. P2, P3 et P4 exigent ensuite l’URI et le SHA-256 immuables du parent précédent.
10. Le gate final reste interdit avant plateau interne approuvé.

La L3 initiale équilibrée utilise un runner et des wrappers séparés dans `jobs/prepared/l3-pure-role-v2-20260720/`. Les deux lignées partagent seulement l’outil de calcul des poids, jamais leurs manifests ni leurs décisions de promotion.

Aucun wrapper ne chaîne automatiquement le suivant et aucun job scientifique n’est lancé par la PR.
