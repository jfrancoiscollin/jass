# L3 — pilote self-play à budget de nœuds variable

> Date : 3 août 2026
> Statut : lancement HOME explicitement autorisé par JFC ; aucun résultat
> scientifique consulté au moment de figer ce plan.

## Question

À parent, volume frais, graines, exploration et recette d'entraînement
identiques, remplacer la recherche de jeu historique à profondeur 8 par une
distribution déterministe de budgets de nœuds produit-il un signal de force ?

Ce run est un **screen à deux bras**, pas une porte de succession. Son volume
scientifique est volontairement borné à **2 millions de records frais au
total** :

- `DEPTH` : 1 000 000 de records ;
- `NODES` : 1 000 000 de records.

Les trois cellules de calibration de 6 000 records sont jetées. Une quatrième
cellule de confirmation est autorisée uniquement si la quantification rate la
fenêtre de coût au premier essai. Elles ajoutent donc au plus 24 000 records de
travail et n'entrent dans aucun corpus ni fit.

Le parent des deux bras est le champion PRIORTIGHT :

```text
sha256 décompressé
2bbe1733ca0976ce4934131f83178a9e3757b5bc7a9b5a3bdbc41984781dfec7

r2:jass-data/runs/cpx62-1159-l3-prior-tight-refit-v1/
  20260802T171908Z-646f1149/artefacts/exact.pjtw.gz
```

## Facteur expérimental

| Paramètre | DEPTH | NODES |
|---|---:|---:|
| limite active du PLAY search | profondeur 8 | budget pondéré par coup |
| records frais | 1 M | 1 M |
| parent | PRIORTIGHT | PRIORTIGHT |
| graines de shards | identiques | identiques |
| ouvertures appariées | oui | oui |
| RNG self-play séparés | oui | oui |
| exploration | uniforme, 8 %, décroissance au pli 60 | identique |
| label | WDL terminal, aucune recherche de score | identique |
| fit | exact-fold + prior-mean PRIORTIGHT | identique |
| L2 / gtol | `3e-5` / `1e-4` | identique |

La comparaison primaire est `NODES - DEPTH`. Comparer seulement le candidat
NODES au parent confondrait l'effet du self-play on-policy frais avec le type de
limite de recherche.

## Calibration HOME, aveugle aux résultats

La distribution proposée initialement est :

```text
5000:10,20000:25,80000:35,300000:20,1200000:10
```

Sa moyenne demandée vaut 213 500 nœuds par coup. Elle n'est pas lancée à
l'échelle sans calibration :

1. 6 000 records depth et 6 000 records nodes sont générés séquentiellement,
   avec six producteurs et les mêmes graines ;
2. le ratio des temps muraux définit un facteur de redimensionnement ;
3. chaque bucket est arrondi au millier de nœuds le plus proche, borné au
   minimum moteur de 1 000 nœuds, et les buckets devenus identiques sont
   fusionnés ;
4. le facteur doit rester dans `[0,005 ; 5,00]` ;
5. un second canari nodes de 6 000 records doit coûter entre `0,75×` et
   `1,35×` le témoin depth ;
6. si ce canari rate la fenêtre, un unique redimensionnement de feedback est
   calculé à partir de son ratio de temps, puis un dernier canari de 6 000
   records doit satisfaire la même fenêtre. Un second échec arrête le job.

La calibration et son éventuel feedback ne lisent ni WDL, ni holdout, ni
force. Le feedback a été ajouté après qu'un premier canari purement technique a
mesuré `1,409×`, juste hors de la fenêtre, à cause du plancher à 1 000 et de
l'arrondi par millier ; aucun bras scientifique n'avait alors démarré. Si un
garde échoue, le job s'arrête **avant** les deux bras de 1 M. La distribution
réellement utilisée, les temps, le ratio et la version du sampler sont publiés
dans les artefacts.

## Readout

Le job de génération entraîne et authentifie les deux modèles, puis s'arrête.
Un job séparé devra opposer NODES à DEPTH sur des ouvertures fraîches appariées,
les deux couleurs et les deux vues Q00/native. Le holdout et la couverture sont
des diagnostics, jamais la règle de sélection.

- IC95 Elo entièrement positif : signal détecté ; autorise une réplication
  ultérieure à 2 M par bras avec le champion alors gelé ;
- IC95 entièrement négatif : distribution rejetée ;
- IC95 recouvrant zéro : pilote non concluant, aucune promotion.

Même en cas de signal positif :

```text
promotion_authorized=false
automatic_next_job=null
```

## Implémentation

Le contrat exécutable est
`jobs/templates/l3-node-budget-pilot-2m-v1.sh`. Il utilise le mode expérimental
introduit par la PR 416, conserve le mode depth historique dans le bras témoin
et archive la télémétrie nodes compressée.
