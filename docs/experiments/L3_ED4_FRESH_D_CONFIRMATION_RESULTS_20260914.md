# ED4-FRESH — résultat terminal du bloc D

Date : 2026-09-14. Ce document scelle le premier bloc confirmatoire de la tentative prospective `k=1` de la campagne `L3_EVAL_SEARCH_CANDIDATE_CAMPAIGN_V1_20260909.md`.

## Identité de l'exécution

- job : `cpx62-1970-l3-ed4-fresh-d-confirmation-production-v1`
- attempt : `20260914T163341Z-1dd1d078`
- code : `1dd1d07806d50e766baef151b3dab3c5fe48fc31`
- candidat : `ED4_CHOICE.pjtw`
- SHA256 candidat : `2e856652efdd1d2758a949a5d4a29557fa31f4a64d55505ae6dc41482b641f5b`
- source D scellée : `cpx62-1937-l3-ed4-fresh-d-source-production-v1` / `20260913T073800Z-9673030c`
- teacher : Scan, budget `200000` nœuds par appel
- parents décision : `512`, exactement `64` dans chacune des huit cellules phase × STM
- alpha campagne `k=1` : `0.025`
- alpha bloc D : `0.025/3 = 0.008333333333333333`
- bootstrap : parent, stratifié phase × STM, `20000` réplications, contrat gelé avant cible.

Le rehearsal authentifié précédent est `cpx62-1969-l3-ed4-fresh-d-confirmation-rehearsal-v6`, attempt `20260914T161838Z-1dd1d078`, terminal `ED4_FRESH_D_CONFIRMATION_REHEARSAL_COMPLETE_V1`, avec zéro lecture de cible, zéro recherche Scan confirmatoire et alpha zéro.

## Résultat confirmatoire

Le bloc D termine avec :

- `block_verdict = ED4_FRESH_D_CONFIRMATION_NOT_SUPPORTED_V1`
- `scientific_verdict = CAMPAIGN_ATTEMPT_SCIENTIFIC_NOT_SUPPORTED_V1`
- `next_stage = STOP_ED4_K1_SCIENTIFIC_NOT_SUPPORTED`
- `confirmation_target_consumed = true`
- `alpha_spent = 0.008333333333333333`

Agrégats de regret moyen / top-hit :

| arm | regret moyen | top-hit |
| --- | ---: | ---: |
| BASE | 452.955078125 | 0.3046875 |
| CANDIDATE | 466.44140625 | 0.31640625 |
| HARD | 495.103515625 | 0.322265625 |
| SOFT | 475.58984375 | 0.318359375 |

Contraste candidat vs BASE, défini comme amélioration de regret `BASE - CANDIDATE` :

- moyenne : `-13.486328125`
- borne inférieure unilatérale : `-68.400390625`
- borne supérieure descriptive : `13.698697916666674`
- changements de décision : `136`
- améliorés : `62`
- dégradés : `57`
- inchangés : `393`
- delta top-hit : `+0.01171875`.

Contraste candidat vs HARD :

- moyenne : `+28.662109375`
- borne inférieure unilatérale : `-73.77223307291666`
- borne supérieure descriptive : `137.04931640625003`
- changements de décision : `163`
- améliorés : `67`
- dégradés : `81`
- inchangés : `364`
- delta top-hit : `-0.005859375`.

SOFT reste descriptif : gain moyen candidat vs SOFT `+9.1484375`, borne inférieure `-85.02101236979166`, delta top-hit `-0.001953125`.

## Gates gelés

- `regret_beats_base_positive_lower_bound` : **FAIL**
- `regret_beats_hard_positive_lower_bound` : **FAIL**
- `top_hit_not_lower_than_base_and_hard` : **FAIL**
- `harms_not_more_than_improvements_vs_base` : **PASS**

Le candidat a un regret moyen supérieur à BASE sur cette cohorte fraîche et aucune des deux bornes inférieures obligatoires n'est positive. Face à HARD, le point moyen est favorable mais l'intervalle ne permet pas d'établir le gain requis. Le top-hit progresse face à BASE mais baisse face à HARD. Ce résultat établit **l'absence de support confirmatoire requis** pour ED4 ; il ne démontre pas un effet exactement nul.

## Coût et consommation

- `target_reads = 4710`
- `new_scan_searches = 4707`
- nœuds Scan demandés : `941400000`
- workers : `8`
- mur teacher : `24.22965674000443 s`
- `fits = 0`, `new_jass_searches = 0`, `strength_games = 0`, `selfplay_games = 0`, `promotions = 0`, `bakes = 0`.

La cohorte D 1937 est consommée définitivement. Les sources W 1959 et S 1949 restent scellées mais **leurs cibles confirmatoires ED4 ne doivent pas être lues**, car le protocole arrête la tentative `k=1` au premier bloc scientifique obligatoire en échec.

## Disposition scientifique

La tentative ED4 `k=1` est close sur `CAMPAIGN_ATTEMPT_SCIENTIFIC_NOT_SUPPORTED_V1`. Aucun retuning, second bootstrap, nouvelle seed, extension de volume, réanalyse avec seuil assoupli, promotion, bake ou scale-up ED4 n'est autorisé.

Le contrat de campagne autorise une tentative adaptative `k=2` seulement après un nouveau préenregistrement à **un axe** et avec de nouvelles cohortes de confirmation. La tentative suivante est préenregistrée séparément dans `L3_ED5_Q200K_TEACHER_CHOICE_SET_PREREG_V1_20260914.md`.
