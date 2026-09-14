# L3 — extension Signal Factory : allocation adaptative du budget-nœuds

> Date : 6 août 2026
> Statut : proposition préenregistrée, **inactive avant le verdict M3**
> Portée de cette version : protocole seulement ; aucun job ni allocateur
> adaptatif n'est créé ou autorisé.

## 1. Question

À parent, volume, graines, exploration, recette de fit et coût de recherche
appariés, la qualité d'un corpus de self-play augmente-t-elle lorsque le budget
de calcul varie :

1. entre les parties ;
2. entre les coups d'une même partie ;
3. selon la phase de jeu ;
4. selon une estimation déterministe de la complexité de la position ?

L'intuition est d'éviter de dépenser le même effort nominal sur une position
triviale et sur une position tactique ou instable. L'objectif n'est toutefois
pas de reproduire un contrôle du temps humain : il est de maximiser la valeur du
corpus **à coût total égal**, puis de vérifier cette valeur contre l'Elo.

## 2. Frontière actuelle

Le mode expérimental livré avec la PR 416 sait déjà :

- limiter le PLAY search par un nombre exact de nœuds ;
- utiliser un budget fixe ou une distribution entière pondérée ;
- tirer une fois par partie (`sample_per=game`) ou à chaque coup
  (`sample_per=move`) ;
- reproduire les tirages depuis `(seed, game_id, ply, side_to_move)` ;
- publier le budget demandé/utilisé, les profondeurs complétée/effective, les
  interruptions et le coût mural dans un JSONL obligatoire.

Le pilote NB0 est déjà préenregistré dans
[`L3_NODE_BUDGET_PILOT_PREREGISTRATION_20260803.md`](L3_NODE_BUDGET_PILOT_PREREGISTRATION_20260803.md).
Il compare d8 fixe à une distribution de budgets tirée par coup. Son readout
autoritatif, lorsqu'il existe, est une entrée de cette extension ; il ne doit
pas être reconstruit ou réinterprété après lecture de ses résultats.

Le moteur ne sait pas encore faire dépendre le budget de la phase ou de la
position. Cette PR ne prétend pas le contraire.

## 3. Séquence causale

Une seule dimension change par étape.

| étape | contrôle | traitement | question isolée |
|---|---|---|---|
| NB0 | profondeur fixe d8 | distribution pondérée par coup | une limite en nœuds variable porte-t-elle un signal ? |
| NB1 | même distribution tirée par partie | même distribution tirée par coup | quelle granularité est utile ? |
| NB2 | budgets indépendants de la position | budgets conditionnés par phase | placer le calcul par phase vaut-il mieux que le hasard ? |
| NB3 | même coût et mêmes niveaux de budget, allocation témoin | allocation par complexité estimée avant recherche | le score place-t-il le calcul au bon endroit ? |

NB1 ne doit pas être confondu avec NB0 : un tirage par partie crée des parties
durablement rapides ou lentes, tandis qu'un tirage par coup mélange les forces
de jeu dans chaque trajectoire.

NB2 teste l'intuition initiale suivante, sans la figer avant calibration :

```text
ouverture  → budget faible
milieu     → budget élevé
finale     → budget moyen
```

Le témoin de NB2 doit conserver le même histogramme marginal de budgets et le
même coût demandé par record, mais affecter les budgets indépendamment de la
phase. Une simple comparaison contre d8 ne permettrait pas d'attribuer l'effet
à l'allocation par phase.

Le témoin de NB3 suit la même règle : il ignore le score de complexité tout en
préservant la distribution marginale et le coût agrégé. Les trajectoires étant
on-policy et donc divergentes, on n'exige pas une permutation position par
position impossible ; on exige des fenêtres de coût et de distribution figées
avant le run.

## 4. NB3 — complexité de position

### 4.1 Allocateur statique V1

La première version doit être calculable **avant** le PLAY search et rester peu
coûteuse. Les entrées candidates sont limitées à des propriétés observables de
la position courante :

- phase ou nombre de pièces ;
- nombre de coups légaux ;
- capture obligatoire ;
- nombre de captures concurrentes ;
- balance matérielle et présence de dames ;
- incertitude du modèle courant `p(1-p)`, avec contribution bornée.

Le score produit seulement trois classes :

```text
simple      → B_low
ordinaire   → B_mid
complexe    → B_high
```

Les features, seuils, budgets et poids doivent être figés avant la génération
scientifique. Aucun ajustement à partir des WDL, du holdout ou d'une première
porte n'est permis.

L'incertitude `p(1-p)` reste un signal dangereux : utilisée seule, elle devient
de l'apprentissage actif et peut attirer le corpus vers des positions bizarres
ou hors distribution. Elle ne peut être qu'un modificateur borné d'un score qui
conserve des ancrages structurels.

### 4.2 Instabilité après recherche

La volatilité du score entre profondeurs, les ré-essais d'aspiration ou le
changement de meilleur coup sont des diagnostics prometteurs, mais ils ne sont
connus qu'après avoir commencé la recherche. Ils ne peuvent influencer le
budget du même coup que dans un protocole séparé de type **probe puis top-up** :

1. probe déterministe de coût `B_probe` pour toutes les positions ;
2. calcul d'un score d'instabilité préenregistré ;
3. top-up borné vers `B_mid` ou `B_high` ;
4. comptabilité du probe et du top-up dans le coût total.

