# L3-IMBALANCE2 — D0 causal diagnostic

Ce bloc intervient après le verdict définitif `STOP_BEFORE_P3_REDESIGN`. Il ne
prolonge pas la lignée et ne produit aucun modèle.

## Question scientifique

Pourquoi G8 n'améliore-t-il pas la conversion par rapport à G4 ? Le diagnostic
sépare quatre hypothèses de travail :

1. horizon ou mécanisme de recherche ;
2. représentation ou objectif d'évaluation insuffisant ;
3. crédit, cible ou distribution d'entraînement ;
4. mélange non séparable nécessitant plusieurs pilotes distincts.

Ces catégories sont des **hypothèses**, jamais une preuve causale automatique.

## Sources immuables

- P1 role-aware V2 `ccx33-0852`, modèle G4 et pools A64/B64 ;
- rapports bruts P1 `ccx33-0853` ;
- P2 role-aware V2 `ccx33-0859`, modèle G8 ;
- rapports bruts P2 `ccx33-0864` ;
- référence matérielle `cpx62-0862`, EGDB exacte pour `1v3/2v4` et Scan d10
  empirique pour `3v5…18v20`.

L'unique timeout connu `plateau-a:1100` est retiré de G4–G8 avec la même politique
symétrique fail-closed que `0870` : maximum deux positions et 0,1 % du corpus.

## Sélection des sentinelles

Le job choisit 30 positions uniques :

- 10 régressions G4→G8 ;
- 10 déficits persistants à la référence EGDB/Scan ;
- 10 cas issus des strates ayant la plus forte divergence A/B.

Les chevauchements sont supprimés et complétés par les cas difficiles suivants.
Chaque entrée conserve le FEN, pool/index, strate, camp avantagé, résultats G4/G8,
référence et métriques de sélection.

## Replays statiques

Pour chaque sentinelle :

- G4 8cf aux profondeurs 8, 10, 12 et 14 ;
- G8 8cf aux mêmes profondeurs ;
- Scan, livre désactivé et `bb-size=0`, aux mêmes profondeurs ;
- coup choisi, score, profondeur annoncée, nœuds, PV et trace HUB brute lorsque
  le moteur expose ces champs.

Total prévu : `30 × 3 × 4 = 360` recherches statiques. Il ne s'agit pas de parties
de self-play.

## Exécution

Choisir **un seul** wrapper selon la première box libre :

```text
ccx33-l3-imbalance2-d0-diagnostic.sh
cpx62-l3-imbalance2-d0-diagnostic.sh
```

Avant mise en file, fournir :

```text
EXPECTED_CODE_SHA=<SHA mergé et revu>
SCAN_BIN=<binaire Scan revu>
```

Les deux wrappers partagent exactement les mêmes sources, sentinelles, profondeurs,
shards et paramètres scientifiques. Leurs sorties ne doivent pas être combinées
comme des observations indépendantes.

## Sorties

- `d0-sentinels.json` ;
- `d0-replay-traces.tar.gz` ;
- `d0-causal-report.json` ;
- `symmetric-exclusions.json` ;
- `source-contract.json` ;
- `c0-decision.json`.

Le rapport peut recommander un type de pilote D1, mais impose toujours :

```text
d1_authorized=false
training_authorized=false
promotion_authorized=false
automatic_next_job=null
```

Une revue humaine doit sélectionner un seul changement causal avant toute nouvelle
campagne : recherche, représentation, ou cible/distribution. P3 reste interdit.
