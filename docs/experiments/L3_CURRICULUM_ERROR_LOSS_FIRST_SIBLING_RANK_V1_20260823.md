# L3 — corpus loss-first et classement borné des coups frères

Date : 23 août 2026

Statut : protocole préenregistré après l’audit 1541 ; aucun refit ou gate de force autorisé par ce document

## Cause mesurée

Le correcteur actionnel 1536 n’a produit aucune règle admissible. L’audit 1541
montre que deux changements de décision à l’échelle sentinelle représentent
74,13 % de la perte et que les trois pires en représentent 86,26 %. La pire
observation vaut −29 949,5 cp. Une moyenne de centipions donne donc à quelques
transitions de classe WDL un levier disproportionné.

## Intervention

Deux pools frais de 384 ouvertures sont joués par CURRICULUM byte-identique,
couleurs appariées, native 0,1 s. Toutes les parties et toutes les décisions
sont conservées. La sélection des candidats ne lit ni issue, ni score profond,
ni regret. Elle utilise seulement instabilité d6–d9, phase, matériel, capture
et branchement.

Chaque candidat est ensuite jugé sur tous ses coups légaux à profondeurs 10 et
12, dans les deux orientations exactes. Un label n’est accepté que si l’ordre
des coups et la classe WDL sont compatibles entre budgets et symétries.

La cible primaire est le classement listwise, masse unitaire par état et par
ouverture. Les préférences pairwise sont secondaires et la marge professeur
est plafonnée à 200 cp. Les scores bruts restent diagnostics.

## Étanchéité et contrôles

- composantes `opening_id/game_uid/état canonique` atomiques ;
- un vote maximum par ouverture et deux états maximum par partie ;
- contrôles sans remise appariés par pool, phase, rois, capture et branchement ;
- fit pool 1 vers pool 2 et réciproquement ;
- 1 000 shams stratifiés et bootstrap 200 000 par composante d’ouverture ;
- aucun refit de production avant réplication du signal sur les deux pools.

## Suite conditionnelle

Un screen mécanistique positif pourra sélectionner au plus 128 buckets
PatternEval canoniques à partir des Jacobiennes de feuilles PV. Le futur refit
gardera toutes les autres coordonnées exactement égales à CURRICULUM. Un
screen négatif ferme cette géométrie sans ajuster les seuils post-hoc.
