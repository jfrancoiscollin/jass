# L3 — atlas des erreurs de recherche de CURRICULUM

Date : 22 août 2026

Statut : protocole préenregistré, read-only avant toute modification moteur

## Motivation

L’autopsie `1474/1475b` a authentifié 79 110 décisions et 388 regrets apparents
d’au moins 50 cp dans des défaites de CURRICULUM. Elle n’a cependant établi
aucune région PatternEval : seulement 10 contrôles, 2,57732 % de matching,
zéro bucket confirmé et un delta de symétrie de recherche de 8 cp.

La voie « refit local » est donc fermée. La présente expérience teste si le
signal vient plutôt de la recherche : instabilité entre profondeurs, faible
marge racine, désaccord sous l’image exacte, ou pruning sélectif.

Les poids CURRICULUM restent byte-identiques. Il n’y a ni corpus, ni fit, ni
self-play, ni partie de force dans cet écran.

## Mesure exactement symétrisée

Pour chaque racine, le moteur analyse la position et son image exacte
`rot180 + colour-swap`. Tout coup candidat est appliqué dans les deux images.
Les deux enfants sont jugés à la même profondeur par le même modèle et la
valeur publiée est :

`2 * V_sym(root, action) = -V(child) - V(exact_image(child))`.

Le calcul reste entier en demi-centipions. La commutation
`image(after(root, move)) == after(image(root), image(move))` est vérifiée pour
chaque action. Un delta de perspective ne peut donc plus décider le résultat :
la symétrie est imposée par construction, pas seulement sondée.

## Contrôles décisionnels

Les erreurs source restent une par `opening_id`, perte, mouvement différent et
regret source >=50 cp. Les contrôles changent de niveau : ce sont des décisions
stables (regret source <=10 cp) provenant d’ouvertures qui ne contiennent
aucune des 388 erreurs retenues. Le résultat terminal de leur partie n’est pas
un critère, car la question causale est la difficulté de la décision.

Le matching est sans remise, dans le même split scellé et sur une autre
ouverture. Les calipers préenregistrés portent sur :

- phase, capture/quiet ;
- nombre total de pièces (±2), dames (±1), balance STM (±2) ;
- coups légaux (±3), ply (±12) ;
- bin de marge top1/top2 voisin ;
- nombre de flips entre profondeurs 8, 9 et 10 (±2).

Au moins 80 % des erreurs doivent recevoir un contrôle. `discovery` et
`confirm` restent séparés par les composantes `opening_id <-> état exact` déjà
scellées avant lecture des regrets.

Le budget n’est pas estimé sur ce jeu cas–témoins, qui surreprésente les
erreurs. Un échantillon déterministe sans lecture du regret ni du résultat,
1 024 décisions par split, est scellé avant la sélection des contrôles. Il sert
exclusivement à mesurer le coût moyen de la politique dans la population.

## Atlas mécanistique

Sur chaque paire, un root trace depths 1..12 publie mouvement, score et coût
cumulé en nœuds. Tous les coups légaux de la racine — dont les actions choisies
aux profondeurs 8..12 et l’action historique — sont jugés exactement comme
ci-dessus. L’atlas publie :

- profondeur du flip, volatilité du score et marge top1/top2 ;
- désaccord position/image exacte ;
- regret historique et regret de chaque profondeur ;
- nombre de nœuds de chaque profondeur ;
- cinq ablations search-only : `NO_FORWARD`, `NO_LMR`, `NO_LMP`,
  `NO_ASP_PVS`, `FULL_WIDTH`.

Une famille de pruning est dite localisée seulement si son taux de présence de
l’action teacher gagne au moins 5 points sur Q00, à la fois sur discovery et
confirm. Cette classification reste diagnostique : elle ne suffit pas à
modifier le moteur.

## Contrôleur à budget moyen constant

Le contrôleur de production ne lit, dans l’orientation effectivement jouée,
que les informations disponibles après profondeur 9 :

- flip d8->d9 ;
- marge racine <=50 cp ;
- volatilité de score >=50 cp.

L’image exacte est utilisée uniquement par l’écran offline pour rendre la
mesure symétrique et vérifier la robustesse. Elle n’est jamais calculée par le
contrôleur en partie et ne lui sert pas d’oracle.

Le score de risque est le nombre de drapeaux actifs. Sur `discovery` seulement,
on choisit parmi les seuils 1..4, une profondeur risquée 11/12 et une profondeur
stable 9/10. La profondeur 8 est exclue de l’économie de budget : le risque
n’est observable qu’après avoir réellement payé d9. Une configuration est
recevable si :

- son coût moyen est entre 98 % et 100 % de d10 ;
- elle baisse regret moyen et taux d’erreur >=50 cp dans les erreurs ;
- elle ne dégrade ni regret ni taux d’erreur des contrôles.

La configuration choisie est appliquée une seule fois à `confirm`. L’écran
passe seulement si :

- matching >=80 %, au moins 64 erreurs restent >=50 cp après symétrisation et
  les deux splits sont non vides ;
- toutes les commutations exactes passent ;
- au moins 512 décisions de budget sont disponibles dans chaque split et le
  budget confirm reste dans [0,98 ; 1,00] de d10 sur cette population ;
- les IC95 bootstrap du gain de regret et de taux d’erreur excluent zéro ;
- les contrôles confirm ne régressent pas.

Un PASS autorise seulement l’implémentation d’un contrôleur moteur et son test
hors échantillon. Il n’autorise ni promotion ni fit. Un FAIL ferme précisément
par manque de matching, disparition du signal après symétrisation, absence de
politique budget-neutre ou non-confirmation.

## Étape suivante conditionnelle

Uniquement après PASS : implémenter la politique scellée dans la recherche,
vérifier les poids CURRICULUM byte-identiques et le budget natif, puis lancer
deux pools frais disjoints. Native 0,1 s est primaire ; Q00 d9 reste diagnostic.
Il n’y a aucune promotion automatique.
