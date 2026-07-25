# L3-PURE — bras causal d10 à volume constant

Date : 26 juillet 2026.

## Déclencheur

L'évaluation indépendante `home-0970bis` ferme la continuation mécanique de
la recette d8/2M :

- M2 contre F2M Q00 d9 : 50,60 %, IC95 [47,54 ; 53,66] ;
- M2 contre F2M native 0,1 s/coup : 49,05 %, IC95 [45,98 ; 52,12] ;
- M2 contre Gen2 réparé : 56,30 % Q00 et 58,80 % native ;
- conversion M2 : 99,00 % sur `p3_mince`, 98,67 % sur `p4_egal` ;
- couverture M2 moins F2M : +2 075 buckets visités et +352 buckets vus au
  moins 100 fois.

Le verdict préenregistré est `M2_PLATEAU_OR_REGRESSION_REVIEW`, tous les
garde-fous passent et la recommandation est
`stop_same_recipe_and_prepare_d10_causal_arm`. La couverture supplémentaire
ne s'est donc pas transformée en pente de force à d8.

## Question causale

À parent, volume, architecture, objectif, exploration, seeds, split et
optimisation constants, une génération de self-play à d10 produit-elle un
modèle plus fort que le contrôle d8 M2 ?

Un seul facteur change :

| Facteur | contrôle M2 | bras D10 |
|---|---:|---:|
| profondeur de jeu | 8 | 10 |
| parent et warm-start | F2M | F2M |
| positions fraîches | 2 000 000 | 2 000 000 |
| seeds producteurs | 1 618 033 + shard | identiques |
| architecture | 8cf | 8cf |
| recherche | Q00 | Q00 |
| objectif | WDL terminal pur | WDL terminal pur |
| split | JSM par ouverture | identique |
| fit | L-BFGS convergé, L2 3e-5 | identique |

Les seeds identiques constituent une randomisation appariée intentionnelle :
les trajectoires peuvent diverger sous l'effet de la profondeur, mais la
source d'aléa et les ouvertures initiales sont contrôlées. Le corpus D10 est
nouvellement généré ; aucun record M2 n'est rejoué dans le fit.

Sont interdits : oracle, teacher, TOP3, reweight V2, replay historique,
changement de géométrie et mélange avec L3-IMBALANCE2.

## Entraînement

Le job `home-0971-l3-pure-d10-causal-fresh2m-train-v1` doit :

1. vérifier le certificat de plateau `home-0970bis` et le parent F2M ;
2. installer NumPy 1.26.4 et SciPy 1.14.1 dans un venv isolé ;
3. construire et tester le moteur réparé ;
4. générer exactement 2 millions de positions à d10 ;
5. publier JNNW/JSM et leurs SHA avant le fit ;
6. fitter depuis F2M jusqu'à convergence, maximum 1 000 itérations ;
7. publier le modèle D10, la loss holdout, la RAM et les manifests.

Un entraînement valide autorise seulement une évaluation séparée.

## Évaluation préenregistrée

Le readout D10 utilisera un nouveau pool d'ouvertures unique et disjoint de
tous les pools M1/M2 :

- D10 contre M2 d8, 1 000 parties Q00 d9 et 1 000 parties native ;
- D10 contre F2M, mêmes deux vues ;
- D10 contre Gen2 réparé comme garde-fou ;
- conversion P3/P4 contre le défenseur Gen2 historique corrigé ;
- couverture exacte D10 contre M2 et F2M.

Une supériorité causale forte exige une borne basse à 95 % au-dessus de 50 %
contre M2 dans les deux vues, sans régression contre F2M, Gen2 ou la
conversion. Deux estimations positives mais non concluantes ouvrent seulement
une confirmation indépendante. Si D10 reste plat, aucun nouveau tour
identique n'est lancé : le facteur suivant sera préenregistré séparément,
d'abord d12 ou un mix d10/d12 à volume constant, puis seulement le
volume/replay cumulatif.

Aucune promotion n'est automatique.
