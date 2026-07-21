# L3-IMBALANCE2 W1 — screen de pondération adaptative par strate

## Question causale

À corpus, split, warm-start, architecture, labels, recherche Q00 et optimiseur
identiques, remplacer la matrice fixe role-aware V2 `1/2/4` par les poids absolus
shrinkés de W0 améliore-t-il la conversion du camp initialement à `+2` ?

## Sources immuables

- corpus G4 et warm-start G3 : `ccx33-0852-l3-imbalance2-role-v2-p1` ;
- politique W0 : `cpx62-0877-l3-imbalance2-w0-oracle-calibration` ;
- classification exigée :
  `STRATUM_ORACLE_WEIGHTING_SUPPORTED_DENSITY_ONLY_NOT_SUPPORTED` ;
- stabilité A/B exigée ; hypothèse de densité seule exigée fausse.

## Bras

- contrôle : rôle courant, poids `expected/draw/upset = 1/2/4` ;
- adaptatif : pour chaque strate `s`, `1 / (1+alpha_s) / (1+3 alpha_s)`, avec
  `alpha_s` shrinké par W0 ;
- hors domaine exact `|Δ hommes|=2`, dames égales : poids ancre `1` ;
- même seed de rééchantillonnage `271832` et même nombre de lignes ;
- holdout final strictement byte-identique ;
- les cibles WDL terminales ne sont jamais modifiées.

L’oracle influence donc le crédit d’apprentissage, pas les labels. Cette variante
est teacher-calibrée et interdite dans `L3-PURE`.

## Évaluation indépendante

- nouveaux pools E64/F64, seed `141421` ;
- 18 strates × 64 positions × 2 pools = 2 304 positions appariées par bras ;
- profondeur 10, max 400 plies, recherche Q00 identique ;
- coût principal `2L+D`, macro-moyenne égale par strate ;
- bootstrap apparié et stratifié, 10 000 réplications ;
- garde généraliste de 64 paires color-swapped à d8.

## Gate du screen

Un passage exige simultanément :

- delta adaptatif−contrôle ≤ `−0,020` ;
- borne haute IC95 stratifiée ≤ `0` ;
- aucun pool E ou F dégradé ;
- au moins 12/18 strates non dégradées ;
- pire régression locale ≤ `0,10` ;
- garde généraliste passée.

## Portée du résultat

Un succès ne confirme pas définitivement la politique, car W0 a été calibré sur
A64/B64. Il autorise seulement une revue humaine pour concevoir une confirmation
avec calibration oracle fraîche C512 et cross-fit, puis nouveaux pools de test.

```text
training_continuation_authorized=false
promotion_authorized=false
automatic_next_job=null
```
