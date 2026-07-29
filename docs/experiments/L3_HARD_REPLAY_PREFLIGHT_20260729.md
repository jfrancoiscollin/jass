# L3-PURE — préflight hard-replay UNIFORM

Date : 2026-07-29
Job : `home-1042-l3-pure-hard-replay-preflight-uniform-v1`
Verdict : `L3_PURE_HARD_REPLAY_CATALOGUE_INSUFFICIENT`

## Question bornée

Après le rejet de TOPK3 par `home-1040`, TURNOVER reste champion. Le protocole
hard-replay utilise donc comme source historique le bras UNIFORM de `home-1017`
et demande exactement 1 000 000 de records `failed_conversion`, sélectionnés
uniquement dans le train historique, avec :

- une position au plus par partie ;
- déduplication canonique ;
- miroir couleur ;
- split par `opening_id` reproduit bit à bit ;
- mining exécuté deux fois et bit-identique ;
- aucune réduction post-hoc de la dose.

Le job est data-only : aucun self-play, fit, match ou bake.

## Entrées authentifiées

Source :

`r2:jass-data/runs/home-1017-l3-pure-topk-causal-ab-v2/20260728T123640Z-9e404854`

Certificat :

`r2:jass-data/runs/home-1021-preflight-1017-fit-resume-v1/20260728T162800Z-9e404854`

Le run source est `failed` parce que ses fits n'ont pas terminé, mais son
corpus UNIFORM de 2 000 000 records et son split sont complets et authentifiés
par `home-1021`.

## Capacité observée

| Étape | Cardinalité |
|---|---:|
| records portant `failed_conversion` | 325 233 |
| parties après `one-per-game` | 30 205 |
| positions après déduplication canonique | 29 454 |
| records après miroir couleur | **58 908** |
| dose préenregistrée requise | **1 000 000** |

Les 58 908 records couvrent 29 454 parties uniques et 21 408 ouvertures
uniques. Le mining A/B est bit-déterministe ; l'échec est une insuffisance de
capacité, pas une panne.

Au rendement final observé (`58 908 / 2 000 000 = 2,9454 %`), atteindre un
million demanderait environ 33,95 M records historiques comparables. Cette
extrapolation sert seulement à dimensionner une éventuelle nouvelle source ;
elle ne prouve pas que le rendement resterait constant.

## Décision

`training_authorized=false`. Le fit causal de 2 M par bras n'est pas lancé et
la dose n'est pas abaissée à 58 908 après observation. La réouverture exige un
nouveau préenregistrement qui choisit explicitement l'une de ces voies :

1. produire/authentifier une source post-correctif beaucoup plus large ;
2. définir prospectivement un DOE de dose hard, avec plusieurs doses et un
   contrôle uniforme de même taille, plutôt que de rebaptiser le préflight
   échoué.

Aucun corpus pré-correctif ou mélange de calibrations de nulles ne peut être
ajouté silencieusement pour remplir le quota.

Résultat autoritatif :

`r2:jass-data/runs/home-1042-l3-pure-hard-replay-preflight-uniform-v1/20260729T053149Z-9ba51abe`

```json
{
  "training_authorized": false,
  "promotion_authorized": false,
  "automatic_next_job": null
}
```
