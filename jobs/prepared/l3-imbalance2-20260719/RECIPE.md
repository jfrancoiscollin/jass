# L3-IMBALANCE2 — recette préparée

La campagne couvre les départs `n v n+2`, `n=1..18`, avec pions simples et
couleurs avantagées équilibrées.

- `1v3` et `2v4` : professeur WDL EGDB exact, corpus statique frais ;
- `3v5` à `18v20` : rollouts autonomes selon la recette P1 de #358 ;
- objectif du camp avantagé : victoire/nulle/défaite pondérées `1/2/4` par
  rééchantillonnage déterministe du train set, holdout intact ;
- P1/P2/P3/P4 : d8/d10/d12/d14, quatre générations par palier ;
- aucun enchaînement automatique.

Gen2-MMTO et Scan ne sont consultés qu’après un plateau interne confirmé sur
quatre générations et deux pools dédiés. Gen2 est la référence basse, Scan la
référence haute. Un plateau sous Scan produit `PLATEAU_BELOW_SCAN_REDESIGN`, pas
une continuation aveugle.
