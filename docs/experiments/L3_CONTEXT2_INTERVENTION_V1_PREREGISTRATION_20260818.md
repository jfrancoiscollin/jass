# CTX2-Intervention-v1 — préenregistrement

## Question

Le résultat neutre de `CURRENT_2M` aligned contre shuffled peut-il provenir
d'une distribution qui rend les 30 canaux CTX2 redondants, plutôt que d'une
absence d'information conditionnelle exploitable ?

L'audit fixe montre que `men_delta` porte 57,3462 % du logit absolu, que les
trois premiers signaux en portent 76,6677 %, et que le nombre effectif de
composantes n'est que 2,803. Le pilote apparié `home-1395` a en revanche établi
53 effets paramètre × composante au-delà du bruit de seed. `NODECAY` est exclu :
son contrôle WDL a échoué.

## Plan d'expérience

Le premier job ne génère rien. Il réutilise les cellules de 250 000 positions
`BASE`, `ROP16`, `EPS16`, `DECAY120`, `TOPK3M30`, `DEPTH10`, ainsi que les
contrôles `BASEBIS` et `NODECAY`. Il reconstruit, pour chacun des six régimes
admissibles, la covariance des 15 signaux de base depuis les moyennes, RMS et
corrélations auditées.

Le mélange est choisi sur une grille de 5 % en maximisant le log-déterminant
régularisé de la covariance poolée (`D-optimal design`). Les contraintes sont
figées avant lecture du résultat :

- `BASE >= 15 %` ;
- chaque intervention `>= 5 %` ;
- chaque cellule `<= 30 %` ;
- déplacement relatif du taux de nulles contre `BASE <= 15 %` ;
- asymétrie W/L `<= 2 %` ;
- dérive relative du tempo Scan moyen contre `BASE <= 15 %` ;
- `BASEBIS` reste un contrôle de bruit et `NODECAY` reste exclu.

Le corpus cible contient exactement 2 000 000 de positions. Avec un pas de
5 %, chaque quota est un multiple entier de 100 000 positions.

### Corrigendum avant génération

Les attempts de planification `1404` et `1407` n'ont généré aucune donnée et
ont révélé que la borne absolue `[45 %, 55 %]` appliquait une sémantique
erronée à `tempo_mid_weight_mean`. Cette quantité est le tempo Scan normalisé
par 300, pas une probabilité de phase centrée sur 0,5. La garde est donc
corrigée, avant toute génération et sans lecture d'un résultat de force, en
une dérive relative au régime `BASE <= 15 %`. Cela conserve l'intention
préenregistrée — empêcher un déplacement de phase — sur l'échelle réelle de
la variable.

## Écrans avant fit

Le corpus réellement généré devra confirmer : activation matérielle des 15
signaux, gardes WDL/phase, et gain strict de log-déterminant contre `BASE`.
Avant le fit PatternEval, le mapper aligned devra améliorer, relativement à
l'audit `CURRENT_2M`, les trois diagnostics de concentration :

- part maximale `<= 90 %` de la valeur courante ;
- part top-3 `<= 95 %` de la valeur courante ;
- nombre effectif de composantes `>= 125 %` de la valeur courante.

Un échec d'écran renvoie à la génération ; il n'est pas sauvé par un fit.

## Contraste causal ultérieur

À volume, parent, architecture, alpha `.30`, folds et recette constants :

1. `INTERVENTION_ALIGNED_CTX2_A30` ;
2. `INTERVENTION_SHUFFLED_CTX2_A30`, permutation WDL × phase identique.

Le primaire sera aligned − shuffled en force native 0,1 s, sur deux pools frais
disjoints. Q00 profondeur 9 restera diagnostique. Le contraste contre le
champion Curriculum ne sera autorisé que si aligned bat shuffled selon ce
protocole. Aucun frozen, aucune promotion automatique.