Ce protocole est NB3b, hors de V1. Réutiliser silencieusement une table de
transposition chaude ou relancer une recherche complète changerait le coût et
doit être spécifié avant toute implémentation.

### 4.3 Signaux interdits

L'allocateur ne lit jamais :

- le résultat terminal de la partie ;
- le WDL qui sera écrit ;
- une vérité EGDB non disponible au joueur témoin ;
- la sélection future du record dans train/holdout ;
- une métrique ou un Elo provenant du même run.

## 5. Ce que le budget améliore réellement

Dans le pipeline WDL pur, le budget-nœuds contrôle le **PLAY search**. Le label
d'un record reste le résultat terminal de la partie. Donner plus de nœuds à une
position ne nettoie donc pas directement son label : cela peut changer le coup,
la trajectoire, les positions visitées et finalement le résultat de partie.

Trois niveaux doivent être distingués dans le readout :

1. **recherche locale** : profondeur complétée, meilleur coup, interruption,
   accord éventuel avec une référence profonde ;
2. **corpus** : contamination, ply-cap, WDL, désaccord EGDB, Fisher et structure ;
3. **valeur finale** : Elo du modèle entraîné sous une recette inchangée.

Les deux premiers expliquent un résultat ; seul le troisième juge la force.

## 6. Appariement du coût

Chaque contraste publie au minimum :

- nœuds demandés et utilisés par partie, coup et record émis ;
- histogramme des budgets et part de recherches terminées avant le plafond ;
- profondeur complétée/effective et taux d'itérations interrompues ;
- temps mural, NPS et positions émises par minute ;
- nombre de parties, plies et rejets au ply-cap.

Le coût causal primaire à apparier est le **nombre total de `nodes_used` par
record émis**. L'enveloppe demandée et l'histogramme des budgets doivent eux
aussi rester appariés : une recherche peut finir avant son plafond, donc
`nodes_budget` seul ne représente pas toujours le travail réellement effectué.
Le temps mural est un garde opérationnel, pas l'unité causale : il varie avec
la machine, le cache et l'ordonnancement.

La calibration est aveugle aux résultats et précède les bras scientifiques.
Elle ne lit ni WDL, ni holdout, ni métrique M1, ni Elo. Les bras doivent aussi
finir avec le même nombre de records d'entraînement ; une différence de volume
rend le contraste ininterprétable.

Pour NB2/NB3, le contrôle et le traitement doivent rester dans une fenêtre
préenregistrée de coût demandé. Une tolérance, un nombre maximal de
recalibrations et la règle d'arrêt sont à figer dans le futur template ; aucune
valeur n'est choisie post-hoc.

## 7. Artefacts obligatoires

Chaque bras produit et authentifie :

- JNNW et sidecar JSM2 alignés ;
- JSONL de provenance budget-nœuds ;
- manifeste de distribution et version de l'allocateur ;
- fiche M1 avant et après tout filtre autorisé ;
- hashes du corpus, du modèle parent, du code et des poids entraînés ;
- rapport de coût et test de reproductibilité ;
- modèle entraîné sous la recette championne figée ;
- readout Elo séparé sur ouvertures fraîches appariées.

Le manifeste doit permettre de distinguer sans inférence : `fixed_depth`,
`random_per_game`, `random_per_move`, `phase_conditioned` et
`position_adaptive`.

## 8. Règles de décision

Pour chaque étape, le contraste primaire est le traitement moins son contrôle
direct, jamais le traitement seul contre le parent.

- IC95 Elo entièrement positif : signal détecté pour cette étape ;
- IC95 Elo entièrement négatif : politique rejetée ;
- IC95 recouvrant zéro : étape non concluante ; aucune continuation automatique.

La ou les métriques validées par M3 doivent évoluer dans le sens préenregistré,
mais ni le holdout ni la couverture ne peuvent remplacer la porte Elo. Un gain
qui ne survit pas à l'appariement du coût ou du volume est rejeté.

Un résultat NB0 négatif ne réfute pas logiquement NB3 : une allocation ciblée
est une autre hypothèse qu'un tirage aléatoire. Il interdit toutefois d'enchaîner
automatiquement ; un go humain explicite et un nouveau préenregistrement sont
alors nécessaires.

Pour tous les bras :

```text
promotion_authorized=false
automatic_next_job=null
```

## 9. Relation à M3 et conditions d'activation

Cette extension ne change ni les cellules, ni les jobs, ni les règles de M3.
Elle appartient à M4 parce qu'elle modifie la politique du joueur qui génère
les trajectoires et donc la qualité des résultats terminaux.

Conditions nécessaires avant tout job NB1, NB2 ou NB3 :

1. M3 a rendu son verdict ;
2. au moins une métrique de corpus est validée contre l'ordre Elo, sinon M4 est
   bloqué par la charte ;
3. le readout NB0 disponible est lu et archivé sans modifier sa règle ;
4. le parent, le coût cible, le contraste et la puissance sont préenregistrés ;
5. JFC donne un go scientifique explicite.

NB2 et NB3 exigent en plus une implémentation revue : nouvelle politique
versionnée, manifeste complet, tests unitaires du score, reproductibilité du
sampler, contrôles fail-closed et smoke à coût borné. Cette PR documentaire ne
fournit aucune de ces pièces et n'autorise donc aucun lancement adaptatif.
