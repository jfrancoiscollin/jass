# L3-PURE — source historique UNIFORM 40M pour hard replay

Date : 2026-07-29  
Statut : préenregistré ; aucun résultat scientifique à ce stade

## Objectif

Produire une source post-correctif assez grande pour retenter la dose
préenregistrée d'un million de records `failed_conversion`, sans diminuer cette
dose après l'observation de `home-1042`.

`home-1042` a obtenu 58 908 records hard depuis 2 000 000 records historiques,
soit un rendement final de 2,9454 %. L'extrapolation ponctuelle demande
33,95 M records pour atteindre un million. La nouvelle source est fixée à
**40 000 000 records**, soit 17,8 % de marge sur cette extrapolation.

Cette marge protège contre la fluctuation du rendement. Elle ne garantit pas
la capacité : seul le préflight de mining ultérieur pourra publier
`L3_PURE_HARD_REPLAY_CATALOGUE_READY`.

## Contrat de génération

La source reproduit le bras UNIFORM admissible de `home-1017` :

- parent `TURNOVER`, modèle SHA256
  `b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16` ;
- moteur post-correctif de racine nulle ;
- Q00, jeu d8, label d4 WDL-only ;
- `random-open-plies=8`, `explore-eps=8`, `explore-decay-plies=60` ;
- exploration uniforme, aucun TOPK ;
- RNG self-play séparés, ouvertures appariées, `drop-plycap` ;
- six producteurs HOME au maximum ;
- nouvelles graines `31415926..31415931`, disjointes de `home-1017` ;
- split déterministe par `opening_id`, graine 577215, holdout 10 %.

Il s'agit d'une production de données, pas d'un bras d'entraînement. Aucun
oracle, teacher, ré-étiquetage, corpus pré-correctif ou mélange de calibration
de nulles n'est admis.

## Budget HOME

Le débit préenregistré est 9 804 records/minute/producteur à d8. Pour
6 666 667 records au plus par producteur :

- durée saine estimée : environ 680 minutes, soit 11 h 20 ;
- timeout par producteur : 72 000 secondes, soit 20 heures ;
- concurrence maximale : six producteurs ;
- garde disque initiale : 20 GiB libres.

Les phases `merge` et `split` utilisent désormais des parcours bornés en
mémoire. `mine-hard` ne conserve qu'un candidat par partie avant la
déduplication canonique.

## Sorties attendues

- `uniform.jnnw.gz` et `uniform.jsm.gz` ;
- `uniform-split.json` ;
- canari WDL, manifeste de merge et compteurs d'exploration ;
- codes de sortie des six producteurs ;
- hashes SHA256 compressés et bruts ;
- certificat `L3_PURE_HARD_REPLAY_LARGE_SOURCE_READY`.

Le certificat fixe :

```json
{
  "scientific_value": "authenticated historical source only",
  "external_teacher_inputs": 0,
  "promotion": false,
  "automatic_next_job": null
}
```

## Séquencement

1. produire et authentifier les 40 M records ;
2. seulement après succès, lancer un nouveau préflight `mine-hard` à dose
   inchangée de 1 M ;
3. n'autoriser le fit A/B que si ce préflight publie exactement
   `L3_PURE_HARD_REPLAY_CATALOGUE_READY` et
   `training_authorized=true`.

La source ne déclenche automatiquement ni le préflight, ni le fit.
