# L3-IMBALANCE2-TOP3 — self-play haute matière

## Objet

Tester une sous-lignée indépendante entraînée uniquement depuis les trois strates de haute matière :

- `16v18` ;
- `17v19` ;
- `18v20`.

Aucune position de départ des quinze autres strates n'entre dans le corpus. La sous-lignée repart du bootstrap matériel G0 afin de ne pas conserver l'héritage d'un modèle entraîné sur `1v3..15v17`.

## Contrat d'entraînement

- P1 autonome G1–G4 à profondeur 8 ;
- 500 000 records frais par génération, répartis également entre les trois strates puis entre les deux couleurs avantagées ;
- self-play terminal WDL exclusivement ;
- positions initiales avec pions simples uniquement ;
- huit plies aléatoires, epsilon 8 %, décroissance au ply 60 ;
- Q00 complet, géométrie 8cf, L2 `3e-5` ;
- pondération fixe role-aware V2 `1/2/4` ;
- aucune donnée EGDB statique, aucun professeur Scan/Gen2, aucun replay ;
- G1 depuis G0 matériel, puis warm-start de la génération précédente.

La pondération adaptative W1 rejetée par `0887` n'est pas réutilisée. Le seul facteur expérimental modifié est la distribution de départ.

## Hypothèse mesurée

L'hypothèse utilisateur est qu'un avantage de deux pions dans ces configurations produit environ 80–90 % de victoires. Cette plage n'est pas imposée à l'entraînement et ne sert pas à sélectionner les parties.

Après G4, G0 et G4 jouent exactement les mêmes pools indépendants A64/B64, soit 128 parties par strate et par modèle. Le rapport publie :

- W/D/L global et par strate ;
- coût d'échec `2L+D` ;
- delta apparié G4−G0 ;
- IC bootstrap à 95 % ;
- indicateur d'appartenance à la plage 80–90 %.

Le verdict `TOP3_SPECIALIZATION_SIGNAL` exige :

- taux de victoire G4 global au moins égal à 80 % ;
- taux de victoire d'au moins 75 % dans chacune des trois strates ;
- coût d'échec G4 strictement inférieur à celui de G0 ;
- zéro erreur moteur.

Sinon le verdict est `TOP3_TARGET_NOT_REACHED`.

Dans les deux cas :

```text
promotion_authorized=false
training_continuation_authorized=false
automatic_next_job=null
```

Une éventuelle suite nécessitera une revue humaine, notamment parce que cette sous-lignée n'est pas évaluée comme généraliste sur les quinze strates retirées.
