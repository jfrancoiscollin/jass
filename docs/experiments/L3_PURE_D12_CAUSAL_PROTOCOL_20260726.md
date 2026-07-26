# L3-PURE — bras causal d12 à volume constant

Date : 26 juillet 2026.

## Déclencheur

`home-0972-l3-pure-d10-causal-independent-eval-v1` termine avec le verdict
`D10_PLATEAU_OR_REGRESSION_REVIEW`, tous les garde-fous valides :

- D10 contre M2 d8 : 47,50 % Q00 et 50,70 % native ;
- D10 contre F2M : 48,80 % Q00 et 51,00 % native ;
- D10 contre Gen2 : 56,70 % Q00 et 58,40 % native ;
- conversion P3/P4 : 99,33 % et 98,67 % ;
- couverture D10 moins M2 : -4 864 buckets visités et -494 buckets vus au
  moins 100 fois.

La profondeur d10 ne crée donc pas de pente de force reproductible. Elle
préserve la conversion, mais produit deux vues de force de signes opposés.

## Question causale

À parent, volume, architecture, objectif, exploration, seeds, split et
optimisation constants, une génération de self-play à d12 produit-elle un
modèle plus fort que le contrôle d10 ?

Le bras reste un test à un facteur : seule la profondeur de jeu passe de d10 à
d12. Le parent et le warm-start restent **F2M**, et non D10, afin que les
corpus d8, d10 et d12 soient trois bras appariés issus du même modèle.

| Facteur | contrôle D10 | bras D12 |
|---|---:|---:|
| profondeur de jeu | 10 | 12 |
| parent et warm-start | F2M | F2M |
| positions fraîches | 2 000 000 | 2 000 000 |
| seeds producteurs | 1 618 033 + shard | identiques |
| architecture | 8cf | 8cf |
| recherche | Q00 | Q00 |
| objectif | WDL terminal pur | WDL terminal pur |
| split | JSM par ouverture | identique |
| fit | L-BFGS, L2 3e-5 | identique |

Un mix d10/d12 n'est pas utilisé dans ce bras : il changerait à la fois la
profondeur et la distribution du corpus. Il pourra être testé séparément si
la profondeur pure demeure ambiguë.

Sont interdits : oracle, teacher, TOP3, reweight V2, replay historique,
changement de géométrie et mélange avec L3-IMBALANCE2.

## Entraînement

`home-0973-l3-pure-d12-causal-fresh2m-train-v1` doit :

1. vérifier le certificat 0972 et l'identité exacte du modèle D10 ;
2. vérifier le parent immuable F2M ;
3. construire et tester le moteur réparé ;
4. générer exactement 2 millions de positions à d12 avec les seeds appariées ;
5. archiver JNNW/JSM et leurs SHA avant le fit ;
6. fitter depuis F2M jusqu'à convergence ;
7. publier loss holdout, RAM, manifests et modèle D12.

L'entraînement n'autorise qu'une évaluation séparée. Aucune promotion ou
continuation n'est automatique.

## Évaluation prévue

Après un entraînement valide, un job séparé utilisera un nouveau pool unique
et disjoint pour comparer D12 à D10, F2M et Gen2 en Q00 d9 et en cadence
native. Il répétera les jauges P3/P4 à défenseur fixe et la couverture exacte.

Une borne basse à 95 % au-dessus de 50 % contre D10 dans les deux vues,
accompagnée de garde-fous valides contre F2M, Gen2 et la conversion, est
nécessaire pour conclure à un effet causal fort. Un signal seulement
directionnel ouvre une confirmation indépendante. Un nouveau plateau ferme
la simple escalade de profondeur et fait passer au facteur suivant
préenregistré — distribution multi-profondeur ou replay/volume — sans
promotion implicite.
