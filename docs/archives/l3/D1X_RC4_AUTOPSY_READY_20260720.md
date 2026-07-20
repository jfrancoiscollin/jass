# D1-X RC4 — autopsie terminée

> Verdict immuable du 20 juillet 2026.  
> Job : `cpx62-0874-l3-imbalance2-d1x-autopsy`  
> Code : `a7301ac6b80b10d6881132d293d951cd113f3d6a`

## Résultat

```text
D1X_RC4_AUTOPSY_READY
classification=RC4_ACTIVE_BUT_NONCAUSAL_FOR_CONVERSION
recommendation_for_human_review=DESIGN_ONE_SEPARATE_SEARCH_ONLY_PILOT
candidate=S1_ROLE_STABILITY_EXTENSION
```

RC4 n’a pas échoué parce que ses quatre canaux seraient absents ou totalement ignorés. Ils sont actifs et ont été appris, mais ils n’ont pas produit d’amélioration causale de la conversion dans le protocole D1-A.

Cette lecture est cohérente avec le verdict D1-A déjà figé :

- delta macro RC4−contrôle : `+0,003038` ;
- IC95 stratifié : `[−0,043403 ; +0,049913]` ;
- strates non dégradées : `9/18` ;
- sentinelles ciblées corrigées : `0/7` ;
- nouvelles divergences : `0` ;
- débit RC4/contrôle : `0,935302` ;
- garde généraliste : `0,4140625`, échouée.

## Portée scientifique

Le résultat ferme RC4 à protocole identique. Il ne justifie ni davantage de volume sur les mêmes features, ni un refit supplémentaire, ni une intégration dans `L3-PURE`.

Le concept `S1_ROLE_STABILITY_EXTENSION` est seulement une piste de revue pour un éventuel pilote search-only séparé, hors quiescence et borné au domaine spécialiste. Il devra disposer de nouveaux pools, d’une comparaison fixe-nœuds et movetime, d’une garde généraliste et d’une garde de débit.

`L3-IMBALANCE2` reste un laboratoire spécialiste. Aucun résultat de ce track ne constitue un remplacement généraliste de `L3-PURE` ou de `gen2-mmto`.

## Gardes finales

```text
search_pilot_authorized=false
training_authorized=false
promotion_authorized=false
automatic_next_job=null
```

## Exécution et artefacts

- début : `2026-07-20T22:09:26Z` ;
- fin : `2026-07-20T22:14:24Z` ;
- exit code : `0` ;
- résultat R2 :

```text
r2:jass-data/runs/cpx62-0874-l3-imbalance2-d1x-autopsy/20260720T220921Z-a7301ac6
```

Artefacts principaux :

- `d1x-rc4-autopsy.json` ;
- `JASS_CONTROL_SUMMARY.json` ;
- `RESULTS.txt` ;
- `rc4-source-transform-replayed.json` ;
- contrats de sources vérifiées ;
- logs ;
- marqueurs GitOps de verdict, classification, recommandation et candidat.
