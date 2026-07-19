# Prepared jobs — L3-IMBALANCE2 role-aware V2

Ces wrappers reproduisent la lignée V1 en ne modifiant que le rééchantillonnage :

- domaine courant exact : `|Δ hommes| = 2` et nombre de dames égal ;
- camp au trait à `+2` : victoire/nulle/défaite = `1/2/4` ;
- camp au trait à `-2` : victoire/nulle/défaite = `4/2/1` ;
- hors domaine : poids `1` ;
- holdout final intact ;
- aucun relabel profond de criticité.

Ordre : P1, puis P2/P3/P4 uniquement avec URI et SHA-256 immuables du parent. Le gate final reste soumis à un plateau interne approuvé. Aucun wrapper ne chaîne automatiquement le suivant.
